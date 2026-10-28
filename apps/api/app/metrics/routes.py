"""Metrics endpoint (F13 plan §1)."""

from fastapi import APIRouter

from app.auth.dependencies import WorkspaceScopeDep
from app.core.db_session import DbSession
from app.core.errors import problem_responses
from app.metrics import service
from app.metrics.schemas import Period, WorkspaceMetrics
from app.storage.dependencies import ClockDep

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["metrics"])


@router.get("/metrics", responses=problem_responses(401, 404, 422, 503))
async def get_workspace_metrics(
    *, scope: WorkspaceScopeDep, session: DbSession, clock: ClockDep, period: Period = "30d"
) -> WorkspaceMetrics:
    """The workspace's headline metrics, volume, AI provider reliability and queue (AC1-AC4)."""
    return await service.workspace_metrics(session, scope, period, clock.now())
