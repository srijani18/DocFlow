"""Process entrypoint: `python -m app`.

ROLE=api|all  -> uvicorn serving the FastAPI app (ROLE=all also runs the worker inside it)
ROLE=worker   -> the worker loop alone, with no HTTP server
"""

import asyncio
import contextlib
import signal

import uvicorn

from app.core.config import Settings, load_settings
from app.core.logging import configure_logging
from app.main import create_app
from app.wiring import build_services


def serve_http(settings: Settings) -> None:
    uvicorn.run(
        create_app(settings),
        host="0.0.0.0",  # noqa: S104  # runs in a container; the platform routes traffic to it
        port=settings.port,
        workers=1,
        proxy_headers=True,
        forwarded_allow_ips="*",
        access_log=False,  # RequestContextMiddleware logs each request with its request_id
    )


async def _run_worker_until_signal(settings: Settings) -> None:
    services = build_services(settings)
    if services.worker is None:  # pragma: no cover - only called for ROLE=worker
        raise RuntimeError("ROLE does not run the worker")
    task = asyncio.create_task(services.worker.run())
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, task.cancel)
    try:
        with contextlib.suppress(asyncio.CancelledError):
            await task
    finally:
        await services.aclose()


def run_worker_process(settings: Settings) -> None:
    configure_logging(settings)
    asyncio.run(_run_worker_until_signal(settings))


def main(settings: Settings | None = None) -> None:
    settings = settings or load_settings()
    if settings.role.serves_http:
        serve_http(settings)
    else:
        run_worker_process(settings)


if __name__ == "__main__":
    main()
