import io
import uuid
from pathlib import Path

import pytest
from PIL import Image

from app.llm.circuit import CircuitBreaker
from app.llm.inputs import Capabilities, adapt_parts, pdf_to_images
from app.llm.routing import RouteEntry, parse_route
from app.llm.types import FilePart, PermanentLlmError, TextPart

SAMPLE_PDF = (
    Path(__file__).resolve().parents[5] / "evals" / "samples" / "synthetic-invoice-001.pdf"
).read_bytes()
KEY = (uuid.uuid4(), "groq", "llama")


def test_route_parsing() -> None:
    route = parse_route(
        "gemini:gemini-flash-lite-latest, groq:meta-llama/llama-4-scout-17b-16e-instruct,"
        "openrouter:openrouter/free:extra"
    )

    assert route == (
        RouteEntry("gemini", "gemini-flash-lite-latest"),
        RouteEntry("groq", "meta-llama/llama-4-scout-17b-16e-instruct"),
        RouteEntry("openrouter", "openrouter/free:extra"),
    )


@pytest.mark.parametrize("value", ["", "gemini", "gemini:", "openai:gpt", " , "])
def test_bad_routes_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="route"):
        parse_route(value)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_ac4_opens_after_three_transient_failures() -> None:
    clock = Clock()
    breaker = CircuitBreaker(clock=clock)

    for _ in range(2):
        breaker.failure(KEY)
        assert breaker.allow(KEY)
    breaker.failure(KEY)

    assert not breaker.allow(KEY)
    clock.now = 59
    assert not breaker.allow(KEY)
    assert breaker.seconds_until_retry(KEY) == pytest.approx(1)


def test_ac4_half_open_trial_closes_or_reopens() -> None:
    clock = Clock()
    breaker = CircuitBreaker(clock=clock)
    for _ in range(3):
        breaker.failure(KEY)

    clock.now = 61
    assert breaker.allow(KEY)  # the one trial
    assert not breaker.allow(KEY)  # no second request while the trial runs
    breaker.failure(KEY)  # trial failed: open again
    assert not breaker.allow(KEY)

    clock.now = 122
    assert breaker.allow(KEY)
    breaker.success(KEY)
    assert breaker.allow(KEY)
    assert breaker.allow(KEY)


def test_ac4_success_resets_the_count() -> None:
    breaker = CircuitBreaker(clock=Clock())
    breaker.failure(KEY)
    breaker.failure(KEY)
    breaker.success(KEY)
    breaker.failure(KEY)

    assert breaker.allow(KEY)


def test_breakers_are_per_workspace_provider_and_model() -> None:
    breaker = CircuitBreaker(clock=Clock())
    for _ in range(3):
        breaker.failure(KEY)

    assert breaker.allow((uuid.uuid4(), "groq", "llama"))
    assert breaker.allow((KEY[0], "groq", "other-model"))


def test_ac5_pdf_rendered_to_at_most_three_pngs() -> None:
    images = pdf_to_images(SAMPLE_PDF)

    assert 1 <= len(images) <= 3
    assert all(part.mime_type == "image/png" for part in images)
    rendered = Image.open(io.BytesIO(images[0].data))
    assert rendered.width > 1000  # A4 at 150 DPI is about 1240 px wide


def test_ac5_pdf_kept_for_providers_that_read_pdfs() -> None:
    parts: list[TextPart | FilePart] = [
        TextPart("Document type: invoice"),
        FilePart("application/pdf", SAMPLE_PDF),
    ]

    adapted, mode = adapt_parts(parts, Capabilities(reads_pdf=True, max_images=0))

    assert adapted == parts
    assert mode == "pdf"


def test_ac5_images_sent_unchanged_and_pdfs_converted() -> None:
    png = FilePart("image/png", b"\x89PNG...")
    as_images, mode_images = adapt_parts(
        [FilePart("application/pdf", SAMPLE_PDF)], Capabilities(reads_pdf=False, max_images=5)
    )
    as_is, mode_image = adapt_parts([png], Capabilities(reads_pdf=False, max_images=5))

    assert mode_images == "images"
    assert all(part.mime_type == "image/png" for part in as_images)  # type: ignore[union-attr]
    assert (as_is, mode_image) == ([png], "image")


def test_unreadable_pdf_is_permanent_for_that_provider() -> None:
    with pytest.raises(PermanentLlmError):
        pdf_to_images(b"%PDF-1.7 not really a pdf")
