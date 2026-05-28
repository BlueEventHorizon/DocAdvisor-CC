#!/usr/bin/env python3
"""forge subagent terminology test helpers."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
TERMS_PATH = REPO_ROOT / 'docs/rules/skill_launch_terms.toml'


def load_terms() -> dict[str, Any]:
    with TERMS_PATH.open('rb') as f:
        return tomllib.load(f)
