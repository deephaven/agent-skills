"""Aggregate grading results into benchmark.json.

Produces benchmark.json and benchmark.md compatible with skill-creator's
eval-viewer. Reads grading.json files from the evals run directory layout.

Usage:
    uv run aggregate-evals --run-id test-001
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

console = Console()

EVALS_DIR = Path(__file__).resolve().parent
EVALS_RUNS_DIR = EVALS_DIR / "runs"
EVALS_JSON_PATH = EVALS_DIR / "evals.json"
CONFIGS = ["with_skill", "without_skill"]


def calculate_stats(values: list[float]) -> dict:
    if not values:
        return {"mean": 0.0, "stddev": 0.0, "min": 0.0, "max": 0.0}
    n = len(values)
    mean = sum(values) / n
    if n > 1:
        variance = sum((x - mean) ** 2 for x in values) / (n - 1)
        stddev = math.sqrt(variance)
    else:
        stddev = 0.0
    return {
        "mean": round(mean, 4),
        "stddev": round(stddev, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def main():
    parser = argparse.ArgumentParser(description="Aggregate eval results")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    run_dir = EVALS_RUNS_DIR / args.run_id
    if not run_dir.exists():
        console.print(f"[red]Run not found: {run_dir}[/red]")
        sys.exit(1)

    evals_data = json.loads(EVALS_JSON_PATH.read_text())
    name_to_eval = {e["name"]: e for e in evals_data["evals"]}

    runs = []
    config_results: dict[str, list[dict]] = {c: [] for c in CONFIGS}

    for eval_dir in sorted(run_dir.iterdir()):
        if not eval_dir.is_dir() or eval_dir.name.startswith("."):
            continue
        if eval_dir.name not in name_to_eval:
            continue

        eval_def = name_to_eval[eval_dir.name]

        for config in CONFIGS:
            grading_path = eval_dir / config / "run-1" / "grading.json"
            if not grading_path.exists():
                continue

            grading = json.loads(grading_path.read_text())
            timing_path = eval_dir / config / "run-1" / "timing.json"
            timing = (
                json.loads(timing_path.read_text()) if timing_path.exists() else {}
            )

            result = {
                "pass_rate": grading["summary"]["pass_rate"],
                "passed": grading["summary"]["passed"],
                "failed": grading["summary"]["failed"],
                "total": grading["summary"]["total"],
                "time_seconds": timing.get("total_duration_seconds", 0),
                "tokens": timing.get("total_tokens", 0),
                "tool_calls": 0,
                "errors": grading["summary"].get("failed", 0),
            }

            run_entry = {
                "eval_id": eval_def["id"],
                "eval_name": eval_def["name"],
                "configuration": config,
                "run_number": 1,
                "result": result,
                "expectations": grading.get("expectations", []),
                "notes": [],
            }
            runs.append(run_entry)
            config_results[config].append(result)

    # Compute summaries
    run_summary = {}
    for config in CONFIGS:
        results = config_results[config]
        if not results:
            continue
        run_summary[config] = {
            "pass_rate": calculate_stats([r["pass_rate"] for r in results]),
            "time_seconds": calculate_stats([r["time_seconds"] for r in results]),
            "tokens": calculate_stats([r["tokens"] for r in results]),
        }

    # Delta
    configs_present = [c for c in CONFIGS if c in run_summary]
    if len(configs_present) == 2:
        a, b = configs_present
        delta_pr = run_summary[a]["pass_rate"]["mean"] - run_summary[b]["pass_rate"]["mean"]
        delta_time = run_summary[a]["time_seconds"]["mean"] - run_summary[b]["time_seconds"]["mean"]
        delta_tokens = run_summary[a]["tokens"]["mean"] - run_summary[b]["tokens"]["mean"]
        run_summary["delta"] = {
            "pass_rate": f"{delta_pr:+.2f}",
            "time_seconds": f"{delta_time:+.1f}",
            "tokens": f"{delta_tokens:+.0f}",
        }

    # Read run config
    run_config_path = run_dir / "run-config.json"
    run_config = (
        json.loads(run_config_path.read_text()) if run_config_path.exists() else {}
    )

    benchmark = {
        "metadata": {
            "skill_name": "deephaven-core-query-writing",
            "skill_path": str(EVALS_DIR.parent.parent / "skills" / "deephaven-core-query-writing"),
            "executor_model": run_config.get("model", "default"),
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "evals_run": sorted(set(r["eval_id"] for r in runs)),
            "runs_per_configuration": 1,
        },
        "runs": runs,
        "run_summary": run_summary,
        "notes": [],
    }

    # Write outputs
    (run_dir / "benchmark.json").write_text(json.dumps(benchmark, indent=2))

    # Generate markdown summary
    lines = [
        f"# Benchmark: deephaven-core-query-writing",
        f"**Run ID:** {args.run_id}",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d')}",
        f"**Model:** {run_config.get('model', 'default')}",
        "",
    ]

    if len(configs_present) == 2:
        a_pr = run_summary[configs_present[0]]["pass_rate"]
        b_pr = run_summary[configs_present[1]]["pass_rate"]
        delta = run_summary.get("delta", {})
        lines.extend([
            "## Summary",
            "",
            f"| Metric | With Skill | Without Skill | Delta |",
            f"|--------|-----------|---------------|-------|",
            f"| Pass Rate | {a_pr['mean']*100:.0f}% | {b_pr['mean']*100:.0f}% | {delta.get('pass_rate', '—')} |",
            "",
        ])

    lines.append("## Per-Eval Results")
    lines.append("")
    lines.append("| Eval | Config | Passed | Total | Rate |")
    lines.append("|------|--------|--------|-------|------|")
    for r in runs:
        res = r["result"]
        lines.append(
            f"| {r['eval_name']} | {r['configuration']} | "
            f"{res['passed']} | {res['total']} | {res['pass_rate']:.0%} |"
        )

    (run_dir / "benchmark.md").write_text("\n".join(lines))

    console.print(f"[green]Generated:[/green] {run_dir / 'benchmark.json'}")
    console.print(f"[green]Generated:[/green] {run_dir / 'benchmark.md'}")

    for config in configs_present:
        pr = run_summary[config]["pass_rate"]["mean"]
        label = config.replace("_", " ").title()
        console.print(f"  {label}: {pr*100:.0f}% pass rate")
    if "delta" in run_summary:
        console.print(f"  Delta: {run_summary['delta']['pass_rate']}")


if __name__ == "__main__":
    main()
