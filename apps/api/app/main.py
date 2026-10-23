"""Application factory. `ROLE` decides what this process runs (ADR-0002)."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, load_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.request_context import REQUEST_ID_HEADER, RequestContextMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings)

    app = FastAPI(title="DocFlow API", version="0.1.0")
    app.state.settings = settings

    install_error_handlers(app)
    # Starlette runs the last-added middleware first: CORS wraps everything, so even
    # last-resort 500s carry CORS headers and the browser can read them.
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_origin_regex=settings.cors_allowed_origin_regex,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )
    return app
