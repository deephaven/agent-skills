"""Grade eval runs by checking expectations against outputs using a Claude agent.

The grader runs as a full Claude agent (haiku) with tool access. Instead of
parsing raw LLM text as JSON, the agent writes grading.json directly via the
Write tool — guaranteeing valid JSON output.

Usage:
    uv run grade-evals --run-id test-001
    uv run grade-evals --run-id test-001 --evals 11
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from rich.console import Console

console = Console()

EVALS_DIR = Path(__file__).resolve().parent
EVALS_JSON_PATH = EVALS_DIR / "evals.json"
EVALS_RUNS_DIR = EVALS_DIR / "runs"
CONFIGS = ["with_skill", "without_skill"]

GRADER_PROMPT = """\
You are an eval grader. Evaluate each expectation against the outputs of a \
code generation task and write the results to a JSON file.

## Inputs

Expectations to evaluate:
{expectations}

Output files are in: {outputs_dir}

Read the following files from that directory (if they exist):
- script.py — the generated script
- exec-result.txt — dh exec stdout/stderr and exit code
- render-result.txt — accessibility-tree snapshot of the rendered UI (or error output)
- validation.json — structured exec/render results

The grading output must be written to: {grading_path}

## Grading Rules

- Be strict: the expectation must be clearly met, not just partially.
- For "executes without errors": check exec_success and exit code.
- For "renders successfully": check render_success and that the snapshot \
shows actual components (not an error message).
- For code-level expectations (uses a certain API, handles nulls, etc.): \
read the script carefully.
- For UI expectations (includes a chart, has a picker, etc.): check both \
the script AND the render snapshot for evidence.
- If information is missing or insufficient to judge, mark as failed with \
evidence explaining what's missing.

## Output Format

Write a JSON file to {grading_path} with this exact structure:

{{
  "expectations": [
    {{
      "text": "the expectation text",
      "passed": true,
      "evidence": "brief explanation citing specific evidence"
    }}
  ],
  "summary": {{
    "passed": <count>,
    "failed": <count>,
    "total": <count>,
    "pass_rate": <float 0.0-1.0>
  }}
}}

## Process

1. Read the output files listed above
2. Evaluate each expectation
3. Write the grading JSON file

Do not output anything else. Just read, evaluate, and write the file.
"""


def load_evals_map() -> dict[str, dict]:
    """Load evals indexed by name."""
    data = json.loads(EVALS_JSON_PATH.read_text())
    return {e["name"]: e for e in data["evals"]}


def gather_context(outputs_dir: Path) -> dict:
    """Collect all grading context from the outputs directory."""
    script_path = outputs_dir / "script.py"
    validation_path = outputs_dir / "validation.json"
    snapshot_path = outputs_dir / "render-result.txt"
    exec_result_path = outputs_dir / "exec-result.txt"

    script = script_path.read_text() if script_path.exists() else "(no script produced)"
    validation = (
        json.loads(validation_path.read_text()) if validation_path.exists() else {}
    )
    snapshot = snapshot_path.read_text() if snapshot_path.exists() else "(no snapshot)"
    exec_output = exec_result_path.read_text() if exec_result_path.exists() else "(no exec result)"

    return {
        "script": script,
        "validation": validation,
        "snapshot": snapshot,
        "exec_output": exec_output,
        "exec_exit_code": validation.get("exec_exit_code", "unknown"),
        "exec_success": validation.get("exec_success", False),
    }


def grade_run(eval_name: str, config: str, run_dir: Path, eval_def: dict) -> dict:
    """Grade a single run by launching a Claude agent that writes grading.json."""
    run_subdir = run_dir / eval_name / config / "run-1"
    outputs_dir = run_subdir / "outputs"
    grading_path = run_subdir / "grading.json"
    expectations = eval_def.get("expectations", [])

    expectations_text = "\n".join(f"- {e}" for e in expectations)

    prompt = GRADER_PROMPT.format(
        expectations=expectations_text,
        outputs_dir=outputs_dir,
        grading_path=grading_path,
    )

    try:
        result = subprocess.run(
            [
                "claude", "-p",
                "--model", "haiku",
                "--allowedTools", "Read,Write,Glob",
                "--max-turns", "10",
                "--strict-mcp-config",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            console.print(f"    [red]Agent failed: {result.stderr[:200]}[/red]")

    except subprocess.TimeoutExpired:
        console.print("    [red]Agent timed out[/red]")
    except Exception as e:
        console.print(f"    [red]Agent error: {e}[/red]")

    # Read grading.json written by the agent
    if grading_path.exists():
        try:
            grading = json.loads(grading_path.read_text())
        except json.JSONDecodeError:
            console.print(f"    [red]Agent wrote invalid JSON to {grading_path}[/red]")
            grading = _fallback_grading(expectations)
    else:
        console.print(f"    [red]Agent did not write {grading_path}[/red]")
        grading = _fallback_grading(expectations)

    # Ensure summary is present and correct
    results = grading.get("expectations", [])
    passed = sum(1 for r in results if r.get("passed") is True)
    failed = sum(1 for r in results if r.get("passed") is False)
    total = len(results)
    grading["summary"] = {
        "passed": passed,
        "failed": failed,
        "total": total,
        "pass_rate": round(passed / total, 4) if total > 0 else 0.0,
    }

    # Merge timing if available
    timing_path = run_subdir / "timing.json"
    timing = json.loads(timing_path.read_text()) if timing_path.exists() else {}
    grading["timing"] = {
        "total_duration_seconds": timing.get("total_duration_seconds", 0),
    }

    # Re-write with normalized summary and timing
    grading_path.write_text(json.dumps(grading, indent=2))
    return grading


def _fallback_grading(expectations: list[str]) -> dict:
    """Produce a grading dict where every expectation fails."""
    return {
        "expectations": [
            {"text": e, "passed": False, "evidence": "Grader agent did not produce results"}
            for e in expectations
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Grade eval runs")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--evals", nargs="*", type=int, help="Specific eval IDs")
    args = parser.parse_args()

    run_dir = EVALS_RUNS_DIR / args.run_id
    if not run_dir.exists():
        console.print(f"[red]Run not found: {run_dir}[/red]")
        sys.exit(1)

    evals_map = load_evals_map()
    if args.evals:
        all_evals = json.loads(EVALS_JSON_PATH.read_text())["evals"]
        id_to_name = {e["id"]: e["name"] for e in all_evals}
        eval_names = [id_to_name[eid] for eid in args.evals if eid in id_to_name]
    else:
        eval_names = None

    total_graded = 0
    for eval_dir in sorted(run_dir.iterdir()):
        if not eval_dir.is_dir() or eval_dir.name.startswith("."):
            continue
        if eval_names and eval_dir.name not in eval_names:
            continue
        if eval_dir.name not in evals_map:
            continue

        eval_def = evals_map[eval_dir.name]
        for config in CONFIGS:
            outputs_dir = eval_dir / config / "run-1" / "outputs"
            if not outputs_dir.exists():
                continue

            grading = grade_run(eval_dir.name, config, run_dir, eval_def)
            summary = grading["summary"]
            total_graded += 1

            status = (
                "[green]" if summary["pass_rate"] >= 0.8
                else "[yellow]" if summary["pass_rate"] >= 0.5
                else "[red]"
            )
            console.print(
                f"  {status}{eval_dir.name}[/] [{config}]: "
                f"{summary['passed']}/{summary['total']} passed "
                f"({summary['pass_rate']:.0%})"
            )

    console.print(f"\n[bold green]Graded {total_graded} runs[/bold green]")


if __name__ == "__main__":
    main()
