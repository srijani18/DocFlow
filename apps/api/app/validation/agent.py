"""The validation agent (F6 AC3, AC4, spec D1).

Loop: run the deterministic checks; if some failures could be misreadings (arithmetic,
GSTIN checksum), ask the model to reread just those fields; apply its corrections to a
copy; keep the copy only if the checks get better. At most `max_rounds` rereads.
"""

import copy
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from app.schemas_registry import validation_errors
from app.validation.checks import Issue, WorkspaceLookups, all_checks, severity_score


@dataclass(frozen=True)
class Fix:
    path: str
    value: Any
    confidence: float
    reason: str


class Rereader(Protocol):
    async def reread(
        self, *, doc_type: str, issues: list[Issue], data: dict[str, Any]
    ) -> list[Fix]: ...


@dataclass
class AgentResult:
    data: dict[str, Any]
    issues: list[Issue]
    resolved: list[Issue] = field(default_factory=list)
    fixes: list[Fix] = field(default_factory=list)
    rounds: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.fixes)


def get_path(data: Any, path: str) -> Any:
    node = data
    for part in path.split("."):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def set_path(data: Any, path: str, value: Any) -> None:
    *parents, last = path.split(".")
    node = data
    for part in parents:
        node = node[int(part)] if isinstance(node, list) else node[part]
    if isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value


def _apply(
    data: dict[str, Any], fixes: list[Fix], allowed: set[str]
) -> tuple[dict[str, Any], list[Fix]]:
    candidate = copy.deepcopy(data)
    applied = []
    for fix in fixes:
        if fix.path not in allowed:
            continue  # the model may only touch fields named by a failed check
        try:
            if get_path(candidate, fix.path) == fix.value:
                continue
            set_path(candidate, fix.path, fix.value)
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        applied.append(fix)
    return candidate, applied


async def run_agent(  # the loop's whole context
    doc_type: str,
    schema_id: str,
    data: dict[str, Any],
    *,
    today: date,
    rereader: Rereader | None,
    lookups: WorkspaceLookups | None = None,
    max_rounds: int = 2,
) -> AgentResult:
    issues = await all_checks(doc_type, data, today=today, lookups=lookups)
    result = AgentResult(data=data, issues=issues)
    original = list(issues)
    for _ in range(max_rounds):
        fixable = [issue for issue in result.issues if issue.fixable]
        if not fixable or rereader is None:
            break
        result.rounds += 1
        proposals = await rereader.reread(doc_type=doc_type, issues=fixable, data=result.data)
        allowed = {path for issue in fixable for path in issue.paths}
        candidate, applied = _apply(result.data, proposals, allowed)
        if not applied or validation_errors(schema_id, candidate):
            break  # no progress, or the "fix" doesn't fit the schema
        new_issues = await all_checks(doc_type, candidate, today=today, lookups=lookups)
        if severity_score(new_issues) >= severity_score(result.issues):
            break  # a correction must make things better, or it's discarded (AC4)
        result.data, result.issues = candidate, new_issues
        result.fixes.extend(applied)
    remaining = {(i.check, i.paths) for i in result.issues}
    result.resolved = [i for i in original if (i.check, i.paths) not in remaining]
    return result
