"""Validate SKILL.md frontmatter and reference file existence."""

import re
import sys

import yaml

from config import SKILL_DIR, SKILL_MD


def parse_frontmatter(text: str) -> dict | None:
    """Extract YAML frontmatter from markdown text."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return None
    return yaml.safe_load(match.group(1))


def validate_frontmatter(fm: dict) -> list[str]:
    """Validate required frontmatter fields."""
    errors = []

    required_top = ["name", "description", "license"]
    for field in required_top:
        if field not in fm:
            errors.append(f"Missing required frontmatter field: {field}")

    if "metadata" not in fm:
        errors.append("Missing required frontmatter field: metadata")
    else:
        meta = fm["metadata"]
        for field in ["author", "version"]:
            if field not in meta:
                errors.append(f"Missing required metadata field: {field}")

    # Name must match directory name
    if "name" in fm:
        if fm["name"] != SKILL_DIR.name:
            errors.append(
                f"Frontmatter name '{fm['name']}' does not match "
                f"directory name '{SKILL_DIR.name}'"
            )
        # Name format: lowercase with hyphens
        if not re.match(r"^[a-z][a-z0-9-]*$", fm["name"]):
            errors.append(
                f"Skill name '{fm['name']}' must be lowercase with hyphens only"
            )

    return errors


def extract_referenced_files(text: str) -> list[str]:
    """Extract reference file paths from SKILL.md markdown tables."""
    # Match backtick-wrapped paths like `references/joins.md`
    return re.findall(r"`(references/[^`]+\.md)`", text)


def validate_references(text: str) -> list[str]:
    """Check that all referenced files actually exist."""
    errors = []
    refs = extract_referenced_files(text)

    for ref in refs:
        path = SKILL_DIR / ref
        if not path.exists():
            errors.append(f"Referenced file does not exist: {ref}")

    return errors


def check_line_count(text: str) -> list[str]:
    """Warn if SKILL.md exceeds 500 lines."""
    warnings = []
    lines = text.count("\n") + 1
    if lines > 500:
        warnings.append(f"SKILL.md has {lines} lines (consider keeping under 500)")
    return warnings


def main() -> None:
    errors = []
    warnings = []

    # Check SKILL.md exists
    if not SKILL_MD.exists():
        print(f"FAIL: {SKILL_MD} does not exist")
        sys.exit(1)

    text = SKILL_MD.read_text()

    # Parse and validate frontmatter
    fm = parse_frontmatter(text)
    if fm is None:
        errors.append("SKILL.md is missing YAML frontmatter (--- delimiters)")
    else:
        errors.extend(validate_frontmatter(fm))

    # Validate referenced files exist
    errors.extend(validate_references(text))

    # Line count warning
    warnings.extend(check_line_count(text))

    # Report
    if warnings:
        for w in warnings:
            print(f"WARN: {w}")

    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        sys.exit(1)

    print("OK: Validation passed")
    sys.exit(0)
