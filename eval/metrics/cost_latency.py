"""Cost & latency metric — checks resource usage bounds."""

from __future__ import annotations

from typing import Any

from eval.models import MetricResult, MetricStatus, TestCase
from eval.metrics import Metric, register


# Reasonable defaults; cases can override via tags.
_DEFAULT_MAX_COST_USD = 0.05
_DEFAULT_MAX_LATENCY_MS = 60_000  # 60 seconds


class CostLatencyMetric(Metric):
    """Reports cost and latency, flags outliers."""

    name = "cost_latency"
    description = "Checks cost and latency against thresholds"

    def score(
        self, case: TestCase, trace: dict[str, Any], final_answer: str | None
    ) -> MetricResult:
        cost = trace.get("cost_usd", 0.0)
        latency = trace.get("wall_time_ms", 0)
        tokens = trace.get("total_tokens", {})

        issues = []

        if cost > _DEFAULT_MAX_COST_USD:
            issues.append(
                f"Cost ${cost:.4f} exceeds threshold ${_DEFAULT_MAX_COST_USD:.4f}"
            )

        if latency > _DEFAULT_MAX_LATENCY_MS:
            issues.append(
                f"Latency {latency}ms exceeds threshold {_DEFAULT_MAX_LATENCY_MS}ms"
            )

        details = {
            "cost_usd": cost,
            "wall_time_ms": latency,
            "input_tokens": tokens.get("input", 0),
            "output_tokens": tokens.get("output", 0),
        }

        if issues:
            return MetricResult(
                metric_name=self.name,
                status=MetricStatus.FAIL,
                score=0.0,
                rationale="; ".join(issues),
                details=details,
            )

        return MetricResult(
            metric_name=self.name,
            status=MetricStatus.PASS,
            score=1.0,
            rationale=f"Cost ${cost:.4f}, latency {latency}ms — within bounds",
            details=details,
        )


register(CostLatencyMetric())
