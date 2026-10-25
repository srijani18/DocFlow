from typing import Protocol

from app.llm.types import ProviderRequest, ProviderResponse


class Provider(Protocol):
    name: str

    async def generate(self, request: ProviderRequest) -> ProviderResponse: ...
