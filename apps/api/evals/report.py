"""Turns model runs into the JSON record and the Markdown report (F11 AC3 to AC6)."""

import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from evals.runner import DocumentOutcome, ModelRun


@dataclass(frozen=True)
class Summary:
    route: str
    served_models: list[str]
    documents: int
    classification_accuracy: float
    field_accuracy: float
    fields_scored: int
    all_correct_rate: float
    invalid_rate: float
    error_rate: float
    latency_median_ms: float
    latency_p95_ms: float
    cost_per_document_usd: float | None
    by_doc_type: dict[str, float]
    by_source: dict[str, float]
    by_field: dict[str, float]


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _accuracy(outcomes: list[DocumentOutcome]) -> float:
    fields = [f for o in outcomes for f in o.fields]
    return _rate(sum(f.correct for f in fields), len(fields))


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]


def summarise(run: ModelRun) -> Summary:
    outcomes = run.outcomes
    latencies = [float(sum(c.latency_ms for c in o.calls)) for o in outcomes if o.calls]
    costs = [c.cost_usd for o in outcomes for c in o.calls]
    known = [c for c in costs if c is not None]
    by_field: dict[str, list[bool]] = defaultdict(list)
    for outcome in outcomes:
        for result in outcome.fields:
            by_field[result.generic_path].append(result.correct)
    grouped_type: dict[str, list[DocumentOutcome]] = defaultdict(list)
    grouped_source: dict[str, list[DocumentOutcome]] = defaultdict(list)
    for outcome in outcomes:
        grouped_type[outcome.doc_type].append(outcome)
        grouped_source[outcome.source].append(outcome)
    return Summary(
        route=run.route,
        served_models=sorted({c.model for o in outcomes for c in o.calls if c.outcome == "ok"}),
        documents=len(outcomes),
        classification_accuracy=_rate(sum(o.classified_correctly for o in outcomes), len(outcomes)),
        field_accuracy=_accuracy(outcomes),
        fields_scored=sum(len(o.fields) for o in outcomes),
        all_correct_rate=_rate(
            sum(bool(o.fields) and all(f.correct for f in o.fields) for o in outcomes),
            len(outcomes),
        ),
        invalid_rate=_rate(sum(o.invalid for o in outcomes), len(outcomes)),
        error_rate=_rate(
            sum(o.error is not None and not o.invalid for o in outcomes), len(outcomes)
        ),
        latency_median_ms=statistics.median(latencies) if latencies else 0.0,
        latency_p95_ms=_p95(latencies),
        cost_per_document_usd=float(sum(known, Decimal(0)) / len(outcomes))
        if known and outcomes
        else None,
        by_doc_type={k: _accuracy(v) for k, v in sorted(grouped_type.items())},
        by_source={k: _accuracy(v) for k, v in sorted(grouped_source.items())},
        by_field={k: _rate(sum(v), len(v)) for k, v in sorted(by_field.items())},
    )


@dataclass(frozen=True)
class AgentSummary:
    """Before and after the validation agent, for one model (F6 AC10)."""

    route: str
    documents: int
    accuracy_before: float
    accuracy_after: float
    fields_fixed: int  # wrong → right
    fields_broken: int  # right → wrong
    documents_changed: int
    expected_issues: int
    expected_caught: int
    false_alarms: int  # all fields right, yet an issue that wasn't expected
    misread_documents: int  # some field still wrong after the agent
    misreads_flagged: int  # ... and flagged by an unexpected issue
    auto_approved: int
    auto_approved_with_error: int
    calls: int
    cost_usd: float | None


