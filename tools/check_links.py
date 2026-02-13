"""Check that all relative markdown links resolve to real files."""

import re
import sys
from pathlib import Path

from config import REFERENCES_DIR, SKILL_DIR, SKILL_MD


def find_markdown_files() -> list[Path]:
    """Find all markdown files in the skill directory."""
    files = [SKILL_MD]
    files.extend(sorted(REFERENCES_DIR.glob("*.md")))
    return files


def extract_relative_links(text: str) -> list[str]:
    """Extract relative links from markdown (not http/https)."""
    # Match [text](path) but not [text](https://...) or [text](http://...)
    links = re.findall(r"\[(?:[^\]]*)\]\(([^)]+)\)", text)
    return [link for link in links if not link.startswith(("http://", "https://", "#"))]


def main() -> None:
    errors = []

    for md_file in find_markdown_files():
        text = md_file.read_text()
        links = extract_relative_links(text)

        for link in links:
            # Strip any anchor fragments
            path_part = link.split("#")[0]
            if not path_part:
                continue

            target = (md_file.parent / path_part).resolve()
            if not target.exists():
                rel = md_file.relative_to(SKILL_DIR)
                errors.append(f"{rel}: broken link -> {link}")

    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        sys.exit(1)

    print("OK: All internal links resolve")
    sys.exit(0)
