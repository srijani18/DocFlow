import httpx


async def test_healthz_ok_without_database(client: httpx.AsyncClient) -> None:
    # The default test settings point the database at a closed port.
    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_503_when_database_unreachable(client: httpx.AsyncClient) -> None:
    response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["retry-after"] == "5"
    assert response.json()["type"].endswith("/database-unavailable")
