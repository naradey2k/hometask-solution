"""Correctness metric — hard assertions + LLM-judge combined."""

from __future__ import annotations

import re
from typing import Any

from eval.models import (
    AssertionType,
    HardAssertion,
    MetricResult,
    MetricStatus,
    TestCase,
)


class CorrectnessMetric:
    """Evaluates answer correctness via hard assertions.

    Soft (LLM-judge) correctness is handled separately via the judge module
    and wired in through the scorer.
    """

    name = "correctness"
    description = "Checks hard correctness constraints on the final answer and trace"

    def score(
        self, case: TestCase, trace: dict[str, Any], final_answer: str | None
    ) -> MetricResult:
        failures = []
        answer = final_answer or ""

        for assertion in case.hard_assertions:
            ok, reason = _check_hard(assertion, trace, answer)
            if not ok:
                failures.append(reason)

        if failures:
            return MetricResult(
                metric_name=self.name,
                status=MetricStatus.FAIL,
                score=0.0,
                rationale="; ".join(failures),
                details={"failures": failures},
            )

        return MetricResult(
            metric_name=self.name,
            status=MetricStatus.PASS,
            score=1.0,
            rationale="All hard assertions passed",
        )


def _check_hard(
    assertion: HardAssertion, trace: dict[str, Any], answer: str
) -> tuple[bool, str]:
    """Run a single hard assertion. Returns (passed, reason)."""
    from eval.metrics import extract_tool_names, count_tool_calls, extract_fetch_urls

    t = assertion.type
    v = assertion.value

    if t == AssertionType.ANSWER_CONTAINS:
        if v.lower() not in answer.lower():
            return False, f"Answer missing substring: {v!r}"
        return True, ""

    if t == AssertionType.ANSWER_NOT_CONTAINS:
        if v.lower() in answer.lower():
            return False, f"Answer unexpectedly contains: {v!r}"
        return True, ""

    if t == AssertionType.ANSWER_REGEX:
        if not re.search(v, answer, re.IGNORECASE):
            return False, f"Answer does not match regex: {v!r}"
        return True, ""

    if t == AssertionType.STOPPED_REASON:
        actual = trace.get("stopped_reason", "")
        if actual != v:
            return False, f"stopped_reason={actual!r}, expected {v!r}"
        return True, ""

    if t == AssertionType.TOOL_CALLED:
        names = extract_tool_names(trace)
        if v not in names:
            return False, f"Tool {v!r} was never called"
        return True, ""

    if t == AssertionType.TOOL_NOT_CALLED:
        names = extract_tool_names(trace)
        if v in names:
            return False, f"Tool {v!r} was called but should not have been"
        return True, ""

    if t == AssertionType.TOOL_SEQUENCE:
        names = extract_tool_names(trace)
        expected = v if isinstance(v, list) else [v]
        # Check subsequence
        it = iter(names)
        for exp in expected:
            if exp not in it:
                return False, f"Expected tool sequence {expected}, got {names}"
        return True, ""

    if t == AssertionType.TOOL_COUNT_LEQ:
        actual = count_tool_calls(trace)
        if actual > int(v):
            return False, f"Tool calls={actual}, expected ≤{v}"
        return True, ""

    if t == AssertionType.TOOL_COUNT_GEQ:
        actual = count_tool_calls(trace)
        if actual < int(v):
            return False, f"Tool calls={actual}, expected ≥{v}"
        return True, ""

    if t == AssertionType.CITATIONS_FETCHED:
        citations = trace.get("citations", [])
        fetched = extract_fetch_urls(trace)
        unfetched = [c for c in citations if c not in fetched]
        if unfetched:
            return False, f"Citations not fetched: {unfetched}"
        return True, ""

    if t == AssertionType.CITATION_CONTAINS:
        citations = trace.get("citations", [])
        if v not in citations:
            return False, f"Citation {v!r} missing from citations list"
        return True, ""

    if t == AssertionType.CITATION_NOT_CONTAINS:
        citations = trace.get("citations", [])
        if v in citations:
            return False, f"Citation {v!r} should not be in citations"
        return True, ""

    return False, f"Unknown assertion type: {t}"


# ---------------------------------------------------------------------------
# Self-register
# ---------------------------------------------------------------------------

from eval.metrics import register  # noqa: E402

register(CorrectnessMetric())
