"""Suite loader — reads YAML or JSON test cases from directories or files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from eval.models import (
    AssertionType,
    HardAssertion,
    SoftAssertion,
    TestCase,
)


def load_suite(suite_path: Path | str) -> list[TestCase]:
    """Load test cases from a file or a directory of YAML/JSON files.

    Format matches:
    - input: "user message"
    - expected_behavior:
        hard_assertions: [...]
        soft_assertions: [...]
    """
    path = Path(suite_path)
    if not path.exists():
        raise FileNotFoundError(f"Suite path not found: {path}")

    cases = []
    
    # If it's a directory, parse all .yaml, .yml, .json files
    if path.is_dir():
        files = []
        for ext in ["*.yaml", "*.yml", "*.json"]:
            files.extend(path.glob(ext))
        
        for file in files:
            cases.extend(_parse_file(file))
    else:
        # Single file
        cases.extend(_parse_file(path))
        
    return cases


def _parse_file(file_path: Path) -> list[TestCase]:
    with file_path.open() as f:
        if file_path.suffix == ".json":
            data = json.load(f)
        else:
            data = yaml.safe_load(f)

    # Some suites might specify a top level "cases" array, or just an array of dicts at root
    raw_cases = data.get("cases", []) if isinstance(data, dict) and "cases" in data else (data if isinstance(data, list) else [data])
    
    parsed = []
    for entry in raw_cases:
        expected_behavior = entry.get("expected_behavior", {})
        
        hard = []
        for a in expected_behavior.get("hard_assertions", []):
            hard.append(
                HardAssertion(
                    type=AssertionType(a["type"]),
                    value=a.get("value"),
                    description=a.get("description", ""),
                )
            )

        soft = []
        for a in expected_behavior.get("soft_assertions", []):
            soft.append(
                SoftAssertion(
                    metric=a["metric"],
                    rubric=a["rubric"],
                    pass_threshold=a.get("pass_threshold", 4),
                    description=a.get("description", ""),
                )
            )

        parsed.append(
            TestCase(
                id=entry.get("id", ""),
                name=entry.get("name", "Unnamed Case"),
                input=entry.get("input", ""),
                category=entry.get("category", ""),
                hard_assertions=hard,
                soft_assertions=soft,
                tags=entry.get("tags", []),
                notes=entry.get("notes", ""),
            )
        )

    return parsed
