"""The only way to call an LLM (constitution §5.1, ADR-0003).

For each task there is an ordered route of provider/model pairs (F10). A request goes:

    cache ──hit──▶ done
      │ miss
    for each route entry the workspace has a key for (F15):
        circuit open? ──▶ skip
        adapt the file (PDF → page images if the provider can't read PDFs)
        call ──ok and valid──▶ cache, done
             ──transient / invalid / rejected input──▶ next entry
    nothing worked ──▶ raise the most retryable error

Every attempt, skip and cache hit is logged to `llm_calls` (constitution §5.2).
"""

import json
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import timedelta
from decimal import Decimal
from typing import Any, Protocol, cast

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.llm import cache
from app.llm.circuit import CircuitBreaker
from app.llm.inputs import adapt_parts
from app.llm.pricing import estimate_cost
from app.llm.providers.base import Embedder, Provider
from app.llm.recording import CallRecord, CallRecorder, DbCallRecorder
from app.llm.routing import RouteEntry
from app.llm.types import (
    CredentialRejectedError,
    EmbedRequest,
    EmbedResult,
    InvalidOutputError,
    LlmError,
    LlmRequest,
    LlmResult,
    NoCredentialsError,
    PermanentLlmError,
    ProviderEmbedRequest,
    ProviderRequest,
    ProviderResponse,
    Task,
    TransientLlmError,
)
from app.schemas_registry import validation_errors

log = get_logger(__name__)

# A schema id from schemas/, or a function returning the problems with an answer.
Validator = str | Callable[[dict[str, Any]], list[str]]
DEFAULT_CACHE_TTL = timedelta(days=30)


class Credentials(Protocol):
    """Where a workspace's own provider keys come from (F15)."""

    async def keys_for(self, workspace_id: uuid.UUID) -> Mapping[str, str]: ...

    async def mark_rejected(self, workspace_id: uuid.UUID, provider: str) -> None: ...


