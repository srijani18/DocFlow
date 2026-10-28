"""Builds the long-lived services shared by the API and the worker (ADR-0002).

Both `create_app` (ROLE=api|all) and the standalone worker process (ROLE=worker) use this,
so the two roles can't be wired differently.
"""

from dataclasses import dataclass
from datetime import timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.aikeys.crypto import KeyBox
from app.aikeys.service import WorkspaceCredentials
from app.core.clock import SystemClock
from app.core.config import Settings
from app.core.db import create_engine, create_sessionmaker
from app.events.broker import EventBroker
from app.llm.gateway import Credentials, Gateway
from app.llm.providers import openai_compat
from app.llm.providers.gemini import GeminiProvider
from app.llm.recording import CallTracer, DbCallRecorder
from app.llm.routing import parse_route
from app.llm.tracing import LangfuseTracer
from app.pipeline.runner import Pipeline
from app.pipeline.steps.classify import ClassifyStep
from app.pipeline.steps.extract import ExtractStep
from app.pipeline.steps.validate import ValidateStep
from app.search.indexer import EmbedRunner
from app.storage.supabase import SupabaseStorage
from app.worker.loop import Worker
from app.worker.maintenance import Maintenance


@dataclass
class Services:
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    # One HTTP client for outbound calls (JWKS, storage, LLMs).
    http: httpx.AsyncClient
    storage: SupabaseStorage
    events: EventBroker
    keybox: KeyBox | None
    worker: Worker | None
    gateway: Gateway
    tracer: LangfuseTracer | None = None

    async def aclose(self) -> None:
        if self.tracer is not None:
            await self.tracer.aclose()  # send the last traces while the client is open
        await self.http.aclose()
        await self.engine.dispose()


def build_services(settings: Settings) -> Services:
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    http = httpx.AsyncClient()
    storage = SupabaseStorage(
        supabase_url=settings.supabase_url,
        secret_key=settings.supabase_secret_key,
        bucket=settings.supabase_storage_bucket,
        http=http,
        clock=SystemClock(),
    )
    events = EventBroker()
    keybox = KeyBox.from_setting(settings.byok_master_keys) if settings.byok_master_keys else None
    # The API embeds search queries (F8); the worker runs the pipeline and embeds documents.
    credentials = WorkspaceCredentials(sessionmaker=sessionmaker, keybox=keybox)
    tracer = LangfuseTracer.from_settings(settings, http)
    gateway = build_gateway(
        settings, sessionmaker=sessionmaker, http=http, credentials=credentials, tracer=tracer
    )
    worker = None
    if settings.role.runs_worker:
        pipeline = Pipeline(
            sessionmaker=sessionmaker,
            storage=storage,
            publish=events.publish,
            classify=ClassifyStep(gateway, prompt_version=settings.llm_classify_prompt),
            extract=ExtractStep(gateway, prompt_version=settings.llm_extract_prompt),
            validate=ValidateStep(
                gateway, prompt_version=settings.llm_validate_prompt, clock=SystemClock()
            ),
        )
        worker = Worker(
            sessionmaker=sessionmaker,
            pipeline=pipeline,
            events=events,
            embedder=EmbedRunner(gateway, sessionmaker=sessionmaker),
            maintenance=Maintenance(sessionmaker=sessionmaker, storage=storage),
        )
    return Services(engine, sessionmaker, http, storage, events, keybox, worker, gateway, tracer)


def build_gateway(
    settings: Settings,
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    http: httpx.AsyncClient,
    credentials: Credentials,
    tracer: CallTracer | None = None,
) -> Gateway:
    gemini = GeminiProvider(
        http=http,
        base_url=settings.gemini_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    groq = openai_compat.groq(http, timeout_seconds=settings.llm_timeout_seconds)
    openrouter = openai_compat.openrouter(http, timeout_seconds=settings.llm_timeout_seconds)
    return Gateway(
        sessionmaker=sessionmaker,
        providers={provider.name: provider for provider in (gemini, groq, openrouter)},
        routes={
            "classify": parse_route(settings.llm_route_classify),
            "extract": parse_route(settings.llm_route_extract),
            # Rereading uses the extraction route (F6 D4).
            "validate": parse_route(settings.llm_route_extract),
            "embed": parse_route(settings.llm_route_embed),
        },
        credentials=credentials,
        recorder=DbCallRecorder(sessionmaker, tracer=tracer),
        cache_ttl=timedelta(days=settings.llm_cache_ttl_days),
    )
