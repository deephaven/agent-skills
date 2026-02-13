"""Run each Python code block from skill markdown files against Deephaven.

Each block runs in its own isolated `dh exec` process with `--port 0` (auto-
assigned port), so no state leaks between blocks. Blocks run in parallel by
default for speed.

Usage:
    uv run run-each-block                  # run all blocks in parallel
    uv run run-each-block joins.md         # run blocks from one reference file
    uv run run-each-block --timeout 45     # custom per-block timeout (default: 30s)
    uv run run-each-block --workers 4      # limit parallelism (default: 8)
    uv run run-each-block --sequential     # disable parallelism
    uv run run-each-block --stop-on-fail   # stop at first failure
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from config import REFERENCES_DIR, SKILL_DIR, SKILL_MD

SKIP_MARKERS = {"# pseudo", "# incomplete"}


@dataclass
class Block:
    file: str  # relative path like "references/joins.md"
    block_num: int  # 1-based index within the file
    line_num: int  # line number in the markdown file
    code: str
    label: str
    skipped: bool = False
    passed: bool | None = None  # None = not run yet
    output: str = ""


@dataclass
class Results:
    blocks: list[Block] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.blocks)

    @property
    def skip_count(self) -> int:
        return sum(1 for b in self.blocks if b.skipped)

    @property
    def pass_count(self) -> int:
        return sum(1 for b in self.blocks if b.passed is True)

    @property
    def fail_count(self) -> int:
        return sum(1 for b in self.blocks if b.passed is False)

    @property
    def failures(self) -> list[Block]:
        return [b for b in self.blocks if b.passed is False]


def find_markdown_files(filter_name: str | None = None) -> list[Path]:
    if filter_name:
        if not filter_name.endswith(".md"):
            filter_name += ".md"
        candidate = REFERENCES_DIR / filter_name
        if candidate.exists():
            return [candidate]
        if filter_name.upper() == "SKILL.MD" and SKILL_MD.exists():
            return [SKILL_MD]
        print(f"Error: No file matching '{filter_name}' found")
        sys.exit(2)

    files = [SKILL_MD]
    files.extend(sorted(REFERENCES_DIR.glob("*.md")))
    return files


def extract_python_blocks(text: str) -> list[tuple[int, str]]:
    blocks = []
    pattern = re.compile(r"^```python\s*\n(.*?)^```", re.MULTILINE | re.DOTALL)
    for match in pattern.finditer(text):
        line_num = text[: match.start()].count("\n") + 2
        blocks.append((line_num, match.group(1)))
    return blocks


def should_skip(code: str) -> bool:
    first_line = code.strip().split("\n")[0] if code.strip() else ""
    return any(marker in first_line for marker in SKIP_MARKERS)


def get_block_label(code: str, line_num: int) -> str:
    for line in code.strip().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("from ", "import ", "#")):
            continue
        return stripped[:57] + "..." if len(stripped) > 60 else stripped
    return f"line {line_num}"


def run_block(block: Block, timeout: int, dh_path: str) -> Block:
    """Run a single block in its own dh exec process. Mutates and returns block."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", prefix="dh_block_", delete=False
    ) as f:
        f.write(block.code)
        tmp_path = Path(f.name)

    try:
        cmd = [
            dh_path,
            "exec",
            str(tmp_path),
            "--port",
            "0",
            "--timeout",
            str(timeout),
            "--no-show-tables",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 30,
        )
        parts = []
        if result.stdout.strip():
            parts.append(result.stdout.strip())
        if result.stderr.strip():
            parts.append(result.stderr.strip())
        block.output = "\n".join(parts)
        block.passed = result.returncode == 0

    except subprocess.TimeoutExpired:
        block.output = f"Timed out after {timeout}s"
        block.passed = False
    finally:
        tmp_path.unlink(missing_ok=True)

    return block


