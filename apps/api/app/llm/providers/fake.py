"""Scripted provider for tests and CI (ADR-0003): no network, no key."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.llm.types import LlmError, ProviderRequest, ProviderResponse

Script = Callable[[ProviderRequest], ProviderResponse | LlmError | dict[str, Any] | str]


@dataclass
class FakeProvider:
    """Answers with `script(request)`: a dict (sent as JSON), raw text, a full
    ProviderResponse, or an LlmError to raise."""

    script: Script
    name: str = "fake"
    requests: list[ProviderRequest] = field(default_factory=list)

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        answer = self.script(request)
        if isinstance(answer, LlmError):
            raise answer
        if isinstance(answer, ProviderResponse):
            return answer
        text = answer if isinstance(answer, str) else json.dumps(answer)
        return ProviderResponse(text=text, model="fake-model", input_tokens=1000, output_tokens=50)
