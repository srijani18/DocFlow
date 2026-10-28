"""A Sentry transport that keeps events in memory instead of sending them (F16)."""

from typing import Any

from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport

TEST_DSN = "https://public@o0.ingest.sentry.io/0"


class CapturingTransport(Transport):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict[str, Any]] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        event = envelope.get_event()
        if event is not None:
            self.events.append(dict(event))
