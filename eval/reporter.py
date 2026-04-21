"""Reporter — console output, JSON reports, and diff between runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from eval.models import CaseDiff, CaseSummary, RunDiff, RunReport


console = Console()


# ---------------------------------------------------------------------------
# Console Report
# ---------------------------------------------------------------------------


def print_report(report: RunReport) -> None:
    """Print a rich console report."""
    # Header
    console.print()
    console.print(
        Panel(
            f"[bold]Eval Run: {report.run_id}[/bold]\n"
            f"Model: {report.model} | Cases: {report.total_cases} | "
            f"Repeats: {report.repeats}\n"
            f"Time: {report.timestamp}",
            title="Deep Research Lite — Evaluation Report",
            border_style="blue",
        )
    )

    # Summary table
    summary = Table(title="Aggregate Summary", show_header=True)
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", style="white")

    pass_style = "green" if report.pass_rate >= 0.8 else "yellow" if report.pass_rate >= 0.5 else "red"
    summary.add_row("Pass Rate", f"[{pass_style}]{report.total_passed}/{report.total_cases} ({report.pass_rate:.1%})[/]")
    summary.add_row("Total Cost", f"${report.total_cost_usd:.4f}")
    summary.add_row("p50 Latency", f"{report.p50_latency_ms:.0f}ms")
    summary.add_row("p95 Latency", f"{report.p95_latency_ms:.0f}ms")
    summary.add_row("Mean Tool Calls", f"{report.mean_tool_calls:.1f}")

    if report.flaky_cases:
        summary.add_row("Flaky Cases", f"[yellow]{', '.join(report.flaky_cases)}[/]")

    console.print(summary)
    console.print()

    # Per-case table
    cases_table = Table(title="Per-Case Results", show_header=True)
    cases_table.add_column("Case", style="white", min_width=30)
    cases_table.add_column("Category", style="dim")
    cases_table.add_column("Result", justify="center")
    cases_table.add_column("Cost", justify="right")
    cases_table.add_column("Latency", justify="right")
    cases_table.add_column("Tools", justify="right")
    cases_table.add_column("Details", style="dim", max_width=50)

    for cs in report.case_summaries:
        if report.repeats > 1:
            if cs.is_flaky:
                result = f"[yellow]FLAKY {cs.passed_count}/{cs.total_repeats}[/]"
            elif cs.passed_count == cs.total_repeats:
                result = f"[green]PASS {cs.passed_count}/{cs.total_repeats}[/]"
            else:
                result = f"[red]FAIL {cs.passed_count}/{cs.total_repeats}[/]"
        else:
            result = "[green]PASS[/]" if cs.passed_count > 0 else "[red]FAIL[/]"

        # Get failure reasons from first failing result
        details = ""
        for r in cs.results:
            if not r.passed and r.failure_reasons:
                details = r.failure_reasons[0][:50]
                break

        cases_table.add_row(
            cs.case_name,
            cs.results[0].trace.get("category", "") if cs.results else "",
            result,
            f"${cs.mean_cost_usd:.4f}",
            f"{cs.mean_wall_time_ms:.0f}ms",
            f"{cs.mean_tool_calls:.1f}",
            details,
        )

    console.print(cases_table)

    # Print detailed failures
    failures = [cs for cs in report.case_summaries if cs.passed_count < cs.total_repeats]
    if failures:
        console.print()
        console.print("[bold red]Failures:[/]")
        for cs in failures:
            for r in cs.results:
                if not r.passed:
                    console.print(f"\n  [red]✗[/] [bold]{cs.case_name}[/] (repeat {r.repeat_index})")
                    for reason in r.failure_reasons:
                        console.print(f"    → {reason}")
                    break  # show only first failure per case


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


def compute_diff(old_report: dict[str, Any], new_report: RunReport) -> RunDiff:
    """Compute diff between an old report (loaded from JSON) and a new RunReport."""
    old_cases = {cs["case_id"]: cs for cs in old_report.get("case_summaries", [])}
    new_cases = {cs.case_id: cs for cs in new_report.case_summaries}

    regressions = []
    improvements = []
    unchanged = []

    for case_id in set(list(old_cases.keys()) + list(new_cases.keys())):
        old = old_cases.get(case_id)
        new = new_cases.get(case_id)

        if old is None or new is None:
            continue

        old_passed = old["passed_count"] == old["total_repeats"]
        new_passed = new.passed_count == new.total_repeats
        old_pr = old.get("pass_rate", 0)
        new_pr = new.pass_rate

        diff = CaseDiff(
            case_id=case_id,
            was_passing=old_passed,
            now_passing=new_passed,
            is_regression=old_passed and not new_passed,
            is_improvement=not old_passed and new_passed,
            old_pass_rate=old_pr,
            new_pass_rate=new_pr,
            latency_delta_ms=new.mean_wall_time_ms - old.get("mean_wall_time_ms", 0),
            cost_delta_usd=new.mean_cost_usd - old.get("mean_cost_usd", 0),
        )

        if diff.is_regression:
            regressions.append(diff)
        elif diff.is_improvement:
            improvements.append(diff)
        else:
            unchanged.append(diff)

    return RunDiff(
        old_run_id=old_report.get("run_id", "?"),
        new_run_id=new_report.run_id,
        old_pass_rate=old_report.get("pass_rate", 0),
        new_pass_rate=new_report.pass_rate,
        regressions=regressions,
        improvements=improvements,
        unchanged=unchanged,
        total_cost_delta=new_report.total_cost_usd - old_report.get("total_cost_usd", 0),
    )


def print_diff(diff: RunDiff) -> None:
    """Print a rich diff report."""
    console.print()
    title_style = "red bold" if diff.has_regressions else "green bold"
    console.print(
        Panel(
            f"[{title_style}]Diff: {diff.old_run_id} → {diff.new_run_id}[/]\n"
            f"Pass rate: {diff.old_pass_rate:.1%} → {diff.new_pass_rate:.1%}\n"
            f"Cost delta: ${diff.total_cost_delta:+.4f}",
            title="Run Comparison",
            border_style="red" if diff.has_regressions else "green",
        )
    )

    if diff.regressions:
        console.print("\n[bold red]⚠ REGRESSIONS:[/]")
        for r in diff.regressions:
            console.print(
                f"  [red]✗[/] {r.case_id}: "
                f"pass_rate {r.old_pass_rate:.1%} → {r.new_pass_rate:.1%}"
            )

    if diff.improvements:
        console.print("\n[bold green]✓ IMPROVEMENTS:[/]")
        for i in diff.improvements:
            console.print(
                f"  [green]✓[/] {i.case_id}: "
                f"pass_rate {i.old_pass_rate:.1%} → {i.new_pass_rate:.1%}"
            )

    if not diff.regressions and not diff.improvements:
        console.print("\n[dim]No changes in pass/fail status.[/]")
