"""`/mcp` over HTTP: bearer-token authentication in front of the SDK's Streamable HTTP app
(F12 AC4).

The SDK's own bearer middleware expects an OAuth authorization server. Our tokens are issued
in DocFlow's Settings instead (spec D2), so this wrapper checks them itself, then hands the
verified token to the tools through the request state.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.errors import PROBLEM_TYPE_BASE
from app.core.rls_system import become_system
from app.mcp import tokens
from app.mcp.server import STATE_KEY, McpDeps, build_mcp

MCP_PATH = "/mcp"
METADATA_PATH = "/.well-known/oauth-protected-resource/mcp"


def streamable_http_app(server: MCPServer) -> ASGIApp:
    return server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        stateless_http=True,  # no server-side sessions: any request can land anywhere
        json_response=True,
        # Every request needs a DocFlow token, which a DNS-rebinding page can't have, and
        # the public host differs per deployment; so no host allow-list.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )


def install_mcp(app: FastAPI, deps: McpDeps) -> MCPServer:
    """Serve the MCP server at `/mcp` and its metadata. The caller runs
    `server.session_manager.run()` in the app's lifespan: a route's app has no lifespan."""
    server = build_mcp(deps)
    # A route, not a mount: a mount would answer POST /mcp with a redirect to /mcp/.
    app.router.routes.append(
        Route(
            MCP_PATH,
            endpoint=TokenAuth(streamable_http_app(server), deps),
            methods=["GET", "POST", "DELETE"],
        )
    )

    @app.get(METADATA_PATH, include_in_schema=False)
    async def mcp_resource_metadata(request: Request) -> dict[str, Any]:
        return resource_metadata(request)

    return server


@asynccontextmanager
async def running(server: MCPServer) -> AsyncIterator[None]:
    """Run the transport's session manager for the app's lifetime. It holds an anyio task
    group, which must be entered and exited in one task: so it lives in its own task, not
    in whichever task happens to run the lifespan."""
    started, stop = asyncio.Event(), asyncio.Event()

    async def hold() -> None:
        async with server.session_manager.run():
            started.set()
            await stop.wait()

    task = asyncio.create_task(hold(), name="mcp-sessions")
    await started.wait()
    try:
        yield
    finally:
        stop.set()
        await task


def resource_metadata(request: Request) -> dict[str, Any]:
    """RFC 9728 protected-resource metadata. There's no authorization server to list:
    tokens are created in DocFlow's Settings."""
    return {
        "resource": str(request.url.replace(path=MCP_PATH, query="")),
        "resource_name": "DocFlow",
        "bearer_methods_supported": ["header"],
    }


class TokenAuth:
    def __init__(self, app: ASGIApp, deps: McpDeps) -> None:
        self.app = app
        self.deps = deps

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        header = Headers(scope=scope).get("authorization", "")
        scheme, _, token = header.partition(" ")
        verified = None
        if scheme.lower() == "bearer" and token:
            async with self.deps.open_session() as session:
                # The token names the workspace, so it is looked up across all (F14 AC3).
                await become_system(session)
                verified = await tokens.verify_token(
                    session, token.strip(), now=self.deps.clock.now()
                )
                await session.commit()  # last_used_at
        if verified is None:
            await self._unauthorized(scope, send)
            return
        scope.setdefault("state", {})[STATE_KEY] = verified
        structlog.contextvars.bind_contextvars(workspace_id=str(verified.scope.workspace_id))
        await self.app(scope, receive, send)

    async def _unauthorized(self, scope: Scope, send: Send) -> None:
        # The same answer for a missing, wrong, expired, revoked or other-workspace token.
        metadata_url = str(Request(scope).url.replace(path=METADATA_PATH, query=""))
        body = json.dumps(
            {
                "type": f"{PROBLEM_TYPE_BASE}unauthorized",
                "title": "Unauthorized",
                "status": 401,
                "detail": "Create an access token in DocFlow: Settings, AI assistants (MCP).",
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/problem+json"),
                    (b"www-authenticate", f'Bearer resource_metadata="{metadata_url}"'.encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
