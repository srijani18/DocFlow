from typing import Protocol

from app.llm.inputs import Capabilities
from app.llm.types import (
    ProviderEmbedRequest,
    ProviderEmbedResponse,
    ProviderRequest,
    ProviderResponse,
)


class Provider(Protocol):
    name: str
    capabilities: Capabilities

    async def generate(self, request: ProviderRequest) -> ProviderResponse: ...


class Embedder(Protocol):
    """A provider that can also embed text (F8). Only Gemini does today."""

    name: str

    async def embed(self, request: ProviderEmbedRequest) -> ProviderEmbedResponse: ...
