"""Workspaces' own AI keys (F15 plan §1). Reading is for members; changing is for admins."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status

from app.aikeys import service
from app.aikeys.crypto import KeyBox
from app.aikeys.models import WorkspaceAiKey
from app.aikeys.schemas import AiKeySave, AiKeyStatus, Provider
from app.auth.dependencies import AdminScopeDep, WorkspaceScopeDep, rate_limit
from app.core.db_session import DbSession
from app.core.errors import problem_responses
from app.events.dependencies import EventsDep, JobWakerDep
from app.idempotency.routing import Idempotent, IdempotentRoute
from app.storage.dependencies import ClockDep

router = APIRouter(
    route_class=IdempotentRoute, prefix="/v1/workspaces/{workspace_id}/ai-keys", tags=["ai-keys"]
)


def get_keybox(request: Request) -> KeyBox | None:
    keybox: KeyBox | None = request.app.state.keybox
    return keybox


def get_key_checker(request: Request, clock: ClockDep) -> service.KeyChecker:
    return service.KeyChecker(
        http=request.app.state.http,
        gemini_base_url=request.app.state.settings.gemini_base_url,
        clock=clock,
    )


KeyBoxDep = Annotated[KeyBox | None, Depends(get_keybox)]
KeyCheckerDep = Annotated[service.KeyChecker, Depends(get_key_checker)]


def _status(provider: Provider, row: WorkspaceAiKey | None) -> AiKeyStatus:
    if row is None:
        return AiKeyStatus(
            provider=provider,
            connected=False,
            last4=None,
            status=None,
            checked_at=None,
            updated_at=None,
        )
    return AiKeyStatus(
        provider=provider,
        connected=True,
        last4=row.last4,
        status=row.status,
        checked_at=row.checked_at,
        updated_at=row.updated_at,
    )


@router.get("", responses=problem_responses(401, 404, 503))
async def list_ai_keys(scope: WorkspaceScopeDep, session: DbSession) -> list[AiKeyStatus]:
    """Every provider, connected or not (AC3). Never includes the keys (AC4)."""
    rows = await service.list_statuses(session, scope)
    return [_status(provider, rows.get(provider)) for provider in Provider]


@router.put(
    "/{provider}",
    responses=problem_responses(401, 403, 404, 422, 429, 503),
    dependencies=[Depends(rate_limit("ai"))],  # checks the key with the provider
)
async def save_ai_key(
    provider: str,
    body: AiKeySave,
    *,
    scope: AdminScopeDep,
    session: DbSession,
    keybox: KeyBoxDep,
    checker: KeyCheckerDep,
    background: BackgroundTasks,
    events: EventsDep,
    wake_worker: JobWakerDep,
    idempotency: Idempotent,
) -> AiKeyStatus:
    """Check the key with its provider, then store it encrypted (AC1, AC8)."""
    row, requeued = await service.save_key(
        session, scope, keybox=keybox, checker=checker, provider=provider, api_key=body.api_key
    )
    if requeued:
        background.add_task(wake_worker)
        for event in requeued:
            background.add_task(events.publish, event)
    return _status(Provider(row.provider), row)


@router.delete(
    "/{provider}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=problem_responses(401, 403, 404, 503),
)
async def delete_ai_key(
    provider: str, scope: AdminScopeDep, session: DbSession, idempotency: Idempotent
) -> Response:
    await service.delete_key(session, scope, provider)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{provider}/test",
    responses=problem_responses(401, 403, 404, 429, 503),
    dependencies=[Depends(rate_limit("ai"))],
)
async def test_ai_key(
    provider: str,
    *,
    scope: AdminScopeDep,
    session: DbSession,
    keybox: KeyBoxDep,
    checker: KeyCheckerDep,
    idempotency: Idempotent,
) -> AiKeyStatus:
    """Check the stored key again (AC5)."""
    row = await service.test_key(session, scope, keybox=keybox, checker=checker, provider=provider)
    return _status(Provider(row.provider), row)
