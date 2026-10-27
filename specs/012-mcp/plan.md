# F12: MCP server (plan)

**Status:** Draft (2026-10-27)
**Spec:** [spec.md](spec.md) · **Tasks:** [tasks.md](tasks.md)

## 1. Library

`mcp==2.3.0` (2026-10-02, the newest at least 2 weeks old). In 2.x, FastMCP is renamed `MCPServer` (`mcp.server.mcpserver`). The pieces used:
- `MCPServer(name, instructions, token_verifier=…, auth=AuthSettings(…))`;
- `@server.tool()` with typed parameters (the input schema is generated from them);
- `server.streamable_http_app(stateless_http=True, json_response=True, streamable_http_path="/")`, mounted at `/mcp`.

The SDK's bearer middleware calls our `TokenVerifier` and serves `/.well-known/oauth-protected-resource/mcp` (RFC 9728) for AC4.

## 2. Data

```
api_tokens (migration 0012_api_tokens)
  id uuid pk, workspace_id uuid fk → workspaces (index), user_id uuid fk → users,
  name text, prefix text (first 8 chars, shown), token_hash text unique (sha256 hex),
  created_at, expires_at, last_used_at null, revoked_at null
```

- **Token format:** `dfw_` followed by 32 random bytes in base64url (43 characters). Its sha256 is the lookup key; there's no salt, as the token itself is high-entropy (the same reasoning as GitHub tokens).
- **`last_used_at`:** updated at most once a minute per token, so each MCP call doesn't cost a write.

## 3. API (tokens)

```yaml
/v1/workspaces/{workspace_id}/api-tokens:
  get:  list (own tokens; all tokens for admins) → [{id, name, prefix, user, created_at,
        expires_at, last_used_at, revoked_at, active}]
  post: {name, expires_in_days: 30|90|365} → 201 {id, name, prefix, expires_at, token}
        (token only here, once)
/v1/workspaces/{workspace_id}/api-tokens/{token_id}:
  delete: revoke (own token, or any token as admin) → 204; already revoked → 204
```

## 4. Server (`app/mcp`)

```
app/mcp/tokens.py       create/hash/verify; WorkspaceTokenVerifier(sessionmaker).verify_token(token)
                        → AccessToken(client_id=token id, subject=user id,
                          claims={workspace_id, role}) after checking expiry, revocation, membership
app/mcp/server.py       build_mcp(services) -> MCPServer with the 4 tools; each tool opens one
                        session, rebuilds the WorkspaceScope from get_access_token(), calls services
app/mcp/summaries.py    list_vendors / spend_summary SQL (GROUP BY vendor_name | date_trunc
                        month | doc_type, currency), approved via approved_extraction_id
app/main.py             app.mount("/mcp", mcp_app); its session manager runs in the lifespan
```

- **Tool results:** compact JSON as text content (structured output where the SDK supports it), with ids and links to the app (`{WEB_BASE_URL}/app/documents/{id}`; new setting `WEB_BASE_URL`).
- **Errors:** "not found" for a missing or other-workspace id (AC6). Bad arguments become MCP tool errors, not HTTP 500s.
- **Transport security:** set `TransportSecuritySettings` allowed hosts from the API's public host, protecting against DNS rebinding. CORS isn't involved: MCP clients aren't browsers.

## 5. Web

**Settings → AI assistants (MCP)** panel:
- token list;
- a create dialog (name, expiry) that shows the token once, with copy-paste snippets:
  - `claude mcp add --transport http docflow <api>/mcp --header "Authorization: Bearer <token>"`;
  - a Claude Desktop `mcp-remote` config;
  - a generic JSON config;
- revoke with confirmation.

## 6. Testing

- **Unit:**
  - token generation, hashing, verification (expired, revoked, removed member, wrong format);
  - `spend_summary` grouping and per-currency totals.
- **Integration:**
  - the real SDK client (`mcp.client` over an ASGI transport) lists the tools and calls each one against seeded data;
  - 401 without, or with a revoked, token;
  - cross-workspace document id returns not found (AC6);
  - logs contain no arguments (AC7).
- **Web:** create (token shown once), list, revoke.
- **Live:** Claude Code connected to the local server with a real token asks "how much did we spend per vendor?" and gets the dev workspace's figures. A screenshot goes in the PR.
