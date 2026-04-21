"""Scorer — orchestrates hard + soft scoring for each case."""

from __future__ import annotations

import json
from typing import Any

from eval.config import EvalConfig
from eval.judge import judge, make_trace_summary
from eval.models import MetricResult, MetricStatus, TestCase, TestResult
from eval.metrics import get_all, count_tool_calls


def score_case(
    case: TestCase,
    trace: dict[str, Any],
    config: EvalConfig,
    repeat_index: int = 0,
    trace_path: str = "",
) -> TestResult:
    """Score a single case against its trace.

    Runs all registered metrics (hard assertions) first, then soft assertions
    (LLM-as-judge). Aggregates into a TestResult.
    """
    final_answer = trace.get("final_answer")
    metric_results: list[MetricResult] = []
    failure_reasons: list[str] = []

    # --- 1. Run all registered metrics (plugin-style hard checks) ---
    for metric in get_all():
        try:
            result = metric.score(case, trace, final_answer)
            metric_results.append(result)
            if result.status == MetricStatus.FAIL:
                failure_reasons.append(f"[{metric.name}] {result.rationale}")
        except Exception as e:
            metric_results.append(
                MetricResult(
                    metric_name=metric.name,
                    status=MetricStatus.ERROR,
                    rationale=f"Metric error: {e}",
                )
            )

    # --- 2. Run soft assertions (LLM-as-judge) ---
    if case.soft_assertions:
        trace_summary = make_trace_summary(trace)
        for assertion in case.soft_assertions:
            try:
                result = judge(
                    assertion=assertion,
                    question=case.input,
                    answer=final_answer or "",
                    trace_summary=trace_summary,
                    model=config.judge_model,
                )
                metric_results.append(result)
                if result.status == MetricStatus.FAIL:
                    failure_reasons.append(
                        f"[judge_{assertion.metric}] score={result.score}, "
                        f"threshold={assertion.pass_threshold}: {result.rationale}"
                    )
            except Exception as e:
                metric_results.append(
                    MetricResult(
                        metric_name=f"judge_{assertion.metric}",
                        status=MetricStatus.ERROR,
                        rationale=f"Judge error: {e}",
                    )
                )

    # --- 3. Aggregate pass/fail ---
    # A case passes if ALL metrics pass (no FAIL status)
    passed = all(
        r.status in (MetricStatus.PASS, MetricStatus.SKIP)
        for r in metric_results
    )

    return TestResult(
        case_id=case.id,
        repeat_index=repeat_index,
        passed=passed,
        metric_results=metric_results,
        failure_reasons=failure_reasons,
        trace_path=trace_path,
        trace=trace,
        wall_time_ms=trace.get("wall_time_ms", 0),
        cost_usd=trace.get("cost_usd", 0.0),
        total_tool_calls=count_tool_calls(trace),
    )


def rescore_from_trace(
    case: TestCase,
    trace_path: str,
    config: EvalConfig,
    repeat_index: int = 0,
) -> TestResult:
    """Re-score a case from a cached trace file without re-running the agent."""
    with open(trace_path) as f:
        trace = json.load(f)

    return score_case(
        case=case,
        trace=trace,
        config=config,
        repeat_index=repeat_index,
        trace_path=trace_path,
    )
