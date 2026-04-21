"""Citation quality metric — checks citation integrity and quote verification."""

from __future__ import annotations

from typing import Any

from eval.models import MetricResult, MetricStatus, TestCase
from eval.metrics import Metric, register, extract_fetch_urls, extract_tool_calls


class CitationQualityMetric(Metric):
    """Verifies that citations are backed by actual fetches and quotes are real."""

    name = "citation_quality"
    description = "Checks that citations match fetched URLs and quotes appear in source"

    def score(
        self, case: TestCase, trace: dict[str, Any], final_answer: str | None
    ) -> MetricResult:
        issues = []

        citations = trace.get("citations", [])
        fetched_urls = extract_fetch_urls(trace)

        # 1. Every citation must have been fetched
        unfetched = [c for c in citations if c not in fetched_urls]
        if unfetched:
            issues.append(f"Citations not backed by fetch_url: {unfetched}")

        # 2. Check for "fabricated" citations (URLs not in any search result)
        search_result_urls = set()
        for msg in trace.get("messages", []):
            if msg.get("role") == "tool" and msg.get("name") == "web_search":
                content = msg.get("content", [])
                if isinstance(content, list):
                    for r in content:
                        if isinstance(r, dict) and "url" in r:
                            search_result_urls.add(r["url"])

        for c in citations:
            if c not in search_result_urls and c not in fetched_urls:
                issues.append(f"Citation {c!r} was never returned by web_search")

        # 3. Check for quote fidelity (planted bug: extract_quotes may hallucinate)
        # We gather extracted quotes and the source texts, then check substring match
        tool_calls = extract_tool_calls(trace)
        tool_results = {
            msg.get("tool_use_id"): msg.get("content")
            for msg in trace.get("messages", [])
            if msg.get("role") == "tool"
        }

        for tc in tool_calls:
            if tc["name"] == "extract_quotes":
                # The input text was passed to extract_quotes
                source_text = tc.get("args", {}).get("text", "")
                # The result contains the extracted quotes
                result = tool_results.get(tc.get("id"))
                if isinstance(result, list):
                    for quote in result:
                        if isinstance(quote, str) and len(quote) > 20:
                            # Check if the quote actually appears in source
                            if quote.strip() not in source_text:
                                issues.append(
                                    f"Extracted 'quote' not found verbatim in source: "
                                    f"{quote[:80]!r}..."
                                )

        details = {
            "citations": citations,
            "fetched_urls": list(fetched_urls),
            "issues": issues,
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
            rationale=f"All {len(citations)} citations verified",
            details=details,
        )


register(CitationQualityMetric())
