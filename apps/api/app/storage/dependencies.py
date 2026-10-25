"""FastAPI wiring for storage and time. Tests override these with fakes."""

from typing import Annotated

from fastapi import Depends, Request

from app.core.clock import Clock, SystemClock
from app.storage.client import Storage


def get_storage(request: Request) -> Storage:
    storage: Storage = request.app.state.storage
    return storage


def get_clock() -> Clock:
    return SystemClock()


StorageDep = Annotated[Storage, Depends(get_storage)]
ClockDep = Annotated[Clock, Depends(get_clock)]
