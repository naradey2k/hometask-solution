"""Tool efficiency metric — detects missing tools, unnecessary calls, duplicates."""

from __future__ import annotations

from typing import Any

from eval.models import MetricResult, MetricStatus, TestCase
from eval.metrics import (
    Metric,
    register,
    extract_tool_names,
    count_tool_calls,
    extract_fetch_urls,
)


class ToolEfficiencyMetric(Metric):
    """Evaluates whether the agent used tools efficiently."""

    name = "tool_efficiency"
    description = "Checks for missing required tools, unnecessary calls, and duplicates"

    def score(
        self, case: TestCase, trace: dict[str, Any], final_answer: str | None
    ) -> MetricResult:
        issues = []
        tool_names = extract_tool_names(trace)
        total = count_tool_calls(trace)

        # Check for duplicate fetch_url calls to the same URL
        fetch_urls = []
        for msg in trace.get("messages", []):
            if msg.get("role") == "assistant":
                for tc in msg.get("tool_calls", []):
                    if tc["name"] == "fetch_url":
                        url = tc.get("args", {}).get("url", "")
                        fetch_urls.append(url)

        unique_fetches = set(fetch_urls)
        if len(fetch_urls) > len(unique_fetches):
            dupes = len(fetch_urls) - len(unique_fetches)
            issues.append(f"Duplicate fetch_url calls: {dupes} redundant fetches")

        # Check for duplicate web_search calls with the same query
        search_queries = []
        for msg in trace.get("messages", []):
            if msg.get("role") == "assistant":
                for tc in msg.get("tool_calls", []):
                    if tc["name"] == "web_search":
                        q = tc.get("args", {}).get("query", "")
                        search_queries.append(q.lower().strip())

        unique_searches = set(search_queries)
        if len(search_queries) > len(unique_searches):
            issues.append(f"Duplicate web_search queries detected")

        # Check: did the agent fetch a page before trying to extract quotes?
        saw_fetch = False
        for name in tool_names:
            if name == "fetch_url":
                saw_fetch = True
            if name == "extract_quotes" and not saw_fetch:
                issues.append("extract_quotes called before any fetch_url")
                break

        # Check: did the agent search before fetching?
        saw_search = False
        for name in tool_names:
            if name == "web_search":
                saw_search = True
            if name == "fetch_url" and not saw_search:
                issues.append("fetch_url called before any web_search")
                break

        if issues:
            return MetricResult(
                metric_name=self.name,
                status=MetricStatus.FAIL,
                score=0.0,
                rationale="; ".join(issues),
                details={"issues": issues, "total_tool_calls": total},
            )

        return MetricResult(
            metric_name=self.name,
            status=MetricStatus.PASS,
            score=1.0,
            rationale=f"Tool usage looks efficient ({total} calls, {len(unique_fetches)} unique fetches)",
            details={"total_tool_calls": total},
        )


register(ToolEfficiencyMetric())
