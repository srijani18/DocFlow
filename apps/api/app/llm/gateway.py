"""The only way to call an LLM (constitution §5.1, ADR-0003).

Phase 1 slice: one route per task, a timeout, schema validation and a log row for every
attempt. F10 adds fallback routes, a circuit breaker and a cache behind the same method.
"""

import json
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.llm.models import LlmCall
from app.llm.pricing import estimate_cost
from app.llm.providers.base import Provider
from app.llm.types import (
    CredentialRejectedError,
    InvalidOutputError,
    LlmError,
    LlmRequest,
    LlmResult,
    NoCredentialsError,
    ProviderRequest,
    ProviderResponse,
    Task,
)
from app.schemas_registry import validation_errors

log = get_logger(__name__)

# A schema id from schemas/, or a function returning the problems with an answer.
Validator = str | Callable[[dict[str, Any]], list[str]]


class Credentials(Protocol):
    """Where a workspace's own provider keys come from (F15)."""

    async def keys_for(self, workspace_id: uuid.UUID) -> Mapping[str, str]: ...

    async def mark_rejected(self, workspace_id: uuid.UUID, provider: str) -> None: ...


@dataclass(frozen=True)
class Route:
    provider: str
    model: str


class Gateway:
    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession],
        providers: Mapping[str, Provider],
        routes: Mapping[Task, Route],
        credentials: Credentials,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._providers = providers
        self._routes = routes
        self._credentials = credentials

    async def generate(self, request: LlmRequest, *, validate_with: Validator) -> LlmResult:
        """Call the task's model and return schema-valid JSON.

        `validate_with` is the schema id in `schemas/` the answer must satisfy, or a function
        for checks a single schema can't express (F5's extraction envelope). Raises
        TransientLlmError, PermanentLlmError or InvalidOutputError; every attempt is logged
        either way (F4 AC4).
        """
        route = self._routes[request.task]
        provider = self._providers[route.provider]
        keys = await self._credentials.keys_for(request.context.workspace_id)
        api_key = keys.get(route.provider)
        if api_key is None:
            raise NoCredentialsError(f"no {route.provider} key connected")
        started = time.monotonic()
        try:
            response = await provider.generate(
                ProviderRequest(
                    model=route.model,
                    instructions=request.prompt.text,
                    parts=request.parts,
                    response_schema=request.response_schema,
                    api_key=api_key,
                )
            )
        except LlmError as exc:
            await self._record(request, route, None, started, outcome="error", error=exc)
            if isinstance(exc, CredentialRejectedError):
                await self._credentials.mark_rejected(request.context.workspace_id, exc.provider)
            raise
        try:
            data = self._parse_and_validate(response, validate_with)
        except InvalidOutputError as exc:
            await self._record(
                request, route, response, started, outcome="invalid_output", error=exc
            )
            raise
        call_id = await self._record(request, route, response, started, outcome="ok")
        return LlmResult(
            data=data,
            raw_json=response.text,
            call_id=call_id,
            model=response.model,
            prompt_version=request.prompt.version,
        )

    @staticmethod
    def _parse_and_validate(response: ProviderResponse, validate_with: Validator) -> dict[str, Any]:
        if response.truncated:
            raise InvalidOutputError("answer was cut off at the output token limit")
        try:
            # Decimals keep money exact (F5 AC8); jsonschema treats them as numbers.
            data = json.loads(response.text, parse_float=Decimal)
        except json.JSONDecodeError as exc:
            raise InvalidOutputError(f"answer is not JSON: {exc.msg}") from exc
        if not isinstance(data, dict):
            raise InvalidOutputError("answer is not a JSON object")
        if isinstance(validate_with, str):
            problems = validation_errors(validate_with, data)
        else:
            problems = validate_with(data)
        if problems:
            raise InvalidOutputError("; ".join(problems[:5]))
        return data

    async def _record(
        self,
        request: LlmRequest,
        route: Route,
        response: ProviderResponse | None,
        started: float,
        *,
        outcome: str,
        error: Exception | None = None,
    ) -> uuid.UUID:
        latency_ms = round((time.monotonic() - started) * 1000)
        model = response.model if response else route.model
        input_tokens = response.input_tokens if response else None
        output_tokens = response.output_tokens if response else None
        ctx = request.context
        # Its own short transaction: a failed attempt is kept even when the step rolls back.
        async with self._sessionmaker() as session, session.begin():
            call_id = (
                await session.execute(
                    insert(LlmCall)
                    .values(
                        workspace_id=ctx.workspace_id,
                        document_id=ctx.document_id,
                        job_id=ctx.job_id,
                        task=request.task,
                        provider=route.provider,
                        model=model,
                        prompt_version=request.prompt.version,
                        attempt=ctx.attempt,
                        outcome=outcome,
                        error_type=type(error).__name__ if error else None,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost_usd=estimate_cost(
                            route.provider,
                            model,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                        ),
                        latency_ms=latency_ms,
                    )
                    .returning(LlmCall.id)
                )
            ).scalar_one()
        log.info(
            "llm_call",
            task=request.task,
            provider=route.provider,
            model=model,
            outcome=outcome,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            error=str(error) if error else None,
        )
        return call_id
