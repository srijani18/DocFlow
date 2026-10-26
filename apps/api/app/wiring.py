"""Builds the long-lived services shared by the API and the worker (ADR-0002).

Both `create_app` (ROLE=api|all) and the standalone worker process (ROLE=worker) use this,
so the two roles can't be wired differently.
"""

from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.aikeys.crypto import KeyBox
from app.aikeys.service import WorkspaceCredentials
from app.core.clock import SystemClock
from app.core.config import Settings
from app.core.db import create_engine, create_sessionmaker
from app.events.broker import EventBroker
from app.llm.gateway import Credentials, Gateway, Route
from app.llm.providers.gemini import GeminiProvider
from app.pipeline.runner import Pipeline
from app.pipeline.steps.classify import ClassifyStep
from app.pipeline.steps.extract import ExtractStep
from app.storage.supabase import SupabaseStorage
from app.worker.loop import Worker


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

    async def aclose(self) -> None:
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
    worker = None
    if settings.role.runs_worker:
        credentials = WorkspaceCredentials(sessionmaker=sessionmaker, keybox=keybox)
        gateway = build_gateway(
            settings, sessionmaker=sessionmaker, http=http, credentials=credentials
        )
        pipeline = Pipeline(
            sessionmaker=sessionmaker,
            storage=storage,
            publish=events.publish,
            classify=ClassifyStep(gateway, prompt_version=settings.llm_classify_prompt),
            extract=ExtractStep(gateway, prompt_version=settings.llm_extract_prompt),
        )
        worker = Worker(sessionmaker=sessionmaker, pipeline=pipeline, events=events)
    return Services(engine, sessionmaker, http, storage, events, keybox, worker)


def build_gateway(
    settings: Settings,
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    http: httpx.AsyncClient,
    credentials: Credentials,
) -> Gateway:
    gemini = GeminiProvider(
        http=http,
        base_url=settings.gemini_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    return Gateway(
        sessionmaker=sessionmaker,
        providers={gemini.name: gemini},
        credentials=credentials,
        routes={
            "classify": Route(gemini.name, settings.llm_classify_model),
            "extract": Route(gemini.name, settings.llm_extract_model),
        },
    )
