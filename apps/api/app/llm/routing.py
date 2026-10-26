"""Per-task routes: an ordered list of provider/model pairs (F10 AC1)."""

from dataclasses import dataclass

KNOWN_PROVIDERS = frozenset({"gemini", "groq", "openrouter", "fake"})


@dataclass(frozen=True)
class RouteEntry:
    provider: str
    model: str

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}"


def parse_route(value: str) -> tuple[RouteEntry, ...]:
    """ "gemini:gemini-flash-lite-latest,groq:meta-llama/…" → entries, in order.

    The model part may itself contain colons (OpenRouter's "…:free"), so only the first
    colon separates provider from model.
    """
    entries = []
    for raw in filter(None, (part.strip() for part in value.split(","))):
        provider, sep, model = raw.partition(":")
        if not sep or not model or provider not in KNOWN_PROVIDERS:
            raise ValueError(f"route entries look like provider:model, got {raw!r}")
        entries.append(RouteEntry(provider, model))
    if not entries:
        raise ValueError("a route needs at least one provider:model")
    return tuple(entries)