class Gateway:
    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession] | None,
        providers: Mapping[str, Provider],
        routes: Mapping[Task, Sequence[RouteEntry]],
        credentials: Credentials,
        breaker: CircuitBreaker | None = None,
        cache_ttl: timedelta = DEFAULT_CACHE_TTL,
        recorder: CallRecorder | None = None,
    ) -> None:
        """Without a sessionmaker there's no cache, and calls go to `recorder` (evals)."""
        if recorder is None:
            if sessionmaker is None:
                raise ValueError("a gateway without a database needs a recorder")
            recorder = DbCallRecorder(sessionmaker)
        self._sessionmaker = sessionmaker
        self._recorder = recorder
        self._providers = providers
        self._routes = routes
        self._credentials = credentials
        self._breaker = breaker or CircuitBreaker()
        self._cache_ttl = cache_ttl

    async def generate(self, request: LlmRequest, *, validate_with: Validator) -> LlmResult:
        """Schema-valid JSON from the first route entry that manages it.

        `validate_with` is the schema id in `schemas/` the answer must satisfy, or a function
        for checks a single schema can't express (F5's extraction envelope). Raises
        NoCredentialsError, TransientLlmError, InvalidOutputError, CredentialRejectedError or
        PermanentLlmError.
        """
        workspace_id = request.context.workspace_id
        keys = await self._credentials.keys_for(workspace_id)
        route = list(self._routes[request.task])
        usable = [
            (position, entry) for position, entry in enumerate(route) if entry.provider in keys
        ]
        if not usable:
            raise NoCredentialsError(f"no key for any of {', '.join(map(str, route))}")

        key = (
            cache.cache_key(request, route)
            if request.use_cache and self._sessionmaker is not None
            else None
        )
        if key is not None:
            hit = await self._from_cache(request, key, validate_with)
            if hit is not None:
                return hit

        errors: list[LlmError] = []
        for position, entry in usable:
            breaker_key = (workspace_id, entry.provider, entry.model)
            if not self._breaker.allow(breaker_key):
                await self._record(
                    request, entry, position, None, time.monotonic(), outcome="skipped"
                )
                errors.append(
                    TransientLlmError(
                        f"{entry} is resting after repeated failures",
                        retry_after_seconds=self._breaker.seconds_until_retry(breaker_key),
                    )
                )
                continue
            result = await self._attempt(
                request,
                entry=entry,
                position=position,
                api_key=keys[entry.provider],
                validate_with=validate_with,
                breaker_key=breaker_key,
                errors=errors,
            )
            if result is not None:
                if key is not None:
                    await self._store(request, key, entry, result)
                return result
        raise _final_error(errors)

    async def embed(self, request: EmbedRequest) -> EmbedResult:
        """Vectors for `request.texts` from the first embedding provider in the route that
        has a key and answers (F8 AC7). Same keys, breaker, logging and cache as generate."""
        workspace_id = request.context.workspace_id
        keys = await self._credentials.keys_for(workspace_id)
        route = list(self._routes[request.task])
        usable = [
            (position, entry)
            for position, entry in enumerate(route)
            if entry.provider in keys and hasattr(self._providers[entry.provider], "embed")
        ]
        if not usable:
            raise NoCredentialsError(f"no key for any of {', '.join(map(str, route))}")
        key = (
            cache.embed_key(request, route)
            if request.use_cache and self._sessionmaker is not None
            else None
        )
        if key is not None and (hit := await self._embeddings_from_cache(request, key)):
            return hit

        errors: list[LlmError] = []
        for position, entry in usable:
            breaker_key = (workspace_id, entry.provider, entry.model)
            started = time.monotonic()
            if not self._breaker.allow(breaker_key):
                await self._record(request, entry, position, None, started, outcome="skipped")
                errors.append(TransientLlmError(f"{entry} is resting after repeated failures"))
                continue
            embedder = cast(Embedder, self._providers[entry.provider])
            try:
                response = await embedder.embed(
                    ProviderEmbedRequest(
                        model=entry.model,
                        texts=request.texts,
                        purpose=request.purpose,
                        dimensions=request.dimensions,
                        api_key=keys[entry.provider],
                    )
                )
                if len(response.vectors) != len(request.texts) or any(
                    len(vector) != request.dimensions for vector in response.vectors
                ):
                    raise InvalidOutputError("embeddings don't match the texts or dimensions")
            except LlmError as exc:
                await self._record(
                    request, entry, position, None, started, outcome=_outcome(exc), error=exc
                )
                await self._after_failure(request, exc, breaker_key)
                errors.append(exc)
                continue
            self._breaker.success(breaker_key)
            logged = ProviderResponse(
                text="", model=response.model, input_tokens=response.input_tokens, output_tokens=0
            )
            call_id = await self._record(request, entry, position, logged, started, outcome="ok")
            result = EmbedResult(vectors=response.vectors, model=response.model, call_id=call_id)
            if key is not None:
                await self._store_raw(
                    request,
                    key,
                    entry,
                    model=response.model,
                    raw_json=json.dumps(result.vectors),
                    call_id=call_id,
                )
            return result
        raise _final_error(errors)

    async def _after_failure(
        self,
        request: LlmRequest | EmbedRequest,
        exc: LlmError,
        breaker_key: tuple[uuid.UUID, str, str],
    ) -> None:
        if isinstance(exc, TransientLlmError):
            self._breaker.failure(breaker_key)
        else:
            self._breaker.release(breaker_key)
        if isinstance(exc, CredentialRejectedError):
            await self._credentials.mark_rejected(request.context.workspace_id, exc.provider)

    async def _embeddings_from_cache(self, request: EmbedRequest, key: str) -> EmbedResult | None:
        started = time.monotonic()
        assert self._sessionmaker is not None  # noqa: S101  # only called when caching
        async with self._sessionmaker() as session:
            entry = await cache.lookup(
                session, key, request.context.workspace_id, ttl=self._cache_ttl
            )
        if entry is None:
            return None
        vectors = json.loads(entry.raw_json)
        logged = ProviderResponse(text="", model=entry.model, input_tokens=0, output_tokens=0)
        call_id = await self._record(
            request, _entry(entry.provider, entry.model), 0, logged, started, outcome="cache_hit"
        )
        return EmbedResult(vectors=vectors, model=entry.model, call_id=call_id)

    async def _attempt(  # one attempt needs all of this context
        self,
        request: LlmRequest,
        *,
        entry: RouteEntry,
        position: int,
        api_key: str,
        validate_with: Validator,
        breaker_key: tuple[uuid.UUID, str, str],
        errors: list[LlmError],
    ) -> LlmResult | None:
        provider = self._providers[entry.provider]
        started = time.monotonic()
        input_mode = None
        try:
            parts, input_mode = adapt_parts(request.parts, provider.capabilities)
            response = await provider.generate(
                ProviderRequest(
                    model=entry.model,
                    instructions=request.prompt.text,
                    parts=parts,
                    response_schema=request.response_schema,
                    api_key=api_key,
                )
            )
        except LlmError as exc:
            await self._record(
                request,
                entry,
                position,
                None,
                started,
                outcome="error",
                error=exc,
                input_mode=input_mode,
            )
            await self._after_failure(request, exc, breaker_key)
            errors.append(exc)
            return None
        try:
            data = self._parse_and_validate(response, validate_with)
        except InvalidOutputError as exc:
            await self._record(
                request,
                entry,
                position,
                response,
                started,
                outcome="invalid_output",
                error=exc,
                input_mode=input_mode,
            )
            self._breaker.release(breaker_key)
            errors.append(exc)
            return None
        self._breaker.success(breaker_key)
        call_id = await self._record(
            request, entry, position, response, started, outcome="ok", input_mode=input_mode
        )
        return LlmResult(
            data=data,
            raw_json=response.text,
            call_id=call_id,
            model=response.model,
            prompt_version=request.prompt.version,
        )

    async def _from_cache(
        self, request: LlmRequest, key: str, validate_with: Validator
    ) -> LlmResult | None:
        started = time.monotonic()
        assert self._sessionmaker is not None  # noqa: S101  # only called when caching
        async with self._sessionmaker() as session:
            entry = await cache.lookup(
                session, key, request.context.workspace_id, ttl=self._cache_ttl
            )
        if entry is None:
            return None
        response = ProviderResponse(
            text=entry.raw_json, model=entry.model, input_tokens=0, output_tokens=0
        )
        try:
            data = self._parse_and_validate(response, validate_with)
        except InvalidOutputError:
            return None  # e.g. the schema changed since: ask a provider again
        call_id = await self._record(
            request, _entry(entry.provider, entry.model), 0, response, started, outcome="cache_hit"
        )
        return LlmResult(
            data=data,
            raw_json=entry.raw_json,
            call_id=call_id,
            model=entry.model,
            prompt_version=request.prompt.version,
        )

    async def _store(
        self, request: LlmRequest, key: str, entry: RouteEntry, result: LlmResult
    ) -> None:
        await self._store_raw(
            request,
            key,
            entry,
            model=result.model,
            raw_json=result.raw_json,
            call_id=result.call_id,
        )

    async def _store_raw(  # a cache row has these columns
        self,
        request: LlmRequest | EmbedRequest,
        key: str,
        entry: RouteEntry,
        *,
        model: str,
        raw_json: str,
        call_id: uuid.UUID,
    ) -> None:
        assert self._sessionmaker is not None  # noqa: S101  # only called when caching
        async with self._sessionmaker() as session, session.begin():
            await cache.store(
                session,
                key=key,
                workspace_id=request.context.workspace_id,
                task=request.task,
                provider=entry.provider,
                model=model,
                raw_json=raw_json,
                source_call_id=call_id,
                ttl=self._cache_ttl,
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

    async def _record(  # one log row has many columns
        self,
        request: LlmRequest | EmbedRequest,
        entry: RouteEntry,
        position: int,
        response: ProviderResponse | None,
        started: float,
        *,
        outcome: str,
        error: Exception | None = None,
        input_mode: str | None = None,
    ) -> uuid.UUID:
        latency_ms = round((time.monotonic() - started) * 1000)
        model = response.model if response else entry.model
        input_tokens = response.input_tokens if response else None
        output_tokens = response.output_tokens if response else None
        cost = (
            Decimal(0)
            if outcome == "cache_hit"
            else estimate_cost(
                entry.provider, model, input_tokens=input_tokens, output_tokens=output_tokens
            )
        )
        ctx = request.context
        call_id = await self._recorder.record(
            CallRecord(
                workspace_id=ctx.workspace_id,
                document_id=ctx.document_id,
                job_id=ctx.job_id,
                task=request.task,
                provider=entry.provider,
                model=model,
                prompt_version=request.prompt.version,
                attempt=ctx.attempt,
                outcome=outcome,
                error_type=type(error).__name__ if error else None,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                latency_ms=latency_ms,
                route_position=position,
                fallback=position > 0,
                input_mode=input_mode,
            )
        )
        log.info(
            "llm_call",
            task=request.task,
            provider=entry.provider,
            model=model,
            outcome=outcome,
            route_position=position,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            error=str(error) if error else None,
        )
        return call_id


def _entry(provider: str, model: str) -> RouteEntry:
    return RouteEntry(provider, model)


def _final_error(errors: list[LlmError]) -> LlmError:
    """The error that tells the queue the most: retry if anything was temporary (F10 AC2),
    give up only if every entry refused the input (AC3)."""
    transient = [e for e in errors if isinstance(e, TransientLlmError)]
    if transient:
        waits = [e.retry_after_seconds for e in transient if e.retry_after_seconds is not None]
        return TransientLlmError(
            "; ".join(str(e) for e in transient), retry_after_seconds=max(waits) if waits else None
        )
    invalid = [e for e in errors if isinstance(e, InvalidOutputError)]
    if invalid:
        return invalid[-1]
    rejected = [e for e in errors if isinstance(e, CredentialRejectedError)]
    if rejected and len(rejected) == len(errors):
        return rejected[-1]
    permanent = [e for e in errors if isinstance(e, PermanentLlmError)]
    return permanent[-1] if permanent else TransientLlmError("no provider answered")


def _outcome(exc: LlmError) -> str:
    return "invalid_output" if isinstance(exc, InvalidOutputError) else "error"
