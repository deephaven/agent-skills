"""Cross-eval analysis and comparison.

Reads metrics.json files from a run and generates aggregate reports:
- aggregate-metrics.json: cross-eval aggregation
- failure-modes.md: failure mode analysis ranked by frequency
- eval-results.md: summary table

Usage:
    uv run analyze-evals --run-id RUN_ID
    uv run analyze-evals --run-id RUN_ID --compare OTHER_RUN_ID
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

from rich.console import Console

console = Console()

TOOLS_DIR = Path(__file__).resolve().parent
EVALS_RUNS_DIR = TOOLS_DIR / "evals" / "runs"


def load_run_metrics(run_dir: Path) -> list[dict]:
    """Load all metrics.json files from a run directory."""
    metrics = []
    for eval_dir in sorted(run_dir.iterdir()):
        if not eval_dir.is_dir():
            continue
        mf = eval_dir / "metrics.json"
        if mf.exists():
            metrics.append(json.loads(mf.read_text()))
    return metrics


def load_run_config(run_dir: Path) -> dict:
    """Load the run configuration."""
    config_path = run_dir / "run-config.json"
    if config_path.exists():
        return json.loads(config_path.read_text())
    return {}


def load_playwright_results(run_dir: Path) -> list[dict]:
    """Load all playwright-results.json files from a run directory."""
    results = []
    for eval_dir in sorted(run_dir.iterdir()):
        if not eval_dir.is_dir():
            continue
        pr = eval_dir / "playwright-results.json"
        if pr.exists():
            data = json.loads(pr.read_text())
            data["_eval_name"] = eval_dir.name
            results.append(data)
    return results


def load_transcripts(run_dir: Path) -> dict[str, str]:
    """Load transcript.md files from a run directory, keyed by eval name."""
    transcripts = {}
    for eval_dir in sorted(run_dir.iterdir()):
        if not eval_dir.is_dir():
            continue
        tf = eval_dir / "transcript.md"
        if tf.exists():
            transcripts[eval_dir.name] = tf.read_text()
    return transcripts


def load_eval_results(run_dir: Path) -> list[dict]:
    """Load eval-result.json files from a run directory."""
    results = []
    for eval_dir in sorted(run_dir.iterdir()):
        if not eval_dir.is_dir():
            continue
        er = eval_dir / "eval-result.json"
        if er.exists():
            results.append(json.loads(er.read_text()))
    return results


def aggregate_playwright_results(pw_results: list[dict]) -> dict:
    """Compute aggregate Playwright test metrics."""
    if not pw_results:
        return {}

    n = len(pw_results)
    load_errors = sum(
        1 for r in pw_results
        if not r.get("initial_load", {}).get("success", True)
    )

    total_components = 0
    total_tested = 0
    total_passed = 0
    total_failed = 0

    # Collect all console error types
    runtime_errors: dict[str, int] = {}
    interaction_failures: list[dict] = []

    for r in pw_results:
        summary = r.get("summary", {})
        total_components += summary.get("total_components", 0)
        total_tested += summary.get("tested", 0)
        total_passed += summary.get("passed", 0)
        total_failed += summary.get("failed", 0)

        # Collect console errors
        for err in r.get("initial_load", {}).get("console_errors", []):
            runtime_errors[err] = runtime_errors.get(err, 0) + 1

        for test in r.get("component_tests", []):
            for err in test.get("console_errors", []):
                runtime_errors[err] = runtime_errors.get(err, 0) + 1
            if test.get("result") == "fail":
                interaction_failures.append({
                    "eval": r.get("_eval_name", r.get("eval_name", "unknown")),
                    "component": test.get("component"),
                    "type": test.get("type"),
                    "action": test.get("action"),
                    "error": test.get("error", ""),
                })

    return {
        "dashboards_tested": n,
        "initial_load_error_rate": round(load_errors / n, 2) if n else 0,
        "component_coverage": {
            "total_components": total_components,
            "tested": total_tested,
            "passed": total_passed,
            "failed": total_failed,
            "coverage_pct": round(total_tested / total_components * 100, 1) if total_components else 0,
            "pass_rate": round(total_passed / total_tested, 2) if total_tested else 0,
        },
        "runtime_errors": dict(sorted(runtime_errors.items(), key=lambda x: -x[1])[:10]),
        "interaction_failures": interaction_failures[:20],
    }


def aggregate_metrics(metrics: list[dict], config: dict) -> dict:
    """Compute aggregate metrics across all evals in a run."""
    if not metrics:
        return {}

    n = len(metrics)

    # Token aggregation
    token_fields = [
        "total_input_tokens", "total_output_tokens",
        "total_cache_read_tokens", "total_cache_creation_5m_tokens",
        "total_cache_creation_1h_tokens", "estimated_cost_usd",
    ]
    token_agg = {}
    for field in token_fields:
        values = [m["token_usage"].get(field, 0) for m in metrics if "token_usage" in m]
        token_agg[f"avg_{field}"] = round(mean(values), 2) if values else 0
        token_agg[f"total_{field}"] = round(sum(values), 2) if values else 0

    # Tool aggregation
    all_tools: dict[str, dict] = {}
    for m in metrics:
        for tool_name, tm in m.get("tool_metrics", {}).items():
            if tool_name not in all_tools:
                all_tools[tool_name] = {
                    "total_invocations": 0,
                    "total_success": 0,
                    "total_errors": 0,
                    "all_durations_ms": [],
                }
            at = all_tools[tool_name]
            at["total_invocations"] += tm["invocation_count"]
            at["total_success"] += tm["success_count"]
            at["total_errors"] += tm["error_count"]
            at["all_durations_ms"].extend(tm.get("durations_ms", []))

    tool_agg = {}
    for name, at in all_tools.items():
        total = at["total_invocations"]
        tool_agg[name] = {
            "total_invocations": total,
            "avg_per_eval": round(total / n, 1),
            "overall_success_rate": round(at["total_success"] / total, 2) if total else 0,
            "avg_duration_ms": round(mean(at["all_durations_ms"])) if at["all_durations_ms"] else 0,
        }

    # Error frequency
    error_counts: dict[str, int] = {}
    for m in metrics:
        # De-duplicate error types per eval (count each type once per eval)
        seen_types = set()
        for err in m.get("error_metrics", {}).get("errors", []):
            et = err.get("error_type", "Unknown")
            seen_types.add(et)
        for et in seen_types:
            error_counts[et] = error_counts.get(et, 0) + 1

    error_freq = {
        et: {"count": c, "pct": round(c / n, 2)}
        for et, c in sorted(error_counts.items(), key=lambda x: -x[1])
    }

    # Script attempt stats
    attempts = [
        m["script_attempts"]["total_attempts"]
        for m in metrics if "script_attempts" in m
    ]
    first_success = [
        m["script_attempts"]["first_success_attempt"]
        for m in metrics
        if "script_attempts" in m and m["script_attempts"]["first_success_attempt"] is not None
    ]
    success_count = len(first_success)
    first_try_count = sum(1 for a in first_success if a == 1)

    # Thinking patterns
    thinking_seqs = [m["thinking_metrics"]["total_thinking_sequences"] for m in metrics if "thinking_metrics" in m]
    thinking_words = [m["thinking_metrics"]["total_thinking_words"] for m in metrics if "thinking_metrics" in m]

    # Duration
    durations = [m["duration_seconds"] for m in metrics if "duration_seconds" in m]

    # Skill file read tracking
    skill_read_stats: dict[str, int] = {}  # path -> how many evals read it
    evals_reading_skills = 0
    for m in metrics:
        fr = m.get("files_read", {})
        skill_files = fr.get("skill_files_read", [])
        if skill_files:
            evals_reading_skills += 1
        for path in skill_files:
            # Normalize to just the filename for aggregation
            basename = path.rsplit("/", 1)[-1] if "/" in path else path
            skill_read_stats[basename] = skill_read_stats.get(basename, 0) + 1

    return {
        "run_metadata": {
            "run_id": config.get("run_id", "unknown"),
            "date": config.get("start_time", datetime.now(timezone.utc).isoformat())[:10],
            "model": config.get("model", "unknown"),
            "with_skills": config.get("with_skills", False),
            "total_evals": n,
        },
        "summary": {
            "success_rate": round(success_count / n, 2) if n else 0,
            "avg_attempts": round(mean(attempts), 1) if attempts else 0,
            "median_attempts": median(attempts) if attempts else 0,
            "first_try_success_rate": round(first_try_count / n, 2) if n else 0,
            "avg_duration_seconds": round(mean(durations), 1) if durations else 0,
            "avg_total_tokens": round(mean(
                m["token_usage"]["total_input_tokens"] + m["token_usage"]["total_output_tokens"]
                for m in metrics if "token_usage" in m
            )) if metrics else 0,
            "avg_cost_usd": token_agg.get("avg_estimated_cost_usd", 0),
            "total_cost_usd": token_agg.get("total_estimated_cost_usd", 0),
        },
        "token_usage_aggregate": token_agg,
        "tool_usage_aggregate": tool_agg,
        "error_frequency": error_freq,
        "thinking_patterns": {
            "avg_thinking_sequences_per_eval": round(mean(thinking_seqs), 1) if thinking_seqs else 0,
            "avg_thinking_words_per_eval": round(mean(thinking_words)) if thinking_words else 0,
        },
        "skill_file_reads": {
            "evals_reading_any_skill": evals_reading_skills,
            "evals_reading_any_skill_pct": round(evals_reading_skills / n, 2) if n else 0,
            "files_read_frequency": dict(sorted(skill_read_stats.items(), key=lambda x: -x[1])),
        },
    }


def generate_failure_modes_report(metrics: list[dict], config: dict) -> str:
    """Generate a markdown report of failure modes."""
    import re

    def _summarize_error(raw: str) -> str:
        """Extract a meaningful one-line summary from a raw error message."""
        matches = re.findall(r"(\w+(?:Error|Exception|Warning): .+?)(?:\n|$)", raw)
        if matches:
            return matches[-1].strip()[:200]
        match = re.search(r"(?:exit code \d+.*)", raw, re.IGNORECASE)
        if match:
            return match.group(0).strip()[:200]
        for line in raw.splitlines():
            line = line.strip()
            if line and not line.startswith("Traceback"):
                return line[:200]
        return raw[:200]

    lines: list[str] = []
    n = len(metrics)
    skill_mode = "With-Skill" if config.get("with_skills") else "No-Skill"

    lines.append(f"# Failure Mode Analysis — {skill_mode} Eval Run")
    lines.append(f"**Run ID:** {config.get('run_id', 'unknown')}")
    lines.append(f"**Date:** {config.get('start_time', '')[:10]}")
    lines.append(f"**Model:** {config.get('model', 'unknown')}")
    lines.append(f"**Total Evals:** {n}")
    lines.append("")

    # Collect all errors with context
    error_groups: dict[str, list[dict]] = {}
    for m in metrics:
        eval_name = m.get("eval_name", "unknown")
        for err in m.get("error_metrics", {}).get("errors", []):
            et = err.get("error_type", "Unknown")
            if et not in error_groups:
                error_groups[et] = []
            raw_msg = err.get("message", "")
            summary_msg = _summarize_error(raw_msg)
            error_groups[et].append({
                "eval": eval_name,
                "turn": err.get("turn"),
                "tool": err.get("tool"),
                "message": raw_msg[:500],
                "summary": summary_msg,
                "recovered": err.get("recovered", False),
                "recovery_turns": err.get("recovery_turns", 0),
            })

    # Count affected evals per error type (de-duplicated)
    error_eval_counts: dict[str, set[str]] = {}
    for et, errs in error_groups.items():
        error_eval_counts[et] = {e["eval"] for e in errs}

    # Sort by frequency
    ranked = sorted(
        error_groups.items(),
        key=lambda x: len(error_eval_counts[x[0]]),
        reverse=True,
    )

    lines.append("## Failure Mode Rankings")
    lines.append("")
    lines.append("| Rank | Error Type | Frequency | Evals Affected | Avg Recovery Turns |")
    lines.append("|------|-----------|-----------|----------------|-------------------|")

    for i, (et, errs) in enumerate(ranked, 1):
        affected = len(error_eval_counts[et])
        pct = round(affected / n * 100) if n else 0
        recovery_turns = [e["recovery_turns"] for e in errs if e["recovered"]]
        avg_recovery = round(mean(recovery_turns), 1) if recovery_turns else "N/A"
        lines.append(f"| {i} | `{et}` | {pct}% | {affected}/{n} | {avg_recovery} |")

    lines.append("")

    # Detailed analysis per error type
    lines.append("## Detailed Analysis")
    lines.append("")

    for i, (et, errs) in enumerate(ranked, 1):
        affected_evals = sorted(error_eval_counts[et])
        lines.append(f"### {i}. `{et}` ({len(affected_evals)}/{n} evals)")
        lines.append("")
        lines.append("**Affected evals:**")
        for eval_name in affected_evals:
            lines.append(f"- {eval_name}")
        lines.append("")
        lines.append("**Example errors:**")
        for err in errs[:5]:
            lines.append(f"- [{err['eval']}] Turn {err['turn']}, {err['tool']}: `{err['summary']}`")
        lines.append("")

    return "\n".join(lines)


def generate_results_table(metrics: list[dict], config: dict) -> str:
    """Generate eval-results.md summary table."""
    lines: list[str] = []
    lines.append("# Eval Results")
    lines.append(f"**Run ID:** {config.get('run_id', 'unknown')}")
    lines.append(f"**Date:** {config.get('start_time', '')[:10]}")
    lines.append(f"**Model:** {config.get('model', 'unknown')}")
    lines.append("")

    lines.append("| Dataset | Success | Attempts | First Try | Duration | Cost | Errors |")
    lines.append("|---------|---------|----------|-----------|----------|------|--------|")

    total_success = 0
    total_attempts = 0
    total_cost = 0.0

    for m in sorted(metrics, key=lambda x: x.get("eval_name", "")):
        name = m.get("eval_name", "unknown")
        sa = m.get("script_attempts", {})
        first_success = sa.get("first_success_attempt")
        attempts = sa.get("total_attempts", 0)
        success = first_success is not None
        first_try = first_success == 1 if first_success else False
        duration = m.get("duration_seconds", 0)
        cost = m.get("token_usage", {}).get("estimated_cost_usd", 0)
        n_errors = m.get("error_metrics", {}).get("total_errors", 0)

        status = "PASS" if success else "FAIL"
        ft = "Yes" if first_try else "No"

        lines.append(
            f"| {name} | {status} | {attempts} | {ft} | {duration:.0f}s | ${cost:.2f} | {n_errors} |"
        )

        if success:
            total_success += 1
        total_attempts += attempts
        total_cost += cost

    n = len(metrics)
    lines.append("")
    lines.append("## Aggregate Stats")
    lines.append(f"- **Total evals:** {n}")
    lines.append(f"- **Success rate:** {total_success}/{n} ({round(total_success/n*100) if n else 0}%)")
    lines.append(f"- **Average attempts:** {round(total_attempts/n, 1) if n else 0}")
    lines.append(f"- **Estimated API cost:** ${total_cost:.2f}")

    return "\n".join(lines)


def generate_comparison_report(
    run1_dir: Path, run2_dir: Path,
    metrics1: list[dict], metrics2: list[dict],
    config1: dict, config2: dict,
) -> str:
    """Generate a comparison report between two runs."""
    agg1 = aggregate_metrics(metrics1, config1)
    agg2 = aggregate_metrics(metrics2, config2)

    s1 = agg1.get("summary", {})
    s2 = agg2.get("summary", {})

    label1 = config1.get("run_id", "Run 1")
    label2 = config2.get("run_id", "Run 2")

    lines: list[str] = []
    lines.append("# Eval Run Comparison")
    lines.append("")
    lines.append(f"| Metric | {label1} | {label2} | Delta |")
    lines.append("|--------|---------|---------|-------|")

    comparisons = [
        ("Success rate", "success_rate", "%", 100),
        ("First-try success", "first_try_success_rate", "%", 100),
        ("Avg attempts", "avg_attempts", "", 1),
        ("Avg duration (s)", "avg_duration_seconds", "s", 1),
        ("Avg cost", "avg_cost_usd", "$", 1),
        ("Avg tokens", "avg_total_tokens", "", 1),
    ]

    for label, key, unit, mult in comparisons:
        v1 = s1.get(key, 0) * mult
        v2 = s2.get(key, 0) * mult
        delta = v2 - v1
        sign = "+" if delta > 0 else ""
        if unit == "$":
            lines.append(f"| {label} | ${v1:.2f} | ${v2:.2f} | {sign}${delta:.2f} |")
        elif unit == "%":
            lines.append(f"| {label} | {v1:.0f}% | {v2:.0f}% | {sign}{delta:.0f}pp |")
        else:
            lines.append(f"| {label} | {v1:.1f}{unit} | {v2:.1f}{unit} | {sign}{delta:.1f} |")

    # Error frequency comparison
    lines.append("")
    lines.append("## Error Frequency Comparison")
    lines.append("")

    ef1 = agg1.get("error_frequency", {})
    ef2 = agg2.get("error_frequency", {})
    all_errors = sorted(set(ef1.keys()) | set(ef2.keys()))

    if all_errors:
        lines.append(f"| Error Type | {label1} | {label2} | Resolved? |")
        lines.append("|-----------|---------|---------|-----------|")
        for et in all_errors:
            p1 = ef1.get(et, {}).get("pct", 0) * 100
            p2 = ef2.get(et, {}).get("pct", 0) * 100
            resolved = "Yes" if p2 < p1 * 0.5 else ("Partial" if p2 < p1 else "No")
            lines.append(f"| `{et}` | {p1:.0f}% | {p2:.0f}% | {resolved} |")

    return "\n".join(lines)


def aggregate_phase_completion(run_dir: Path) -> dict:
    """Compute phase completion stats from eval-result.json files."""
    eval_results = load_eval_results(run_dir)
    if not eval_results:
        return {}

    n = len(eval_results)
    all_complete = 0
    phase_counts: dict[int, int] = {}  # phase -> how many evals completed it
    incomplete_evals: list[dict] = []

    for er in eval_results:
        completed = er.get("phases_completed", [])
        missing = er.get("phases_missing", [])

        # If no phase tracking data, fall back to checking files
        if not completed and not missing:
            eval_dir = run_dir / er.get("eval_name", "")
            if eval_dir.is_dir():
                from run_evals import check_phase_completion
                phases = check_phase_completion(eval_dir)
                completed = phases["completed"]
                missing = phases["missing"]

        if not missing:
            all_complete += 1

        for p in completed:
            phase_counts[p] = phase_counts.get(p, 0) + 1

        if missing:
            incomplete_evals.append({
                "eval": er.get("eval_name", "unknown"),
                "completed": completed,
                "missing": missing,
                "resume_attempts": er.get("resume_attempts", 0),
            })

    return {
        "total_evals": n,
        "all_phases_complete": all_complete,
        "completion_rate": round(all_complete / n, 2) if n else 0,
        "phase_completion_counts": dict(sorted(phase_counts.items())),
        "incomplete_evals": incomplete_evals,
    }


def analyze_run(run_dir: Path):
    """Analyze a single run and write reports."""
    config = load_run_config(run_dir)
    metrics = load_run_metrics(run_dir)

    if not metrics:
        console.print(f"[red]No metrics.json files found in {run_dir}[/red]")
        console.print("[dim]Run parse stage first: uv run run-evals --stage parse --run-id ...[/dim]")
        return

    console.print(f"  Analyzing {len(metrics)} evals...")

    # Aggregate metrics
    agg = aggregate_metrics(metrics, config)

    # Phase completion (from eval-result.json files)
    phase_stats = aggregate_phase_completion(run_dir)
    if phase_stats:
        agg["phase_completion"] = phase_stats

    # Playwright results (if available)
    pw_results = load_playwright_results(run_dir)
    if pw_results:
        agg["playwright"] = aggregate_playwright_results(pw_results)
        console.print(f"  Including Playwright results from {len(pw_results)} dashboards")

    (run_dir / "aggregate-metrics.json").write_text(json.dumps(agg, indent=2))

    # Failure modes
    fm = generate_failure_modes_report(metrics, config)
    (run_dir / "failure-modes.md").write_text(fm)

    # Results table
    rt = generate_results_table(metrics, config)
    (run_dir / "eval-results.md").write_text(rt)

    reports = ["aggregate-metrics.json", "failure-modes.md", "eval-results.md"]
    console.print(f"  [green]Wrote:[/green] {', '.join(reports)}")

    # Print summary
    s = agg.get("summary", {})
    console.print(f"\n  Success rate: {s.get('success_rate', 0)*100:.0f}%")
    console.print(f"  Avg attempts: {s.get('avg_attempts', 0):.1f}")
    console.print(f"  Estimated API cost: ${s.get('total_cost_usd', 0):.2f}")

    if phase_stats:
        total = phase_stats["total_evals"]
        complete = phase_stats["all_phases_complete"]
        console.print(f"  Phase completion: {complete}/{total} evals completed all phases")
        if phase_stats["incomplete_evals"]:
            for ie in phase_stats["incomplete_evals"]:
                console.print(f"    [yellow]{ie['eval']}[/yellow]: missing phases {ie['missing']}")

    if "playwright" in agg:
        pw = agg["playwright"]
        cc = pw.get("component_coverage", {})
        console.print(f"\n  Playwright: {cc.get('tested', 0)} components tested, "
                      f"{cc.get('passed', 0)} passed, {cc.get('failed', 0)} failed")


def compare_runs(run1_dir: Path, run2_dir: Path):
    """Compare two runs and write a comparison report."""
    config1 = load_run_config(run1_dir)
    config2 = load_run_config(run2_dir)
    metrics1 = load_run_metrics(run1_dir)
    metrics2 = load_run_metrics(run2_dir)

    if not metrics1 or not metrics2:
        console.print("[red]Both runs must have metrics.json files. Run parse stage first.[/red]")
        return

    report = generate_comparison_report(run1_dir, run2_dir, metrics1, metrics2, config1, config2)

    # Write to the second run's directory
    (run2_dir / "comparison.md").write_text(report)
    console.print(f"  [green]Wrote:[/green] {run2_dir / 'comparison.md'}")
    console.print(report)


def main():
    parser = argparse.ArgumentParser(description="Analyze eval run results")
    parser.add_argument("--run-id", required=True, help="Run ID to analyze")
    parser.add_argument("--compare", metavar="RUN_ID", help="Compare against another run")

    args = parser.parse_args()

    run_dir = EVALS_RUNS_DIR / args.run_id
    if not run_dir.exists():
        console.print(f"[red]Run not found: {run_dir}[/red]")
        sys.exit(1)

    if args.compare:
        compare_dir = EVALS_RUNS_DIR / args.compare
        if not compare_dir.exists():
            console.print(f"[red]Comparison run not found: {compare_dir}[/red]")
            sys.exit(1)
        compare_runs(run_dir, compare_dir)
    else:
        analyze_run(run_dir)


if __name__ == "__main__":
    main()
