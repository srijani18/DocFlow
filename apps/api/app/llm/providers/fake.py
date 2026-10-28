"""Scripted provider for tests and CI (ADR-0003): no network, no key."""

import hashlib
import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.llm.inputs import Capabilities
from app.llm.types import (
    LlmError,
    ProviderEmbedRequest,
    ProviderEmbedResponse,
    ProviderRequest,
    ProviderResponse,
)

Script = Callable[[ProviderRequest], ProviderResponse | LlmError | dict[str, Any] | str]


@dataclass
class FakeProvider:
    """Answers with `script(request)`: a dict (sent as JSON), raw text, a full
    ProviderResponse, or an LlmError to raise."""

    script: Script
    name: str = "fake"
    capabilities: Capabilities = field(
        default_factory=lambda: Capabilities(reads_pdf=True, max_images=5)
    )
    requests: list[ProviderRequest] = field(default_factory=list)
    embed_requests: list[ProviderEmbedRequest] = field(default_factory=list)
    embed_error: LlmError | None = None

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        answer = self.script(request)
        if isinstance(answer, LlmError):
            raise answer
        if isinstance(answer, ProviderResponse):
            return answer
        text = answer if isinstance(answer, str) else json.dumps(answer)
        return ProviderResponse(text=text, model="fake-model", input_tokens=1000, output_tokens=50)

    async def embed(self, request: ProviderEmbedRequest) -> ProviderEmbedResponse:
        self.embed_requests.append(request)
        if self.embed_error is not None:
            raise self.embed_error
        vectors = [fake_embedding(text, request.dimensions) for text in request.texts]
        return ProviderEmbedResponse(vectors=vectors, model="fake-embedding", input_tokens=10)


def fake_embedding(text: str, dimensions: int) -> list[float]:
    """A hashed bag of words, normalised: texts that share words are close, so tests of
    semantic search behave like the real thing without a network."""
    vector = [0.0] * dimensions
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        vector[int(hashlib.sha256(word.encode()).hexdigest(), 16) % dimensions] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]
