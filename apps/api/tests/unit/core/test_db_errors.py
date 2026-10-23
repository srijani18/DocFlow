from fastapi import FastAPI
from sqlalchemy import text

from app.core.db import DbSession
from tests.conftest import asgi_client


async def test_unreachable_database_maps_to_503(app: FastAPI) -> None:
    # The default test settings point at a closed port.
    @app.get("/_test/query")
    async def query(session: DbSession) -> None:
        await session.execute(text("SELECT 1"))

    async with await asgi_client(app) as client:
        response = await client.get("/_test/query")

    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert response.json()["type"].endswith("/database-unavailable")
