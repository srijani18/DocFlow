"""When a validated document may skip review (F6 AC6, AC7)."""

from decimal import Decimal
from typing import Any

from app.validation.agent import AgentResult

AUTO_APPROVE_CONFIDENCE = Decimal("0.90")  # spec D2


def corrected_confidence(confidence: dict[str, Any], result: AgentResult) -> dict[str, Any]:
    """The model's scores, with each corrected field scored by the agent's reread (AC3)."""
    return {
        **confidence,
        **{fix.path: Decimal(str(fix.confidence)) for fix in result.fixes},
    }


def can_auto_approve(result: AgentResult, confidence: dict[str, Any]) -> bool:
    """No errors or warnings, every field at least 0.90 sure, and not a possible duplicate.
    A duplicate is a warning, but it's excluded explicitly, so a change of severity can't
    let one through."""
    if any(issue.severity in {"error", "warning"} for issue in result.issues):
        return False
    if any(issue.check == "duplicate" for issue in result.issues):
        return False
    scores = [Decimal(str(score)) for score in confidence.values()]
    return bool(scores) and min(scores) >= AUTO_APPROVE_CONFIDENCE
