"""Metrics plugin system.

Adding a new metric:
  1. Create a new file in eval/metrics/
  2. Subclass Metric
  3. Call register() at module level

The scorer discovers metrics via get_all() — no edits to runner or scorer needed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from eval.models import MetricResult, TestCase


class Metric(ABC):
    """Base class for all evaluation metrics."""

    name: str
    description: str = ""

    @abstractmethod
    def score(
        self, case: TestCase, trace: dict[str, Any], final_answer: str | None
    ) -> MetricResult:
        """Score a single case given its trace.

        Args:
            case: The test case definition.
            trace: The full run trace dict (from agent.RunResult.to_dict()).
            final_answer: The agent's final answer string.

        Returns:
            A MetricResult with status, score, and rationale.
        """
        ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, Metric] = {}


def register(metric: Metric) -> None:
    """Register a metric instance in the global registry."""
    _REGISTRY[metric.name] = metric


def get_all() -> list[Metric]:
    """Return all registered metrics."""
    return list(_REGISTRY.values())


def get(name: str) -> Metric | None:
    """Return a metric by name, or None."""
    return _REGISTRY.get(name)


# ---------------------------------------------------------------------------
# Trace helpers (shared across metrics)
# ---------------------------------------------------------------------------


def extract_tool_calls(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull all tool calls from a trace's messages."""
    calls = []
    for msg in trace.get("messages", []):
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls", []):
                calls.append(tc)
    return calls


def extract_tool_names(trace: dict[str, Any]) -> list[str]:
    """Return ordered list of tool names called."""
    return [tc["name"] for tc in extract_tool_calls(trace)]


def extract_fetch_urls(trace: dict[str, Any]) -> set[str]:
    """Return set of URLs passed to fetch_url."""
    urls = set()
    for tc in extract_tool_calls(trace):
        if tc["name"] == "fetch_url":
            url = tc.get("args", {}).get("url", "")
            if url:
                urls.add(url)
    return urls


def count_tool_calls(trace: dict[str, Any]) -> int:
    """Total tool calls in a trace."""
    return len(extract_tool_calls(trace))


# ---------------------------------------------------------------------------
# Auto-import all metric modules so they self-register
# ---------------------------------------------------------------------------

def _auto_register() -> None:
    """Import all metric modules in this package."""
    import importlib
    import pkgutil
    from pathlib import Path

    pkg_dir = Path(__file__).parent
    for info in pkgutil.iter_modules([str(pkg_dir)]):
        if info.name.startswith("_"):
            continue
        importlib.import_module(f"eval.metrics.{info.name}")


_auto_register()
