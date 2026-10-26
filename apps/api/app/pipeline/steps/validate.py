"""Validation step (F6): checks, the rereading agent, then auto-approval or review."""

from datetime import timedelta

from app.core.clock import Clock
from app.documents import service as documents
from app.documents.models import DocumentStatus as DocStatus
from app.extractions import envelope
from app.extractions import service as extractions
from app.jobs.errors import PermanentError
from app.llm.gateway import Gateway
from app.llm.prompts import load_prompt
from app.llm.types import CallContext, FilePart
from app.pipeline.runner import StepContext
from app.validation import service as validation
from app.validation.agent import run_agent
from app.validation.approval import can_auto_approve, corrected_confidence
from app.validation.rereader import GatewayRereader

# The latest calendar date anywhere (UTC+14), so a document dated "today" in any time zone
# isn't reported as being in the future.
LATEST_OFFSET = timedelta(hours=14)


class ValidateStep:
    def __init__(self, gateway: Gateway, *, prompt_version: str, clock: Clock) -> None:
        self._gateway = gateway
        self._prompt = load_prompt(prompt_version)
        self._clock = clock

    async def __call__(self, ctx: StepContext) -> None:
        async with ctx.sessionmaker() as session:
            document = await documents.get_document(session, ctx.scope, str(ctx.document_id))
            if document.current_extraction_id is None:
                raise PermanentError("Nothing to validate", detail="no current extraction")
            current = await extractions.get_current(session, ctx.scope, str(ctx.document_id))
            data = await extractions.get_exact_data(session, ctx.scope, current.id)
        doc_type = document.doc_type or ""
        if doc_type not in envelope.SCHEMA_BY_DOC_TYPE:
            raise PermanentError("Unsupported document type", detail=f"doc_type={doc_type}")

        rereader = GatewayRereader(
            self._gateway,
            self._prompt,
            file=FilePart(mime_type=ctx.content_type, data=ctx.file),
            context=CallContext(
                workspace_id=ctx.scope.workspace_id,
                document_id=ctx.document_id,
                job_id=ctx.job_id,
                attempt=ctx.attempt,
            ),
        )
        result = await run_agent(
            doc_type,
            current.schema_id,
            data,
            today=(self._clock.now() + LATEST_OFFSET).date(),
            rereader=rereader,
            lookups=validation.lookups_for(
                ctx.sessionmaker, ctx.scope, document_id=ctx.document_id, doc_type=doc_type
            ),
        )
        confidence = (
            corrected_confidence(current.confidence, result)
            if result.changed
            else current.confidence
        )
        approve = can_auto_approve(result, confidence)

        # The new version, its issues and the status change commit together, so a re-run of
        # this step (crash, duplicate job) either finds VALIDATING with nothing stored, or
        # finds the document already moved on and does nothing (AC9).
        async with ctx.sessionmaker() as session, session.begin():
            checked = current.id
            if result.changed:
                fixed = await extractions.record_agent_fix(
                    session,
                    ctx.scope,
                    document_id=ctx.document_id,
                    doc_type=doc_type,
                    schema_id=current.schema_id,
                    data=result.data,
                    confidence=confidence,
                    prompt_version=self._prompt.version,
                    llm_call_id=rereader.call_ids[-1] if rereader.call_ids else None,
                    generation=document.processing_generation,
                )
                checked = fixed.id
            await validation.record_issues(
                session,
                ctx.scope,
                document_id=ctx.document_id,
                extraction_id=checked,
                remaining=result.issues,
                fixed=result.resolved if result.changed else [],
            )
            if approve:
                event = await documents.approve(
                    session,
                    ctx.scope,
                    ctx.document_id,
                    expected=[DocStatus.VALIDATING],
                    by_user_id=None,
                    job_id=ctx.job_id,
                    detail="approved by the validation agent",
                )
            else:
                _, event = await documents.transition(
                    session,
                    ctx.scope,
                    ctx.document_id,
                    expected=[DocStatus.VALIDATING],
                    to=DocStatus.NEEDS_REVIEW,
                    job_id=ctx.job_id,
                )
        ctx.publish(event)
