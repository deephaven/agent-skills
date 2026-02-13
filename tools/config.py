"""Path constants for the deephaven-core-query-writing skill."""

from pathlib import Path

# Resolve repo root: tools/config.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "skills" / "deephaven-core-query-writing"
SKILL_MD = SKILL_DIR / "SKILL.md"
REFERENCES_DIR = SKILL_DIR / "references"
