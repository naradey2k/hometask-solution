"""CLI for the evaluation framework.

Usage:
    python -m eval.cli run [OPTIONS]
    python -m eval.cli rescore --traces PATH
    python -m eval.cli viewer --report PATH
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console

from eval.config import EvalConfig
from eval.loader import load_suite
from eval.models import RunReport
from eval.reporter import compute_diff, print_diff, print_report
from eval.viewer import generate_viewer

console = Console()


@click.group()
def cli():
    """Deep Research Lite — Evaluation Framework."""
    pass


@cli.command()
@click.option("--suite", default=None, help="Path to test suite directory of YAML/JSON (default: eval/suite)")
@click.option("--case", default=None, help="Run a single case by ID")
@click.option("--concurrency", default=3, help="Max concurrent agent calls")
@click.option("--repeats", default=1, help="Number of repeats per case (for flakiness)")
@click.option("--diff-against", default=None, help="Path to previous run report JSON for diff")
@click.option("--model", default=None, help="Override agent model")
@click.option("--judge-model", default=None, help="Override judge model")
def run(suite, case, concurrency, repeats, diff_against, model, judge_model):
    """Run the evaluation suite."""
    config = EvalConfig(concurrency=concurrency, repeats=repeats)
    if model:
        config.agent_model = model
    if judge_model:
        config.judge_model = judge_model

    # Load suite
    suite_path = suite or config.suite_dir
    cases = load_suite(suite_path)

    if case:
        cases = [c for c in cases if c.id == case]
        if not cases:
            console.print(f"[red]Case {case!r} not found in suite.[/]")
            sys.exit(1)

    console.print(f"\n[bold blue]Running {len(cases)} cases × {repeats} repeat(s), concurrency={concurrency}[/]\n")

    # Run
    from eval.runner import run_suite
    report = asyncio.run(run_suite(cases, config))

    # Print report
    print_report(report)

    # Generate viewer
    viewer_path = config.viewer_dir / f"{report.run_id}.html"
    generate_viewer(report, viewer_path)
    console.print(f"\n[dim]Trace viewer → {viewer_path}[/]")
    console.print(f"[dim]Report JSON  → {config.reports_dir / f'{report.run_id}.json'}[/]")

    # Diff if requested
    if diff_against:
        old_path = Path(diff_against)
        if old_path.exists():
            old_report = RunReport.load(old_path)
            diff = compute_diff(old_report, report)
            print_diff(diff)

            # Save diff
            diff_path = config.reports_dir / f"diff_{report.run_id}.json"
            with diff_path.open("w") as f:
                json.dump(diff.to_dict(), f, indent=2)
            console.print(f"[dim]Diff JSON    → {diff_path}[/]")
        else:
            console.print(f"[yellow]Diff target not found: {old_path}[/]")

    # Exit code: non-zero if any failures
    if report.total_failed > 0:
        sys.exit(1)


@cli.command()
@click.option("--traces", required=True, help="Path to directory of trace JSON files")
@click.option("--suite", default=None, help="Path to test suite YAML")
@click.option("--diff-against", default=None, help="Path to previous run report JSON for diff")
def rescore(traces, suite, diff_against):
    """Re-score cached traces without re-running the agent."""
    from eval.scorer import rescore_from_trace
    from eval.runner import build_report

    config = EvalConfig()
    suite_path = suite or config.suite_dir
    cases = load_suite(suite_path)
    case_lookup = {c.id: c for c in cases}

    traces_dir = Path(traces)
    if not traces_dir.exists():
        console.print(f"[red]Traces directory not found: {traces_dir}[/]")
        sys.exit(1)

    # Find trace files (recursively)
    trace_files = sorted(traces_dir.rglob("*.json"))
    if not trace_files:
        console.print(f"[yellow]No trace files found in {traces_dir}[/]")
        sys.exit(1)

    console.print(f"\n[bold blue]Re-scoring {len(trace_files)} trace(s)[/]\n")

    results = []
    all_results = {}
    for tf in trace_files:
        # Try to match trace to a case by filename (case_id_r0.json)
        stem = tf.stem
        case_id = stem.rsplit("_r", 1)[0] if "_r" in stem else stem

        case = case_lookup.get(case_id)
        if case is None:
            console.print(f"  [yellow]Skipping {tf.name}: no matching case '{case_id}'[/]")
            continue

        # Determine repeat index
        repeat_idx = 0
        if "_r" in stem:
            try:
                repeat_idx = int(stem.rsplit("_r", 1)[1])
            except ValueError:
                pass

        result = rescore_from_trace(case, str(tf), config, repeat_idx)
        results.append(result)
        
        if case_id not in all_results:
            all_results[case_id] = []
        all_results[case_id].append(result)

    if not results:
        console.print("[red]No valid traces successfully rescored.[/]")
        sys.exit(1)

    # Reconstruct repeats context
    max_repeats = max((r.repeat_index for r in results), default=0) + 1
    
    # Build report aggregate
    run_id = f"rescore_{int(time.time())}"
    timestamp = datetime.now(timezone.utc).isoformat()
    # Assume model is the one from first trace, or config fallback
    model = results[0].trace.get("model", config.agent_model) if results else config.agent_model
    
    report = build_report(
        cases=cases, 
        all_results=all_results, 
        run_id=run_id, 
        model=model, 
        timestamp=timestamp, 
        repeats=max_repeats
    )

    print_report(report)
    
    if diff_against:
        old_path = Path(diff_against)
        if old_path.exists():
            old_report = RunReport.load(old_path)
            diff = compute_diff(old_report, report)
            print_diff(diff)
        else:
            console.print(f"[yellow]Diff target not found: {old_path}[/]")

    if report.total_failed > 0:
        sys.exit(1)


@cli.command()
@click.option("--report", required=True, help="Path to run report JSON")
@click.option("--output", default=None, help="Output HTML path")
def viewer(report, output):
    """Generate an HTML trace viewer from a report."""
    report_path = Path(report)
    if not report_path.exists():
        console.print(f"[red]Report not found: {report_path}[/]")
        sys.exit(1)

    with report_path.open() as f:
        report_data = json.load(f)

    # Reconstruct a RunReport to pass to the viewer
    # For the viewer we can pass the raw dict since generate_viewer accepts RunReport
    # We need to create a minimal RunReport
    from eval.models import CaseSummary, TestResult, MetricResult, MetricStatus

    case_summaries = []
    for cs_data in report_data.get("case_summaries", []):
        test_results = []
        for r_data in cs_data.get("results", []):
            metric_results = []
            for m_data in r_data.get("metric_results", []):
                metric_results.append(MetricResult(
                    metric_name=m_data.get("metric_name", ""),
                    status=MetricStatus(m_data.get("status", "skip")),
                    score=m_data.get("score"),
                    rationale=m_data.get("rationale", ""),
                    details=m_data.get("details", {}),
                ))
            test_results.append(TestResult(
                case_id=r_data.get("case_id", ""),
                repeat_index=r_data.get("repeat_index", 0),
                passed=r_data.get("passed", False),
                metric_results=metric_results,
                failure_reasons=r_data.get("failure_reasons", []),
                trace_path=r_data.get("trace_path", ""),
                trace=r_data.get("trace", {}),
                wall_time_ms=r_data.get("wall_time_ms", 0),
                cost_usd=r_data.get("cost_usd", 0.0),
                total_tool_calls=r_data.get("total_tool_calls", 0),
                error=r_data.get("error"),
            ))
        case_summaries.append(CaseSummary(
            case_id=cs_data.get("case_id", ""),
            case_name=cs_data.get("case_name", ""),
            total_repeats=cs_data.get("total_repeats", 1),
            passed_count=cs_data.get("passed_count", 0),
            results=test_results,
            mean_wall_time_ms=cs_data.get("mean_wall_time_ms", 0),
            mean_cost_usd=cs_data.get("mean_cost_usd", 0),
            mean_tool_calls=cs_data.get("mean_tool_calls", 0),
        ))

    report_obj = RunReport(
        run_id=report_data.get("run_id", ""),
        timestamp=report_data.get("timestamp", ""),
        model=report_data.get("model", ""),
        total_cases=report_data.get("total_cases", 0),
        total_passed=report_data.get("total_passed", 0),
        total_failed=report_data.get("total_failed", 0),
        pass_rate=report_data.get("pass_rate", 0),
        total_cost_usd=report_data.get("total_cost_usd", 0),
        p50_latency_ms=report_data.get("p50_latency_ms", 0),
        p95_latency_ms=report_data.get("p95_latency_ms", 0),
        mean_tool_calls=report_data.get("mean_tool_calls", 0),
        case_summaries=case_summaries,
        repeats=report_data.get("repeats", 1),
        flaky_cases=report_data.get("flaky_cases", []),
    )

    config = EvalConfig()
    out_path = Path(output) if output else config.viewer_dir / f"{report_obj.run_id}.html"
    generate_viewer(report_obj, out_path)
    console.print(f"[green]Viewer generated → {out_path}[/]")


if __name__ == "__main__":
    cli()
