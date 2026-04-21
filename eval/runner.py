"""Runner — parallel test execution with concurrency cap, retries, and flakiness.

Wraps the agent's run_agent() in a thread pool (it's synchronous / blocking)
and manages trace persistence.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eval.config import EvalConfig
from eval.loader import load_suite
from eval.models import CaseSummary, RunReport, TestCase, TestResult
from eval.scorer import score_case


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

_RETRYABLE_ERRORS = (
    "rate_limit",
    "overloaded",
    "429",
    "500",
    "502",
    "503",
    "529",
    "timeout",
    "connection",
)


def _is_retryable(error_str: str) -> bool:
    """Check if an error string indicates a transient, retryable failure."""
    lower = error_str.lower()
    return any(tok in lower for tok in _RETRYABLE_ERRORS)


def _run_agent_with_retry(
    question: str, model: str, config: EvalConfig
) -> dict[str, Any]:
    """Run the agent with exponential backoff on transient errors."""
    # Import here to avoid loading agent/corpus until needed
    from agent import run_agent

    last_error = None
    for attempt in range(config.max_retries + 1):
        try:
            result = run_agent(question, model=model)
            trace = result.to_dict()

            # Check if the agent itself reported a transient error
            if trace.get("stopped_reason") == "error" and trace.get("error"):
                if _is_retryable(trace["error"]) and attempt < config.max_retries:
                    delay = min(
                        config.retry_base_delay * (2**attempt),
                        config.retry_max_delay,
                    )
                    time.sleep(delay)
                    last_error = trace["error"]
                    continue

            return trace

        except Exception as e:
            error_str = f"{type(e).__name__}: {e}"
            if _is_retryable(error_str) and attempt < config.max_retries:
                delay = min(
                    config.retry_base_delay * (2**attempt),
                    config.retry_max_delay,
                )
                time.sleep(delay)
                last_error = error_str
                continue
            raise

    # All retries exhausted
    return {
        "run_id": str(uuid.uuid4()),
        "question": question,
        "model": model,
        "messages": [],
        "final_answer": None,
        "citations": [],
        "stopped_reason": "error",
        "total_tokens": {"input": 0, "output": 0},
        "cost_usd": 0.0,
        "wall_time_ms": 0,
        "error": f"All {config.max_retries} retries exhausted. Last error: {last_error}",
    }


# ---------------------------------------------------------------------------
# Single case execution
# ---------------------------------------------------------------------------


def _run_single(
    case: TestCase,
    repeat_index: int,
    config: EvalConfig,
    run_id: str,
) -> TestResult:
    """Execute a single case once: run agent → save trace → score."""
    # Run the agent
    try:
        trace = _run_agent_with_retry(case.input, config.agent_model, config)
    except Exception as e:
        trace = {
            "run_id": str(uuid.uuid4()),
            "question": case.input,
            "model": config.agent_model,
            "messages": [],
            "final_answer": None,
            "citations": [],
            "stopped_reason": "error",
            "total_tokens": {"input": 0, "output": 0},
            "cost_usd": 0.0,
            "wall_time_ms": 0,
            "error": f"{type(e).__name__}: {e}",
        }

    # Save trace to disk
    trace_dir = config.traces_dir / run_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_filename = f"{case.id}_r{repeat_index}.json"
    trace_path = trace_dir / trace_filename
    with trace_path.open("w") as f:
        json.dump(trace, f, indent=2, default=str)

    # Score the trace
    result = score_case(
        case=case,
        trace=trace,
        config=config,
        repeat_index=repeat_index,
        trace_path=str(trace_path),
    )

    return result


# ---------------------------------------------------------------------------
# Async runner with concurrency cap
# ---------------------------------------------------------------------------


async def run_suite(
    cases: list[TestCase],
    config: EvalConfig,
) -> RunReport:
    """Run all cases with concurrency cap and optional repeats.

    Uses a ThreadPoolExecutor since the agent is synchronous.
    An asyncio.Semaphore controls max concurrent agent calls.
    """
    config.ensure_dirs()
    run_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now(timezone.utc).isoformat()
    semaphore = asyncio.Semaphore(config.concurrency)
    executor = ThreadPoolExecutor(max_workers=config.concurrency)
    loop = asyncio.get_event_loop()

    all_results: dict[str, list[TestResult]] = {c.id: [] for c in cases}

    async def run_one(case: TestCase, repeat: int) -> TestResult:
        async with semaphore:
            result = await loop.run_in_executor(
                executor, _run_single, case, repeat, config, run_id
            )
            return result

    # Build tasks
    tasks = []
    for case in cases:
        for repeat in range(config.repeats):
            tasks.append((case, repeat))

    # Execute all
    coros = [run_one(case, repeat) for case, repeat in tasks]
    results = await asyncio.gather(*coros, return_exceptions=True)

    # Collect results
    for (case, repeat), result in zip(tasks, results):
        if isinstance(result, Exception):
            error_result = TestResult(
                case_id=case.id,
                repeat_index=repeat,
                passed=False,
                failure_reasons=[f"Exception: {result}"],
                error=str(result),
            )
            all_results[case.id].append(error_result)
        else:
            all_results[case.id].append(result)

    executor.shutdown(wait=False)

    report = build_report(cases, all_results, run_id, config.agent_model, timestamp, config.repeats)

    # Save report
    report_path = config.reports_dir / f"{run_id}.json"
    report.save(report_path)

    return report


def build_report(
    cases: list[TestCase],
    all_results: dict[str, list[TestResult]],
    run_id: str,
    model: str,
    timestamp: str,
    repeats: int,
) -> RunReport:
    """Build a RunReport from a dictionary of TestResults."""
    case_summaries = []
    case_lookup = {c.id: c for c in cases}
    for case_id, case_results in all_results.items():
        case = case_lookup.get(case_id)
        if not case:
            continue
            
        passed_count = sum(1 for r in case_results if r.passed)
        total_repeats = len(case_results)

        # Compute means
        mean_latency = (
            sum(r.wall_time_ms for r in case_results) / total_repeats
            if total_repeats > 0 else 0
        )
        mean_cost = (
            sum(r.cost_usd for r in case_results) / total_repeats
            if total_repeats > 0 else 0
        )
        mean_tools = (
            sum(r.total_tool_calls for r in case_results) / total_repeats
            if total_repeats > 0 else 0
        )
        
        variance = {}
        if total_repeats > 1:
            variance = {
                "wall_time_ms": {
                    "min": min(r.wall_time_ms for r in case_results),
                    "max": max(r.wall_time_ms for r in case_results),
                },
                "cost_usd": {
                    "min": min(r.cost_usd for r in case_results),
                    "max": max(r.cost_usd for r in case_results),
                },
                "tool_calls": {
                    "min": min(r.total_tool_calls for r in case_results),
                    "max": max(r.total_tool_calls for r in case_results),
                }
            }

        summary = CaseSummary(
            case_id=case_id,
            case_name=case.name,
            total_repeats=total_repeats,
            passed_count=passed_count,
            results=case_results,
            mean_wall_time_ms=mean_latency,
            mean_cost_usd=mean_cost,
            mean_tool_calls=mean_tools,
            metric_variance=variance,
        )
        case_summaries.append(summary)

    # Aggregate stats
    all_flat = [r for results in all_results.values() for r in results]
    total_passed = sum(1 for s in case_summaries if s.passed_count == s.total_repeats)
    total_failed = sum(1 for s in case_summaries if s.passed_count == 0)
    total_cases = len(cases)
    pass_rate = total_passed / total_cases if total_cases > 0 else 0.0

    latencies = sorted([r.wall_time_ms for r in all_flat if r.wall_time_ms > 0])
    p50 = latencies[len(latencies) // 2] if latencies else 0
    p95_idx = int(len(latencies) * 0.95)
    p95 = latencies[min(p95_idx, len(latencies) - 1)] if latencies else 0

    total_cost = sum(r.cost_usd for r in all_flat)
    mean_tool_calls = (
        sum(r.total_tool_calls for r in all_flat) / len(all_flat) if all_flat else 0
    )

    flaky = [s.case_id for s in case_summaries if s.is_flaky]

    return RunReport(
        run_id=run_id,
        timestamp=timestamp,
        model=model,
        total_cases=total_cases,
        total_passed=total_passed,
        total_failed=total_failed,
        pass_rate=pass_rate,
        total_cost_usd=total_cost,
        p50_latency_ms=float(p50),
        p95_latency_ms=float(p95),
        mean_tool_calls=mean_tool_calls,
        case_summaries=case_summaries,
        repeats=repeats,
        flaky_cases=flaky,
    )
