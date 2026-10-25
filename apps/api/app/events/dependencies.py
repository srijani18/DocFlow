"""FastAPI wiring for live events and waking the worker. Tests override these."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from app.events.broker import EventBroker


def get_events(request: Request) -> EventBroker:
    events: EventBroker = request.app.state.events
    return events


def _no_worker() -> None:
    """ROLE=api: a separate worker process finds the job on its next sweep."""


def get_job_waker(request: Request) -> Callable[[], None]:
    worker = request.app.state.worker
    return worker.wake if worker is not None else _no_worker


EventsDep = Annotated[EventBroker, Depends(get_events)]
JobWakerDep = Annotated[Callable[[], None], Depends(get_job_waker)]
