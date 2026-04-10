"""Interactive TUI for browsing git commits and comparing skill token counts.

Usage:
    uv run token-tui
    uv run token-tui --limit 30    # show more commits
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from token_count import (
    compare_token_counts,
    count_skill_tokens_at_commit,
    format_comparison_table,
    format_token_table,
)

REPO_ROOT = Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
)

console = Console()


def get_commits(limit: int = 20) -> list[dict]:
    result = subprocess.run(
        ["git", "log", f"--max-count={limit}", "--format=%H%x00%h%x00%s%x00%ai"],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    )
    commits = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\0")
        if len(parts) == 4:
            commits.append({
                "hash": parts[0],
                "short": parts[1],
                "subject": parts[2],
                "date": parts[3][:10],
            })
    return commits


def show_commit_table(commits: list[dict]) -> Table:
    table = Table(title="Recent Commits", show_lines=False)
    table.add_column("#", style="bold", width=4)
    table.add_column("Hash", style="cyan", width=9)
    table.add_column("Date", width=12)
    table.add_column("Subject")
    for i, c in enumerate(commits, 1):
        table.add_row(str(i), c["short"], c["date"], c["subject"])
    return table


def parse_selection(text: str, max_val: int) -> list[int] | None:
    parts = [p.strip() for p in text.split(",")]
    if len(parts) not in (1, 2):
        return None
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if any(n < 1 or n > max_val for n in nums):
        return None
    return nums


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive skill token browser")
    parser.add_argument("--limit", type=int, default=20, help="Number of commits")
    args = parser.parse_args()

    commits = get_commits(args.limit)
    if not commits:
        console.print("[red]No commits found.[/red]")
        return

    while True:
        console.print()
        console.print(show_commit_table(commits))
        console.print()
        console.print(
            "[dim]Enter a number for token counts, "
            "or two comma-separated numbers to compare. "
            "q to quit.[/dim]"
        )

        choice = Prompt.ask("Selection")
        if choice.lower() in ("q", "quit", "exit"):
            break

        nums = parse_selection(choice, len(commits))
        if nums is None:
            console.print("[red]Invalid selection. Use a number or two numbers "
                          "separated by a comma.[/red]")
            continue

        try:
            if len(nums) == 1:
                c = commits[nums[0] - 1]
                console.print(f"\n[bold]Counting tokens at {c['short']}[/bold]: "
                              f"{c['subject']}")
                data = count_skill_tokens_at_commit(c["hash"])
                console.print(format_token_table(
                    data, title=f"Skill Tokens @ {c['short']}"
                ))
            else:
                c1 = commits[nums[0] - 1]
                c2 = commits[nums[1] - 1]
                console.print(f"\n[bold]Comparing {c1['short']} → {c2['short']}[/bold]")
                before = count_skill_tokens_at_commit(c1["hash"])
                after = count_skill_tokens_at_commit(c2["hash"])
                comparison = compare_token_counts(before, after)
                console.print(format_comparison_table(
                    comparison,
                    before_label=f"{c1['short']}",
                    after_label=f"{c2['short']}",
                ))
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Git error: {e}[/red]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    main()
