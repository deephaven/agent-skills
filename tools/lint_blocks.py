"""Lint Python code blocks in skill markdown files with ruff.

Extracts each Python code block, writes it to a temp file, and runs
`ruff check` on it. Blocks tagged with `# pseudo` or `# incomplete`
are skipped. F401 (unused imports) is ignored since example blocks
often import symbols used only conceptually.

Usage:
    uv run lint-blocks                    # lint all blocks
    uv run lint-blocks joins.md           # lint blocks from one file
    uv run lint-blocks --fix              # auto-fix issues in-place
    uv run lint-blocks --stop-on-fail     # stop at first failure
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from config import REFERENCES_DIR, SKILL_DIR, SKILL_MD

SKIP_MARKERS = {"# pseudo", "# incomplete"}

IGNORED_RULES = [
    "E402",  # module-level import not at top — some blocks import after setup code
]


@dataclass
class Block:
    file: str
    block_num: int
    line_num: int
    code: str
    label: str
    skipped: bool = False
    passed: bool | None = None
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


def collect_blocks(md_files: list[Path]) -> list[Block]:
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


def lint_block(block: Block, ruff_path: str, *, fix: bool = False) -> Block:
    """Lint a single block with ruff. Mutates and returns block."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", prefix="ruff_block_", delete=False
    ) as f:
        f.write(block.code)
        tmp_path = Path(f.name)

    try:
        ignore = ",".join(IGNORED_RULES)
        cmd = [
            ruff_path,
            "check",
            "--isolated",
            "--select",
            "E,W,F,I",
            "--ignore",
            ignore,
        ]
        if fix:
            cmd.append("--fix")
        cmd.append(str(tmp_path))

        result = subprocess.run(cmd, capture_output=True, text=True)

        # If --fix was used, always read back (ruff may fix some issues
        # while others remain, so returncode can still be non-zero)
        if fix:
            block.code = tmp_path.read_text()

        output = result.stdout.strip()
        # Replace temp path with meaningful location in output
        if output:
            output = output.replace(str(tmp_path), f"{block.file}:{block.line_num}")
        block.output = output
        block.passed = result.returncode == 0

    finally:
        tmp_path.unlink(missing_ok=True)

    return block


def apply_fixes(md_files: list[Path], blocks: list[Block]) -> int:
    """Write fixed code back into the markdown files. Returns count."""
    count = 0
    for md_file in md_files:
        rel = str(md_file.relative_to(SKILL_DIR))
        text = md_file.read_text()
        pattern = re.compile(r"^```python\s*\n(.*?)^```", re.MULTILINE | re.DOTALL)

        # Map line_num -> block for all non-skipped blocks in this file
        block_map = {b.line_num: b for b in blocks if b.file == rel and not b.skipped}

        new_text = text
        offset = 0
        for match in pattern.finditer(text):
            line_num = text[: match.start()].count("\n") + 2
            if line_num in block_map:
                block = block_map[line_num]
                old_code = match.group(1)
                if block.code != old_code:
                    start = match.start(1) + offset
                    end = match.end(1) + offset
                    new_text = new_text[:start] + block.code + new_text[end:]
                    offset += len(block.code) - len(old_code)
                    count += 1

        if new_text != text:
            md_file.write_text(new_text)

    return count


def print_results(results: Results) -> None:
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
        f"  RESULTS: {results.pass_count} passed, "
        f"{results.fail_count} failed, "
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
        description="Lint Python code blocks in skill markdown with ruff"
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="Lint blocks from a specific file (e.g. 'joins.md')",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix issues and write changes back to markdown",
    )
    parser.add_argument(
        "--stop-on-fail",
        action="store_true",
        help="Stop at first failure",
    )
    args = parser.parse_args()

    ruff_path: str | None = shutil.which("ruff")
    if ruff_path is None:
        print("Error: 'ruff' not found on PATH")
        sys.exit(2)
    assert ruff_path is not None  # narrowing for type checkers

    md_files = find_markdown_files(args.file)
    all_blocks = collect_blocks(md_files)
    runnable = [b for b in all_blocks if not b.skipped]

    n_run = len(runnable)
    n_skip = len(all_blocks) - n_run
    mode = "fix" if args.fix else "check"
    print(f"Linting {n_run} blocks ({n_skip} skipped), mode: {mode}")

    for block in runnable:
        lint_block(block, ruff_path, fix=args.fix)
        status = "PASS" if block.passed else "FAIL"
        print(
            f"  {status}  {block.file}:{block.line_num} block {block.block_num}",
            flush=True,
        )
        if args.stop_on_fail and not block.passed:
            break

    if args.fix:
        fixed = apply_fixes(md_files, all_blocks)
        if fixed:
            print(f"\nFixed {fixed} blocks in-place")

    results = Results(blocks=all_blocks)
    print_results(results)
    sys.exit(1 if results.failures else 0)


if __name__ == "__main__":
    main()
