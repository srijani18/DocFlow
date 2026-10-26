from typing import Protocol

from app.llm.inputs import Capabilities
from app.llm.types import ProviderRequest, ProviderResponse


class Provider(Protocol):
    name: str
    capabilities: Capabilities

    async def generate(self, request: ProviderRequest) -> ProviderResponse: ...
