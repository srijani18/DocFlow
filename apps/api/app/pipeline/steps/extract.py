"""Extraction step (F5): the document type's fields, with a confidence per field."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.documents import service as documents
from app.documents.models import DocumentStatus as DocStatus
from app.extractions import envelope
from app.extractions import service as extractions
from app.jobs.errors import PermanentError
from app.llm.gateway import Gateway
from app.llm.prompts import load_prompt
from app.llm.types import CallContext, FilePart, LlmError, LlmRequest, TextPart
from app.pipeline.runner import StepContext
from app.pipeline.steps.llm_errors import to_step_error


class ExtractStep:
    def __init__(self, gateway: Gateway, *, prompt_version: str) -> None:
        self._gateway = gateway
        self._prompt = load_prompt(prompt_version)

    async def __call__(self, ctx: StepContext) -> None:
        async with ctx.sessionmaker() as session:
            document = await documents.get_document(session, ctx.scope, str(ctx.document_id))
            existing = await extractions.find_model_extraction(
                session, ctx.scope, ctx.document_id, document.processing_generation
            )
        if existing is not None:
            # Stored by an earlier attempt of this run: no new call, no new version (AC5).
            await ctx.advance(from_status=DocStatus.EXTRACTING, to=DocStatus.VALIDATING)
            return
        doc_type = document.doc_type
        schema_id = envelope.SCHEMA_BY_DOC_TYPE.get(doc_type or "")
        if doc_type is None or schema_id is None:
            raise PermanentError("Unsupported document type", detail=f"doc_type={doc_type}")

        def check(answer: dict[str, Any]) -> list[str]:
            return envelope.validate(schema_id, answer)

        try:
            result = await self._gateway.generate(
                LlmRequest(
                    task="extract",
                    prompt=self._prompt,
                    parts=[
                        TextPart(f"Document type: {doc_type}"),
                        FilePart(mime_type=ctx.content_type, data=ctx.file),
                    ],
                    response_schema=envelope.response_schema(schema_id),
                    context=CallContext(
                        workspace_id=ctx.scope.workspace_id,
                        document_id=ctx.document_id,
                        job_id=ctx.job_id,
                        attempt=ctx.attempt,
                    ),
                ),
                validate_with=check,
            )
        except LlmError as exc:
            raise to_step_error(exc, invalid_reason="Couldn't extract valid data") from exc

        generation = document.processing_generation

        async def store(session: AsyncSession) -> None:
            await extractions.record_model_extraction(
                session,
                ctx.scope,
                document_id=ctx.document_id,
                doc_type=doc_type,
                schema_id=schema_id,
                data=result.data["data"],
                confidence=envelope.confidence_map(result.data),
                prompt_version=result.prompt_version,
                llm_call_id=result.call_id,
                generation=generation,
            )

        await ctx.advance(from_status=DocStatus.EXTRACTING, to=DocStatus.VALIDATING, write=store)
