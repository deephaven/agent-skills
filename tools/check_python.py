"""Check that Python code blocks in skill markdown files parse correctly."""

import ast
import re
import sys
import textwrap
from pathlib import Path

from config import REFERENCES_DIR, SKILL_DIR, SKILL_MD

# Code blocks containing these comments are skipped
SKIP_MARKERS = {"# pseudo", "# incomplete"}


def find_markdown_files() -> list[Path]:
    """Find all markdown files in the skill directory."""
    files = [SKILL_MD]
    files.extend(sorted(REFERENCES_DIR.glob("*.md")))
    return files


def extract_python_blocks(text: str) -> list[tuple[int, str]]:
    """Extract python code blocks with their starting line numbers."""
    blocks = []
    pattern = re.compile(r"^```python\s*\n(.*?)^```", re.MULTILINE | re.DOTALL)

    for match in pattern.finditer(text):
        # Calculate line number of the code block start
        line_num = text[: match.start()].count("\n") + 2  # +2 for ```python line
        code = match.group(1)
        blocks.append((line_num, code))

    return blocks


def should_skip(code: str) -> bool:
    """Check if a code block should be skipped based on markers."""
    first_line = code.strip().split("\n")[0] if code.strip() else ""
    return any(marker in first_line for marker in SKIP_MARKERS)


def check_syntax(code: str) -> str | None:
    """Try to parse code with ast.parse(). Dedents uniformly-indented blocks."""
    try:
        ast.parse(textwrap.dedent(code))
        return None
    except SyntaxError as e:
        return f"line {e.lineno}: {e.msg}"


def main() -> None:
    errors = []
    total_blocks = 0
    skipped = 0

    for md_file in find_markdown_files():
        text = md_file.read_text()
        blocks = extract_python_blocks(text)
        rel = md_file.relative_to(SKILL_DIR)

        for line_num, code in blocks:
            total_blocks += 1

            if should_skip(code):
                skipped += 1
                continue

            err = check_syntax(code)
            if err:
                errors.append(f"{rel}:{line_num}: {err}")

    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        print(
            f"\nChecked {total_blocks} blocks ({skipped} skipped), {len(errors)} failed"
        )
        sys.exit(1)

    print(
        f"OK: All {total_blocks} Python blocks parse successfully ({skipped} skipped)"
    )
    sys.exit(0)
