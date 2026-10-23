import re

import httpx


async def test_request_id_is_echoed_when_valid(client: httpx.AsyncClient) -> None:
    response = await client.get("/does-not-exist", headers={"X-Request-ID": "abc-123_x.y"})

    assert response.headers["x-request-id"] == "abc-123_x.y"


async def test_request_id_is_generated_when_missing_or_invalid(client: httpx.AsyncClient) -> None:
    missing = await client.get("/does-not-exist")
    invalid = await client.get("/does-not-exist", headers={"X-Request-ID": "bad id\twith spaces"})

    for response in (missing, invalid):
        assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])
    assert missing.headers["x-request-id"] != invalid.headers["x-request-id"]
