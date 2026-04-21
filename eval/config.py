"""Configuration for the evaluation framework."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


@dataclass
class EvalConfig:
    """Runtime configuration for an evaluation run."""

    # Concurrency
    concurrency: int = 3

    # Repeats (for flakiness detection)
    repeats: int = 1

    # Judge model — same cheap tier as the agent
    judge_model: str = "claude-haiku-4-5"

    # Agent model (passed through to agent)
    agent_model: str = os.getenv("DRL_MODEL", "claude-haiku-4-5")

    # Retry policy
    max_retries: int = 3
    retry_base_delay: float = 1.0   # seconds, exponential backoff
    retry_max_delay: float = 30.0   # cap

    # Paths
    project_root: Path = _PROJECT_ROOT
    traces_dir: Path = field(default_factory=lambda: _PROJECT_ROOT / "eval_traces")
    reports_dir: Path = field(default_factory=lambda: _PROJECT_ROOT / "eval_reports")
    fixtures_dir: Path = field(default_factory=lambda: _PROJECT_ROOT / "fixture_traces")
    suite_dir: Path = field(default_factory=lambda: _PROJECT_ROOT / "eval" / "suite")
    rubrics_dir: Path = field(default_factory=lambda: _PROJECT_ROOT / "eval" / "rubrics")
    viewer_dir: Path = field(default_factory=lambda: _PROJECT_ROOT / "eval_viewer")

    def ensure_dirs(self) -> None:
        """Create output directories if they don't exist."""
        for d in [self.traces_dir, self.reports_dir, self.viewer_dir]:
            d.mkdir(parents=True, exist_ok=True)

    @property
    def api_key(self) -> str:
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
            )
        return key
