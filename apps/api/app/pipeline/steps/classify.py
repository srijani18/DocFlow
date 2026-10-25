"""Classification step (F4): invoice, receipt, purchase order or other."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.documents import service as documents
from app.documents.models import DocType
from app.documents.models import DocumentStatus as DocStatus
from app.llm.gateway import Gateway
from app.llm.prompts import load_prompt
from app.llm.types import CallContext, FilePart, LlmError, LlmRequest
from app.pipeline.runner import StepContext
from app.pipeline.steps.llm_errors import to_step_error
from app.schemas_registry import bundle

SCHEMA_ID = "docflow/classification/v1"
OTHER_NOTE = "Not an invoice, receipt or purchase order"


def next_status(doc_type: str) -> DocStatus:
    """`other` skips extraction and waits for a person (F4 AC3)."""
    return DocStatus.NEEDS_REVIEW if doc_type == DocType.OTHER else DocStatus.EXTRACTING


class ClassifyStep:
    def __init__(self, gateway: Gateway, *, prompt_version: str) -> None:
        self._gateway = gateway
        self._prompt = load_prompt(prompt_version)

    async def __call__(self, ctx: StepContext) -> None:
        async with ctx.sessionmaker() as session:
            document = await documents.get_document(session, ctx.scope, str(ctx.document_id))
        if document.doc_type is not None:
            # Already classified in an earlier run: no new AI call (F4 AC7).
            await ctx.advance(from_status=DocStatus.CLASSIFYING, to=next_status(document.doc_type))
            return

        try:
            result = await self._gateway.generate(
                LlmRequest(
                    task="classify",
                    prompt=self._prompt,
                    parts=[FilePart(mime_type=ctx.content_type, data=ctx.file)],
                    response_schema=bundle(SCHEMA_ID),
                    context=CallContext(
                        workspace_id=ctx.scope.workspace_id,
                        document_id=ctx.document_id,
                        job_id=ctx.job_id,
                        attempt=ctx.attempt,
                    ),
                ),
                validate_with=SCHEMA_ID,
            )
        except LlmError as exc:
            raise to_step_error(exc, invalid_reason="Couldn't classify the document") from exc

        doc_type = str(result.data["doc_type"])
        confidence = float(Decimal(str(result.data["confidence"])))

        async def store(session: AsyncSession) -> None:
            await documents.set_classification(
                session, ctx.scope, ctx.document_id, doc_type=doc_type, confidence=confidence
            )

        await ctx.advance(
            from_status=DocStatus.CLASSIFYING,
            to=next_status(doc_type),
            write=store,
            detail=OTHER_NOTE if doc_type == DocType.OTHER else f"{doc_type} ({confidence:.2f})",
        )
