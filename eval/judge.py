"""LLM-as-judge for soft assertions.

Uses a cheap model with structured output (tool_use) to return
a JSON verdict with score and rationale. Per-case rubrics are
loaded from YAML files in eval/rubrics/.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from anthropic import Anthropic

from eval.models import MetricResult, MetricStatus, SoftAssertion


# ---------------------------------------------------------------------------
# Judge tool schema — forces structured output
# ---------------------------------------------------------------------------

_JUDGE_TOOL = {
    "name": "submit_verdict",
    "description": (
        "Submit your evaluation verdict. You MUST call this tool with your "
        "score and rationale."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "score": {
                "type": "integer",
                "description": "Score from 1 to 5 based on the rubric.",
            },
            "rationale": {
                "type": "string",
                "description": (
                    "Brief explanation (2-4 sentences) of why you assigned "
                    "this score. Reference specific parts of the answer."
                ),
            },
        },
        "required": ["score", "rationale"],
    },
}


def judge(
    assertion: SoftAssertion,
    question: str,
    answer: str,
    trace_summary: str,
    model: str = "claude-haiku-4-5",
) -> MetricResult:
    """Run an LLM judge on a single soft assertion.

    Args:
        assertion: The soft assertion with rubric.
        question: The original user question.
        answer: The agent's final answer.
        trace_summary: A condensed summary of the trace (tool calls, etc.).
        model: The judge model to use.

    Returns:
        MetricResult with structured verdict.
    """
    system = (
        "You are an evaluation judge for an AI research assistant. "
        "You evaluate the assistant's answer to a user question based on a rubric.\n\n"
        "Be strict but fair. Focus on factual accuracy and whether the answer "
        "meets the specific criteria in the rubric. Do not give high scores "
        "for vague or partially correct answers.\n\n"
        "You MUST call the submit_verdict tool with your score and rationale."
    )

    user_prompt = (
        f"## Question\n{question}\n\n"
        f"## Assistant's Answer\n{answer}\n\n"
        f"## Trace Summary\n{trace_summary}\n\n"
        f"## Rubric\n{assertion.rubric}\n\n"
        f"## Scoring Scale\n"
        f"1 = Completely wrong or harmful\n"
        f"2 = Mostly wrong, major issues\n"
        f"3 = Partially correct, significant gaps\n"
        f"4 = Mostly correct, minor issues\n"
        f"5 = Fully correct, well-supported\n\n"
        f"Evaluate the answer against the rubric and submit your verdict."
    )

    client = Anthropic()
    max_retries = 5
    base_delay = 5.0

    for attempt in range(max_retries + 1):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=512,
                temperature=0.0,
                system=system,
                tools=[_JUDGE_TOOL],
                tool_choice={"type": "tool", "name": "submit_verdict"},
                messages=[{"role": "user", "content": user_prompt}],
            )

            # Extract the tool call
            for block in resp.content:
                if getattr(block, "type", "") == "tool_use":
                    args = block.input
                    score = int(args.get("score", 0))
                    rationale = str(args.get("rationale", ""))
                    passed = score >= assertion.pass_threshold

                    return MetricResult(
                        metric_name=f"judge_{assertion.metric}",
                        status=MetricStatus.PASS if passed else MetricStatus.FAIL,
                        score=float(score),
                        rationale=rationale,
                        details={
                            "pass_threshold": assertion.pass_threshold,
                            "judge_model": model,
                        },
                    )

            return MetricResult(
                metric_name=f"judge_{assertion.metric}",
                status=MetricStatus.ERROR,
                score=None,
                rationale="Judge did not return a tool call",
            )

        except Exception as e:
            error_str = f"{type(e).__name__}: {e}"
            is_retryable = any(
                tok in error_str.lower()
                for tok in ["rate_limit", "ratelimit", "429", "500", "502", "503", "529", "timeout", "connection"]
            )
            if is_retryable and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                time.sleep(delay)
                continue
                
            return MetricResult(
                metric_name=f"judge_{assertion.metric}",
                status=MetricStatus.ERROR,
                score=None,
                rationale=f"Judge error: {error_str}",
            )


def make_trace_summary(trace: dict[str, Any]) -> str:
    """Condense a trace into a readable summary for the judge."""
    lines = []
    for msg in trace.get("messages", []):
        role = msg.get("role", "?")
        if role == "system":
            lines.append("[SYSTEM PROMPT omitted]")
        elif role == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                lines.append(f"USER: {content[:200]}")
        elif role == "assistant":
            text = msg.get("text", "")
            tool_calls = msg.get("tool_calls", [])
            if text:
                lines.append(f"ASSISTANT: {text[:200]}")
            for tc in tool_calls:
                args_str = json.dumps(tc.get("args", {}), default=str)
                if len(args_str) > 200:
                    args_str = args_str[:200] + "..."
                lines.append(f"  → TOOL_CALL: {tc['name']}({args_str})")
        elif role == "tool":
            name = msg.get("name", "?")
            content = msg.get("content", "")
            content_str = json.dumps(content, default=str) if not isinstance(content, str) else content
            if len(content_str) > 300:
                content_str = content_str[:300] + "..."
            lines.append(f"  ← TOOL_RESULT ({name}): {content_str}")

    lines.append(f"\nFinal answer: {trace.get('final_answer', 'N/A')}")
    lines.append(f"Citations: {trace.get('citations', [])}")
    lines.append(f"Stopped reason: {trace.get('stopped_reason', '?')}")

    return "\n".join(lines)
