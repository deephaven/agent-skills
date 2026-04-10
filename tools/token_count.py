"""Token counting for skill files using tiktoken.

Count tokens in skill files (SKILL.md + references/*.md) from the filesystem
or from a specific git commit.

Usage:
    uv run count-tokens                    # current working tree
    uv run count-tokens abc1234            # at a specific commit
    uv run count-tokens abc1234 def5678    # compare two commits
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import tiktoken
from rich.console import Console
from rich.table import Table

REPO_ROOT = Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
)
SKILL_PREFIX = "skills/deephaven-core-query-writing"
SKILL_DIR = REPO_ROOT / SKILL_PREFIX

console = Console()


def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    enc = tiktoken.get_encoding(encoding_name)
    return len(enc.encode(text))


def count_skill_tokens_from_disk(
    skill_dir: Path, encoding_name: str = "cl100k_base"
) -> dict:
    files = []
    total_tokens = 0
    total_lines = 0

    for md_path in sorted(skill_dir.rglob("*.md")):
        text = md_path.read_text()
        tokens = count_tokens(text, encoding_name)
        lines = text.count("\n")
        rel = str(md_path.relative_to(skill_dir))
        files.append({"path": rel, "tokens": tokens, "lines": lines})
        total_tokens += tokens
        total_lines += lines

    files.sort(key=lambda f: f["tokens"], reverse=True)
    return {
        "total_tokens": total_tokens,
        "total_lines": total_lines,
        "encoding": encoding_name,
        "files": files,
    }


def count_skill_tokens_at_commit(
    commit_hash: str,
    skill_prefix: str = SKILL_PREFIX,
    encoding_name: str = "cl100k_base",
) -> dict:
    result = subprocess.run(
        ["git", "ls-tree", "--name-only", "-r", commit_hash, skill_prefix],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    )
    paths = [p for p in result.stdout.strip().splitlines() if p.endswith(".md")]

    files = []
    total_tokens = 0
    total_lines = 0

    for file_path in sorted(paths):
        text = subprocess.run(
            ["git", "show", f"{commit_hash}:{file_path}"],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO_ROOT,
        ).stdout
        tokens = count_tokens(text, encoding_name)
        lines = text.count("\n")
        rel = file_path.removeprefix(skill_prefix + "/")
        files.append({"path": rel, "tokens": tokens, "lines": lines})
        total_tokens += tokens
        total_lines += lines

    files.sort(key=lambda f: f["tokens"], reverse=True)
    return {
        "total_tokens": total_tokens,
        "total_lines": total_lines,
        "encoding": encoding_name,
        "files": files,
    }


def compare_token_counts(before: dict, after: dict) -> dict:
    before_map = {f["path"]: f for f in before["files"]}
    after_map = {f["path"]: f for f in after["files"]}
    all_paths = sorted(set(before_map) | set(after_map))

    files = []
    for path in all_paths:
        b = before_map.get(path, {"tokens": 0, "lines": 0})
        a = after_map.get(path, {"tokens": 0, "lines": 0})
        delta = a["tokens"] - b["tokens"]
        status = ""
        if path not in before_map:
            status = "(new)"
        elif path not in after_map:
            status = "(removed)"
        files.append({
            "path": path,
            "before": b["tokens"],
            "after": a["tokens"],
            "delta": delta,
            "status": status,
        })

    files.sort(key=lambda f: abs(f["delta"]), reverse=True)
    return {
        "total_before": before["total_tokens"],
        "total_after": after["total_tokens"],
        "total_delta": after["total_tokens"] - before["total_tokens"],
        "files": files,
    }


def format_token_table(data: dict, title: str = "Skill Token Counts") -> Table:
    table = Table(title=title, show_footer=True)
    table.add_column("File", footer="Total", style="cyan")
    table.add_column("Lines", justify="right", footer=f"{data['total_lines']:,}")
    table.add_column(
        "Tokens", justify="right", style="bold", footer=f"{data['total_tokens']:,}"
    )
    table.add_column("% of Total", justify="right")

    for f in data["files"]:
        pct = (
            f"{f['tokens'] / data['total_tokens'] * 100:.1f}%"
            if data["total_tokens"]
            else "0%"
        )
        table.add_row(f["path"], f"{f['lines']:,}", f"{f['tokens']:,}", pct)

    return table


def format_comparison_table(comparison: dict, before_label: str = "Before",
                            after_label: str = "After") -> Table:
    table = Table(title=f"Token Comparison: {before_label} vs {after_label}",
                  show_footer=True)
    table.add_column("File", footer="Total", style="cyan")
    table.add_column(before_label, justify="right",
                     footer=f"{comparison['total_before']:,}")
    table.add_column(after_label, justify="right",
                     footer=f"{comparison['total_after']:,}")

    delta_footer = f"{comparison['total_delta']:+,}"
    table.add_column("Delta", justify="right", footer=delta_footer)
    table.add_column("Status", style="dim")

    for f in comparison["files"]:
        delta = f["delta"]
        if delta > 0:
            delta_str = f"[red]+{delta:,}[/red]"
        elif delta < 0:
            delta_str = f"[green]{delta:,}[/green]"
        else:
            delta_str = "0"

        before_str = f"{f['before']:,}" if f["before"] else "—"
        after_str = f"{f['after']:,}" if f["after"] else "—"
        table.add_row(f["path"], before_str, after_str, delta_str, f["status"])

    return table


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count tokens in skill files using tiktoken"
    )
    parser.add_argument(
        "hashes",
        nargs="*",
        help="0 args = disk, 1 arg = at commit, 2 args = compare commits",
    )
    args = parser.parse_args()

    if len(args.hashes) == 0:
        data = count_skill_tokens_from_disk(SKILL_DIR)
        console.print(format_token_table(data, title="Skill Tokens (working tree)"))
    elif len(args.hashes) == 1:
        h = args.hashes[0]
        data = count_skill_tokens_at_commit(h)
        short = h[:8]
        console.print(format_token_table(data, title=f"Skill Tokens @ {short}"))
    elif len(args.hashes) == 2:
        before = count_skill_tokens_at_commit(args.hashes[0])
        after = count_skill_tokens_at_commit(args.hashes[1])
        comparison = compare_token_counts(before, after)
        console.print(format_comparison_table(
            comparison,
            before_label=args.hashes[0][:8],
            after_label=args.hashes[1][:8],
        ))
    else:
        parser.error("Expected 0, 1, or 2 commit hashes")
        sys.exit(1)


if __name__ == "__main__":
    main()
