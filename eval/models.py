"""Data models for the evaluation framework.

Defines TestCase, assertions, metric results, and run reports as
pure dataclasses — no framework dependencies.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AssertionType(str, Enum):
    """Types of hard assertions over a trace."""

    TOOL_CALLED = "tool_called"           # tool X was called
    TOOL_NOT_CALLED = "tool_not_called"   # tool X was NOT called
    TOOL_SEQUENCE = "tool_sequence"       # tools were called in this order
    ANSWER_CONTAINS = "answer_contains"   # final answer contains substring
    ANSWER_NOT_CONTAINS = "answer_not_contains"
    ANSWER_REGEX = "answer_regex"         # final answer matches regex
    STOPPED_REASON = "stopped_reason"     # stopped_reason == value
    TOOL_COUNT_LEQ = "tool_count_leq"     # total tool calls ≤ N
    TOOL_COUNT_GEQ = "tool_count_geq"     # total tool calls ≥ N
    CITATIONS_FETCHED = "citations_fetched"  # every citation URL was fetched
    CITATION_CONTAINS = "citation_contains"  # citations list contains URL
    CITATION_NOT_CONTAINS = "citation_not_contains"


class MetricStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------


@dataclass
class HardAssertion:
    """A deterministic, boolean check over the trace."""

    type: AssertionType
    value: Any  # depends on type: str, int, list[str], etc.
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type.value, "value": self.value, "description": self.description}


@dataclass
class SoftAssertion:
    """An LLM-judged assertion with a rubric."""

    metric: str       # e.g. "correctness", "refusal_quality"
    rubric: str       # human-readable rubric for the judge
    pass_threshold: int = 4  # score >= this → pass (on 1-5 scale)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "rubric": self.rubric,
            "pass_threshold": self.pass_threshold,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# Test Case
# ---------------------------------------------------------------------------


@dataclass
class TestCase:
    """A single evaluation case."""

    id: str
    name: str
    input: str                              # user question
    category: str = ""                      # e.g. "happy_path", "adversarial"
    hard_assertions: list[HardAssertion] = field(default_factory=list)
    soft_assertions: list[SoftAssertion] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    notes: str = ""                         # human notes about the case

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "input": self.input,
            "category": self.category,
            "hard_assertions": [a.to_dict() for a in self.hard_assertions],
            "soft_assertions": [a.to_dict() for a in self.soft_assertions],
            "tags": self.tags,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Metric Results
# ---------------------------------------------------------------------------


@dataclass
class MetricResult:
    """Result of scoring a single metric on a single case."""

    metric_name: str
    status: MetricStatus
    score: float | None = None        # 0-5 for LLM judge, 0/1 for hard
    rationale: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "status": self.status.value,
            "score": self.score,
            "rationale": self.rationale,
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# Test Result (per case, per repeat)
# ---------------------------------------------------------------------------


@dataclass
class TestResult:
    """Result of running + scoring a single case once."""

    case_id: str
    repeat_index: int
    passed: bool
    metric_results: list[MetricResult] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)
    trace_path: str = ""
    trace: dict[str, Any] = field(default_factory=dict)
    wall_time_ms: int = 0
    cost_usd: float = 0.0
    total_tool_calls: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "repeat_index": self.repeat_index,
            "passed": self.passed,
            "metric_results": [m.to_dict() for m in self.metric_results],
            "failure_reasons": self.failure_reasons,
            "trace_path": self.trace_path,
            "trace": self.trace,
            "wall_time_ms": self.wall_time_ms,
            "cost_usd": self.cost_usd,
            "total_tool_calls": self.total_tool_calls,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Case Summary (aggregated across repeats)
# ---------------------------------------------------------------------------


@dataclass
class CaseSummary:
    """Aggregated result for a case across N repeats."""

    case_id: str
    case_name: str
    total_repeats: int
    passed_count: int
    results: list[TestResult] = field(default_factory=list)
    mean_wall_time_ms: float = 0.0
    mean_cost_usd: float = 0.0
    mean_tool_calls: float = 0.0
    metric_variance: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def pass_rate(self) -> float:
        return self.passed_count / self.total_repeats if self.total_repeats > 0 else 0.0

    @property
    def is_flaky(self) -> bool:
        return 0 < self.passed_count < self.total_repeats

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "case_name": self.case_name,
            "total_repeats": self.total_repeats,
            "passed_count": self.passed_count,
            "pass_rate": round(self.pass_rate, 3),
            "is_flaky": self.is_flaky,
            "mean_wall_time_ms": round(self.mean_wall_time_ms, 1),
            "mean_cost_usd": round(self.mean_cost_usd, 6),
            "mean_tool_calls": round(self.mean_tool_calls, 2),
            "metric_variance": self.metric_variance,
            "results": [r.to_dict() for r in self.results],
        }


# ---------------------------------------------------------------------------
# Run Report
# ---------------------------------------------------------------------------


@dataclass
class RunReport:
    """Aggregate report for a full evaluation run."""

    run_id: str
    timestamp: str
    model: str
    total_cases: int
    total_passed: int
    total_failed: int
    pass_rate: float
    total_cost_usd: float
    p50_latency_ms: float
    p95_latency_ms: float
    mean_tool_calls: float
    case_summaries: list[CaseSummary] = field(default_factory=list)
    repeats: int = 1
    flaky_cases: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "model": self.model,
            "total_cases": self.total_cases,
            "total_passed": self.total_passed,
            "total_failed": self.total_failed,
            "pass_rate": round(self.pass_rate, 3),
            "total_cost_usd": round(self.total_cost_usd, 6),
            "p50_latency_ms": round(self.p50_latency_ms, 1),
            "p95_latency_ms": round(self.p95_latency_ms, 1),
            "mean_tool_calls": round(self.mean_tool_calls, 2),
            "repeats": self.repeats,
            "flaky_cases": self.flaky_cases,
            "case_summaries": [cs.to_dict() for cs in self.case_summaries],
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

    @classmethod
    def load(cls, path: Path) -> dict[str, Any]:
        """Load a report as a raw dict (for diffing)."""
        with path.open() as f:
            return json.load(f)


# ---------------------------------------------------------------------------
# Diff structures
# ---------------------------------------------------------------------------


@dataclass
class CaseDiff:
    """Diff for a single case between two runs."""

    case_id: str
    was_passing: bool
    now_passing: bool
    is_regression: bool
    is_improvement: bool
    old_pass_rate: float = 0.0
    new_pass_rate: float = 0.0
    latency_delta_ms: float = 0.0
    cost_delta_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunDiff:
    """Diff between two run reports."""

    old_run_id: str
    new_run_id: str
    old_pass_rate: float
    new_pass_rate: float
    regressions: list[CaseDiff] = field(default_factory=list)
    improvements: list[CaseDiff] = field(default_factory=list)
    unchanged: list[CaseDiff] = field(default_factory=list)
    total_cost_delta: float = 0.0

    @property
    def has_regressions(self) -> bool:
        return len(self.regressions) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "old_run_id": self.old_run_id,
            "new_run_id": self.new_run_id,
            "old_pass_rate": round(self.old_pass_rate, 3),
            "new_pass_rate": round(self.new_pass_rate, 3),
            "regressions": [r.to_dict() for r in self.regressions],
            "improvements": [i.to_dict() for i in self.improvements],
            "unchanged": [u.to_dict() for u in self.unchanged],
            "total_cost_delta": round(self.total_cost_delta, 6),
        }