def collect_blocks(md_files: list[Path]) -> list[Block]:
    """Extract all blocks from all files into a flat list."""
    blocks = []
    for md_file in md_files:
        text = md_file.read_text()
        rel = str(md_file.relative_to(SKILL_DIR))
        for idx, (line_num, code) in enumerate(extract_python_blocks(text), 1):
            label = get_block_label(code, line_num)
            block = Block(
                file=rel,
                block_num=idx,
                line_num=line_num,
                code=code,
                label=label,
                skipped=should_skip(code),
            )
            blocks.append(block)
    return blocks


def print_results(results: Results) -> None:
    # Group by file for display
    by_file: dict[str, list[Block]] = {}
    for b in results.blocks:
        by_file.setdefault(b.file, []).append(b)

    for file, blocks in by_file.items():
        print(f"\n  {file}")
        for b in blocks:
            if b.skipped:
                status = "SKIP"
            elif b.passed:
                status = "PASS"
            else:
                status = "FAIL"
            print(
                f"    {status}  block {b.block_num:>2} "
                f"(line {b.line_num:>3}): {b.label}"
            )

    print(f"\n{'=' * 60}")
    print(
        f"  RESULTS: {results.pass_count} passed, {results.fail_count} failed, "
        f"{results.skip_count} skipped ({results.total} total)"
    )
    print(f"{'=' * 60}")

    if results.failures:
        print(f"\n{'─' * 60}")
        print("  FAILURES")
        print(f"{'─' * 60}")
        for i, b in enumerate(results.failures, 1):
            print(f"\n  [{i}] {b.file}:{b.line_num} (block {b.block_num})")
            print(f"      {b.label}")
            print()
            for line in b.output.splitlines():
                print(f"      {line}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run each Python code block against Deephaven in isolation"
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="Run blocks from a specific file (e.g. 'joins.md' or 'SKILL.md')",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Per-block timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Max parallel workers (default: 8)",
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Run blocks one at a time instead of in parallel",
    )
    parser.add_argument(
        "--stop-on-fail",
        action="store_true",
        help="Stop at first failure",
    )
    args = parser.parse_args()

    dh_path: str | None = shutil.which("dh")
    if dh_path is None:
        print("Error: 'dh' CLI not found on PATH")
        sys.exit(2)
    assert dh_path is not None  # narrowing for type checkers

    md_files = find_markdown_files(args.file)
    all_blocks = collect_blocks(md_files)
    runnable = [b for b in all_blocks if not b.skipped]

    n_run = len(runnable)
    n_skip = len(all_blocks) - n_run
    workers = 1 if args.sequential else min(args.workers, n_run)

    print(
        f"Running {n_run} blocks ({n_skip} skipped) with {workers} workers, "
        f"timeout {args.timeout}s each"
    )

    completed = 0

    if workers <= 1:
        # Sequential
        for block in runnable:
            block = run_block(block, args.timeout, dh_path)
            completed += 1
            status = "PASS" if block.passed else "FAIL"
            print(
                f"  [{completed}/{n_run}] {status}  {block.file}:{block.line_num} "
                f"block {block.block_num}",
                flush=True,
            )
            if args.stop_on_fail and not block.passed:
                break
    else:
        # Parallel
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(run_block, b, args.timeout, dh_path): b
                for b in runnable
            }
            try:
                for future in as_completed(futures):
                    block = future.result()
                    completed += 1
                    status = "PASS" if block.passed else "FAIL"
                    print(
                        f"  [{completed}/{n_run}] {status}  "
                        f"{block.file}:{block.line_num} "
                        f"block {block.block_num}",
                        flush=True,
                    )
                    if args.stop_on_fail and not block.passed:
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
            except KeyboardInterrupt:
                print("\nInterrupted, waiting for running blocks to finish...")
                executor.shutdown(wait=True, cancel_futures=True)
                sys.exit(130)

    results = Results(blocks=all_blocks)
    print_results(results)
    sys.exit(1 if results.failures else 0)


if __name__ == "__main__":
    main()
