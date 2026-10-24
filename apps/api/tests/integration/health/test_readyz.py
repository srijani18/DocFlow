import httpx


async def test_readyz_ok_with_database(db_client: httpx.AsyncClient) -> None:
    response = await db_client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