def summarise_agent(run: ModelRun) -> AgentSummary | None:
    pairs = [(o, o.agent) for o in run.outcomes if o.agent is not None]
    if not pairs:
        return None
    fixed = broken = changed = expected = caught = alarms = misread = flagged = 0
    approved = approved_wrong = 0
    for outcome, agent in pairs:
        before = {f.path: f.correct for f in outcome.fields}
        after = {f.path: f.correct for f in agent.fields}
        fixed += sum(after[p] and not before.get(p, False) for p in after)
        broken += sum(before.get(p, False) and not after[p] for p in after)
        changed += agent.fixes > 0
        expected += len(outcome.expected_issues)
        caught += len(set(outcome.expected_issues) & set(agent.issues))
        unexpected = set(agent.issues) - set(outcome.expected_issues)
        all_right = all(after.values())
        alarms += all_right and bool(unexpected)
        misread += not all_right
        flagged += not all_right and bool(unexpected)
        approved += agent.auto_approved
        approved_wrong += agent.auto_approved and not all_right
    costs = [c.cost_usd for c in run.agent_calls if c.cost_usd is not None]
    return AgentSummary(
        route=run.route,
        documents=len(pairs),
        accuracy_before=_accuracy([o for o, _ in pairs]),
        accuracy_after=_rate(
            sum(f.correct for _, a in pairs for f in a.fields),
            sum(len(a.fields) for _, a in pairs),
        ),
        fields_fixed=fixed,
        fields_broken=broken,
        documents_changed=changed,
        expected_issues=expected,
        expected_caught=caught,
        false_alarms=alarms,
        misread_documents=misread,
        misreads_flagged=flagged,
        auto_approved=approved,
        auto_approved_with_error=approved_wrong,
        calls=len(run.agent_calls),
        cost_usd=float(sum(costs, Decimal(0))) if costs else None,
    )


def _agent_json(outcome: DocumentOutcome) -> dict[str, Any] | None:
    if outcome.agent is None:
        return None
    before = {f.path: f.actual for f in outcome.fields}
    return {
        "fixes": outcome.agent.fixes,
        "issues": outcome.agent.issues,
        "expected_issues": outcome.expected_issues,
        "auto_approved": outcome.agent.auto_approved,
        "changed_fields": [
            {"path": f.path, "actual": f.actual, "correct": f.correct}
            for f in outcome.agent.fields
            if f.path in before and f.actual != before[f.path]
        ],
    }


def to_json(meta: dict[str, Any], runs: list[ModelRun]) -> dict[str, Any]:
    agent = [a for a in (summarise_agent(run) for run in runs) if a is not None]
    return {
        **meta,
        "summaries": [asdict(summarise(run)) for run in runs],
        **({"agent_summaries": [asdict(a) for a in agent]} if agent else {}),
        "documents": {
            run.route: [
                {
                    "id": o.id,
                    "source": o.source,
                    "doc_type": o.doc_type,
                    "predicted_type": o.predicted_type,
                    "error": o.error,
                    "invalid": o.invalid,
                    "latency_ms": sum(c.latency_ms for c in o.calls),
                    "fields": [
                        {
                            "path": f.path,
                            "rule": f.rule,
                            "expected": f.expected,
                            "actual": f.actual,
                            "correct": f.correct,
                        }
                        for f in o.fields
                    ],
                    **({"agent": _agent_json(o)} if o.agent is not None else {}),
                }
                for o in run.outcomes
            ]
            for run in runs
        },
    }


SUMMARY_COLUMNS = [
    "Model route",
    "Served as",
    "Classification",
    "Field accuracy",
    "All fields correct",
    "Invalid answers",
    "Errors",
    "Median latency",
    "p95 latency",
    "Cost / document",
]


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def to_markdown(meta: dict[str, Any], runs: list[ModelRun]) -> str:
    summaries = [summarise(run) for run in runs]
    lines = [
        f"# Eval run `{meta['run_id']}`",
        "",
        f"- **Commit:** `{meta['commit']}` · **Dataset:** v{meta['dataset_version']} "
        f"({meta['documents']} documents) · **Prompts:** {', '.join(meta['prompt_versions'])} · "
        f"**Created:** {meta['created_at']}",
        "- Extraction uses the true document type; classification is scored separately. No cache.",
        "",
        "## Summary",
        "",
        _row(SUMMARY_COLUMNS),
        "|" + "---|" * len(SUMMARY_COLUMNS),
    ]
    for s in summaries:
        cost = f"${s.cost_per_document_usd:.4f}" if s.cost_per_document_usd is not None else "n/a"
        lines.append(
            _row(
                [
                    f"`{s.route}`",
                    ", ".join(s.served_models) or "—",
                    _pct(s.classification_accuracy),
                    f"**{_pct(s.field_accuracy)}** ({s.fields_scored} fields)",
                    _pct(s.all_correct_rate),
                    _pct(s.invalid_rate),
                    _pct(s.error_rate),
                    f"{s.latency_median_ms / 1000:.1f} s",
                    f"{s.latency_p95_ms / 1000:.1f} s",
                    cost,
                ]
            )
        )
    groups = sorted({k for s in summaries for k in s.by_doc_type})
    lines += [
        "",
        "## Field accuracy by document type",
        "",
        "| Model route | " + " | ".join(groups) + " |",
        "|---|" + "---|" * len(groups),
    ]
    for s in summaries:
        lines.append(
            f"| `{s.route}` | " + " | ".join(_pct(s.by_doc_type.get(g, 0)) for g in groups) + " |"
        )
    sources = sorted({k for s in summaries for k in s.by_source})
    lines += [
        "",
        "## Field accuracy by source",
        "",
        "| Model route | " + " | ".join(sources) + " |",
        "|---|" + "---|" * len(sources),
    ]
    for s in summaries:
        lines.append(
            f"| `{s.route}` | " + " | ".join(_pct(s.by_source.get(g, 0)) for g in sources) + " |"
        )
    lines += _agent_markdown(runs)
    fields = sorted(
        {k for s in summaries for k in s.by_field},
        key=lambda f: min(s.by_field.get(f, 1.0) for s in summaries),
    )
    lines += [
        "",
        "## Per field (worst first)",
        "",
        "| Field | " + " | ".join(f"`{s.route}`" for s in summaries) + " |",
        "|---|" + "---|" * len(summaries),
    ]
    for name in fields:
        lines.append(
            f"| `{name}` | "
            + " | ".join(_pct(s.by_field[name]) if name in s.by_field else "—" for s in summaries)
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


AGENT_COLUMNS = [
    "Model route",
    "Field accuracy before",
    "After agent",
    "Fixed (wrong→right)",
    "Broken (right→wrong)",
    "Documents corrected",
    "Expected issues caught",
    "Misreads flagged",
    "False alarms",
    "Auto-approved",
    "…with a wrong field",
    "Agent calls",
]


def _agent_markdown(runs: list[ModelRun]) -> list[str]:
    agent = [a for a in (summarise_agent(run) for run in runs) if a is not None]
    if not agent:
        return []
    lines = [
        "",
        "## Validation agent (before / after)",
        "",
        "Checks and rereads on every extraction (F6). *Expected issues* are what the checks "
        "raise on the true data: the deliberately broken invoices, a duplicate pair, and real "
        "inconsistencies on CORD receipts. *Misreads flagged*: documents still wrong after the "
        "agent that got an unexpected issue, so a reviewer looks. *False alarms*: documents "
        "fully right that got one anyway. Duplicates are looked up within the dataset.",
        "",
        _row(AGENT_COLUMNS),
        "|" + "---|" * len(AGENT_COLUMNS),
    ]
    for a in agent:
        lines.append(
            _row(
                [
                    f"`{a.route}`",
                    _pct(a.accuracy_before),
                    f"**{_pct(a.accuracy_after)}**",
                    str(a.fields_fixed),
                    str(a.fields_broken),
                    f"{a.documents_changed} / {a.documents}",
                    f"{a.expected_caught} / {a.expected_issues}",
                    f"{a.misreads_flagged} / {a.misread_documents}",
                    str(a.false_alarms),
                    f"{a.auto_approved} / {a.documents}",
                    str(a.auto_approved_with_error),
                    str(a.calls),
                ]
            )
        )
    return lines
