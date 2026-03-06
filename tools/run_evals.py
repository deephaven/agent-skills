"""Eval pipeline orchestrator.

Runs eval datasets through claude -p, then parses session logs and generates
aggregate analysis. Each eval runs as a single claude -p session that handles
all phases (write → verify → test → fix → reflect).

Usage:
    uv run run-evals                              # run all stages for all datasets
    uv run run-evals --stage run                  # just run evals (no parse/analyze)
    uv run run-evals --stage parse --run-id X     # parse existing run
    uv run run-evals --stage analyze --run-id X   # analyze existing run
    uv run run-evals --stage aggregate --run-id X # LLM-generated aggregate recommendations
    uv run run-evals --datasets ds1 ds2           # specific datasets only
    uv run run-evals --parallel 5                 # concurrency level
    uv run run-evals --model sonnet               # override model
    uv run run-evals --with-skills                # inject skill content into prompt
    uv run run-evals --max-fix-iterations 3       # limit fix loop iterations
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()

TOOLS_DIR = Path(__file__).resolve().parent
EVALS_DATA_DIR = TOOLS_DIR / "evals" / "data"
EVALS_RUNS_DIR = TOOLS_DIR / "evals" / "runs"
UNIFIED_PROMPT_TEMPLATE_PATH = TOOLS_DIR / "evals_unified_prompt.md"
AGGREGATE_PROMPT_TEMPLATE_PATH = TOOLS_DIR / "evals_aggregate_prompt.md"
SKILL_DIR = TOOLS_DIR.parent / "skills" / "deephaven-core-query-writing"

# Deterministic UUID namespace for session IDs
EVAL_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

DEFAULT_PARALLEL = 3
DEFAULT_MAX_TURNS = 150
DEFAULT_SESSION_TIMEOUT = 600  # 10 minutes per claude -p attempt
DEFAULT_MAX_RESUME_ATTEMPTS = 2
SCRIPT_NAME = "no-skill-script.py"


def find_session_log(session_id: str) -> Path | None:
    """Find the canonical JSONL session log by searching all project dirs.

    Claude Code stores logs under ~/.claude/projects/{encoded-cwd}/.
    The encoded path depends on where `claude -p` was invoked from,
    which may differ from where this script runs. Search all project
    dirs for the session ID file.
    """
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.exists():
        return None

    filename = f"{session_id}.jsonl"
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        candidate = project_dir / filename
        if candidate.exists():
            return candidate

    return None


def discover_datasets() -> list[str]:
    """List all eval dataset directories."""
    if not EVALS_DATA_DIR.exists():
        console.print("[red]No eval data directory found. Run: uv run download-eval-data[/red]")
        sys.exit(1)
    datasets = sorted(
        d.name for d in EVALS_DATA_DIR.iterdir()
        if d.is_dir() and (d / "manifest.json").exists()
    )
    if not datasets:
        console.print("[red]No eval datasets found with manifest.json[/red]")
        sys.exit(1)
    return datasets


def generate_session_id(eval_name: str, run_id: str) -> str:
    """Generate a deterministic session ID for an eval."""
    return str(uuid.uuid5(EVAL_NAMESPACE, f"eval-{eval_name}-{run_id}"))


def generate_run_id() -> str:
    """Generate a run ID based on current timestamp."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def build_prompt(
    eval_name: str,
    output_dir: Path,
    with_skills: bool = False,
    max_fix_iterations: int = 3,
) -> str:
    """Build the unified prompt for a single eval invocation.

    Uses a single template with {SKILL_PREAMBLE} substitution:
    - No-skill: forbids reading skill files
    - With-skill: instructs agent to read SKILL.md first
    """
    template = UNIFIED_PROMPT_TEMPLATE_PATH.read_text()

    if with_skills:
        skill_path = SKILL_DIR / "SKILL.md"
        if not skill_path.exists():
            console.print(f"[yellow]Warning: skill file not found at {skill_path}[/yellow]")
        preamble = (
            f"## Step 0: Load the Deephaven Skill (MANDATORY FIRST STEP)\n\n"
            f"Before doing anything else, read the skill file at: {skill_path.resolve()}\n\n"
            f"This file contains a reference table listing topic-specific guides for Deephaven APIs "
            f"(joins, aggregations, UI, plotting, etc.). Based on the dataset and the dashboard you "
            f"plan to build, read whichever references are relevant to your task. Use your judgment — "
            f"you do NOT need to read every reference, only those that apply.\n\n"
            f"Do NOT skip this step. Do NOT guess Deephaven APIs from memory."
        )
    else:
        preamble = (
            "DO NOT look for or load any skill files. DO NOT read any SKILL.md or reference files. "
            "You only have the instructions in this prompt and your own knowledge."
        )

    data_dir = (EVALS_DATA_DIR / eval_name).resolve()
    script_name = SCRIPT_NAME

    prompt = template.replace("{SKILL_PREAMBLE}", preamble)
    prompt = prompt.replace("{DATA_DIR}", str(data_dir))
    prompt = prompt.replace("{OUTPUT_DIR}", str(output_dir.resolve()))
    prompt = prompt.replace("{EVAL_NAME}", eval_name)
    prompt = prompt.replace("{SCRIPT_NAME}", script_name)
    prompt = prompt.replace("{MAX_FIX_ITERATIONS}", str(max_fix_iterations))
    return prompt


# Expected output files per phase — used to detect incomplete sessions
PHASE_OUTPUT_FILES = {
    1: SCRIPT_NAME,
    4: "playwright-results.json",
    6: "skill-recommendations.md",
}


def check_phase_completion(output_dir: Path) -> dict:
    """Check which phases completed by looking for expected output files."""
    completed = []
    missing = []
    for phase, filename in sorted(PHASE_OUTPUT_FILES.items()):
        if (output_dir / filename).exists():
            completed.append(phase)
        else:
            missing.append(phase)
    return {"completed": completed, "missing": missing}


def build_resume_prompt(missing_phases: list[int], output_dir: Path) -> str:
    """Build a prompt to continue an interrupted eval session."""
    phases_str = ", ".join(str(p) for p in missing_phases)
    return (
        f"Your previous session was interrupted before completing all phases. "
        f"The following phases are still incomplete: {phases_str}. "
        f"Resume from where you left off. Do not restart completed phases. "
        f"The output directory is: {output_dir.resolve()}"
    )


async def _execute_claude(cmd: list[str], timeout: int, stdin_input: str | None = None) -> dict:
    """Run a claude -p subprocess with timeout. Returns execution info.

    When stdin_input is provided, the prompt is piped via stdin instead of
    appearing as a CLI argument. This prevents `pkill -f "dh serve"` (or
    similar) from matching the claude process itself — since the prompt
    text won't be visible in the process command line.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE if stdin_input else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    timed_out = False
    input_bytes = stdin_input.encode() if stdin_input else None
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=input_bytes), timeout=timeout,
        )
    except asyncio.TimeoutError:
        timed_out = True
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        stdout, stderr = b"", b""

    return {
        "returncode": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "timed_out": timed_out,
    }


def _parse_claude_output(stdout: bytes) -> dict:
    """Parse JSON output from claude -p into a normalized dict."""
    if not stdout:
        return {}
    try:
        claude_output = json.loads(stdout.decode())
        if isinstance(claude_output, list):
            merged = {}
            for item in claude_output:
                if isinstance(item, dict):
                    merged.update(item)
            return merged
        if isinstance(claude_output, dict):
            return claude_output
    except json.JSONDecodeError:
        pass
    return {}


async def run_single_eval(
    eval_name: str,
    run_id: str,
    output_dir: Path,
    model: str | None,
    with_skills: bool,
    max_fix_iterations: int,
    semaphore: asyncio.Semaphore,
    timeout: int = DEFAULT_SESSION_TIMEOUT,
    max_resume_attempts: int = DEFAULT_MAX_RESUME_ATTEMPTS,
) -> dict:
    """Run a single eval via claude -p, with auto-resume for incomplete phases."""
    async with semaphore:
        prefix = "eval-skill" if with_skills else "eval"
        session_id = str(uuid.uuid5(EVAL_NAMESPACE, f"{prefix}-{eval_name}-{run_id}"))
        output_dir.mkdir(parents=True, exist_ok=True)

        prompt = build_prompt(eval_name, output_dir, with_skills, max_fix_iterations)

        # Common args shared between initial run and resume attempts
        shared_args = [
            "--output-format", "json",
            "--max-turns", str(DEFAULT_MAX_TURNS),
            "--disallowedTools", "mcp__*",
            "--allowedTools", "Bash,Read,Write,Edit,Glob,Grep",
            "--verbose",
            "--dangerously-skip-permissions",
        ]
        if model:
            shared_args.extend(["--model", model])

        console.print(f"  [cyan]Starting[/cyan] {eval_name} (session: {session_id[:8]}...)")

        start_time = datetime.now(timezone.utc)
        result = {
            "eval_name": eval_name,
            "session_id": session_id,
            "start_time": start_time.isoformat(),
            "success": False,
            "error": None,
            "resume_attempts": 0,
            "phases_completed": [],
            "phases_missing": [],
        }

        # --- Initial run ---
        # Prompt is piped via stdin so it doesn't appear in the process
        # command line. This prevents `pkill -f "dh serve"` (run by the
        # agent inside its Bash tool) from matching the claude process.
        initial_cmd = [
            "claude", "-p",
            "--session-id", session_id,
            *shared_args,
        ]

        try:
            exec_result = await _execute_claude(initial_cmd, timeout, stdin_input=prompt)
            if exec_result["timed_out"]:
                console.print(f"  [yellow]Timeout[/yellow] {eval_name} ({timeout}s)")

            result["exit_code"] = exec_result["returncode"]
            if exec_result["timed_out"]:
                result["timed_out"] = True

            claude_parsed = _parse_claude_output(exec_result["stdout"])
            if claude_parsed:
                result["claude_session_id"] = claude_parsed.get("session_id")
                result["cost_usd"] = claude_parsed.get("cost_usd")
                result["num_turns"] = claude_parsed.get("num_turns")

            if exec_result["stderr"]:
                result["stderr"] = exec_result["stderr"].decode()[:2000]

            # Copy session log
            log_src = find_session_log(session_id)
            if log_src:
                shutil.copy2(log_src, output_dir / "raw.jsonl")
                result["session_log_copied"] = True
            else:
                result["session_log_copied"] = False

        except Exception as e:
            result["error"] = str(e)
            console.print(f"  [red]ERROR[/red] {eval_name}: {e}")

        # --- Resume loop for incomplete phases ---
        phases = check_phase_completion(output_dir)

        for attempt in range(1, max_resume_attempts + 1):
            if not phases["missing"]:
                break

            result["resume_attempts"] = attempt
            console.print(
                f"  [yellow]Resuming[/yellow] {eval_name} "
                f"(attempt {attempt}/{max_resume_attempts}, "
                f"missing phases: {phases['missing']})"
            )

            resume_prompt = build_resume_prompt(phases["missing"], output_dir)
            resume_cmd = [
                "claude", "-p",
                "--resume", session_id,
                *shared_args,
            ]

            try:
                exec_result = await _execute_claude(resume_cmd, timeout, stdin_input=resume_prompt)
                if exec_result["timed_out"]:
                    console.print(f"  [yellow]Timeout[/yellow] {eval_name} resume ({timeout}s)")

                # Update timing
                end_time = datetime.now(timezone.utc)
                result["end_time"] = end_time.isoformat()
                result["duration_seconds"] = (end_time - start_time).total_seconds()
                result["exit_code"] = exec_result["returncode"]

                # Accumulate cost from resume attempts
                claude_parsed = _parse_claude_output(exec_result["stdout"])
                if claude_parsed and claude_parsed.get("cost_usd"):
                    result["cost_usd"] = (result.get("cost_usd") or 0) + claude_parsed["cost_usd"]

                # Re-copy session log (it now includes resume content)
                log_src = find_session_log(session_id)
                if log_src:
                    shutil.copy2(log_src, output_dir / "raw.jsonl")

            except Exception as e:
                console.print(f"  [red]ERROR[/red] {eval_name} resume: {e}")
                break

            phases = check_phase_completion(output_dir)

        # --- Finalize ---
        end_time = datetime.now(timezone.utc)
        result["end_time"] = end_time.isoformat()
        result["duration_seconds"] = (end_time - start_time).total_seconds()

        phases = check_phase_completion(output_dir)
        result["phases_completed"] = phases["completed"]
        result["phases_missing"] = phases["missing"]
        result["success"] = not phases["missing"]

        if result["success"]:
            status = "[green]OK[/green]"
        elif phases["completed"]:
            status = "[yellow]PARTIAL[/yellow]"
        else:
            status = "[red]FAIL[/red]"

        dur = result.get("duration_seconds", 0)
        phases_str = ",".join(str(p) for p in phases["completed"]) or "none"
        resume_info = f", {result['resume_attempts']} resume(s)" if result["resume_attempts"] else ""
        console.print(f"  {status} {eval_name} ({dur:.0f}s, phases: {phases_str}{resume_info})")

        (output_dir / "eval-result.json").write_text(json.dumps(result, indent=2))
        return result


async def stage_run(
    datasets: list[str],
    run_id: str,
    parallel: int,
    model: str | None,
    with_skills: bool,
    skip_existing: bool,
    max_fix_iterations: int,
    timeout: int = DEFAULT_SESSION_TIMEOUT,
    max_resume_attempts: int = DEFAULT_MAX_RESUME_ATTEMPTS,
) -> list[dict]:
    """Run evals via claude -p."""
    run_dir = EVALS_RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Write run config
    config = {
        "run_id": run_id,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "model": model or "default",
        "with_skills": with_skills,
        "parallel": parallel,
        "max_fix_iterations": max_fix_iterations,
        "timeout": timeout,
        "max_resume_attempts": max_resume_attempts,
        "datasets": datasets,
    }
    (run_dir / "run-config.json").write_text(json.dumps(config, indent=2))

    semaphore = asyncio.Semaphore(parallel)
    tasks = []

    for ds in datasets:
        output_dir = run_dir / ds
        if skip_existing and (output_dir / "eval-result.json").exists():
            console.print(f"  [dim]Skipping {ds} (already exists)[/dim]")
            continue
        tasks.append(run_single_eval(
            ds, run_id, output_dir, model, with_skills, max_fix_iterations, semaphore,
            timeout, max_resume_attempts,
        ))

    if not tasks:
        console.print("[yellow]No evals to run (all skipped)[/yellow]")
        return []

    console.print(f"\n[bold]Running {len(tasks)} evals (parallel={parallel})...[/bold]\n")
    results = await asyncio.gather(*tasks)

    # Update run config with end time
    config["end_time"] = datetime.now(timezone.utc).isoformat()
    config["results_summary"] = {
        "total": len(results),
        "succeeded": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
    }
    (run_dir / "run-config.json").write_text(json.dumps(config, indent=2))

    return results


def stage_parse(run_id: str, datasets: list[str] | None = None):
    """Parse session logs for a run."""
    from parse_session import parse_session_log

    run_dir = EVALS_RUNS_DIR / run_id
    if not run_dir.exists():
        console.print(f"[red]Run directory not found: {run_dir}[/red]")
        sys.exit(1)

    eval_dirs = sorted(d for d in run_dir.iterdir() if d.is_dir())
    if datasets:
        eval_dirs = [d for d in eval_dirs if d.name in datasets]

    for eval_dir in eval_dirs:
        raw_jsonl = eval_dir / "raw.jsonl"
        if not raw_jsonl.exists():
            console.print(f"  [yellow]No raw.jsonl for {eval_dir.name}, skipping[/yellow]")
            continue
        console.print(f"  Parsing {eval_dir.name}...")
        parse_session_log(raw_jsonl, eval_dir)

    console.print(f"[green]Parsed {len(eval_dirs)} sessions[/green]")


def stage_analyze(run_id: str, compare_run_id: str | None = None):
    """Analyze metrics for a run."""
    from analyze_evals import analyze_run, compare_runs

    if compare_run_id:
        compare_runs(
            EVALS_RUNS_DIR / run_id,
            EVALS_RUNS_DIR / compare_run_id,
        )
    else:
        analyze_run(EVALS_RUNS_DIR / run_id)


async def stage_aggregate_recommendations(run_id: str, model: str | None):
    """Invoke claude -p to generate aggregate skill recommendations.

    Reads all per-eval skill-recommendations.md files and deterministic
    reports, then writes a top-level skill-recommendations.md.
    """
    run_dir = EVALS_RUNS_DIR / run_id
    if not run_dir.exists():
        console.print(f"[red]Run directory not found: {run_dir}[/red]")
        sys.exit(1)

    # Find all per-eval recommendation files
    rec_files = []
    for eval_dir in sorted(run_dir.iterdir()):
        if not eval_dir.is_dir():
            continue
        rec = eval_dir / "skill-recommendations.md"
        if rec.exists():
            rec_files.append(str(rec.resolve()))

    if not rec_files:
        console.print("[yellow]No per-eval skill-recommendations.md files found. "
                      "Run the eval stage first.[/yellow]")
        return

    # Load run config for skill mode
    config_path = run_dir / "run-config.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    skill_mode = "With-Skill" if config.get("with_skills") else "No-Skill"

    # Build prompt from template
    template = AGGREGATE_PROMPT_TEMPLATE_PATH.read_text()
    rec_list = "\n".join(f"- `{f}`" for f in rec_files)
    prompt = template.replace("{RECOMMENDATION_FILES_LIST}", rec_list)
    prompt = prompt.replace("{RUN_DIR}", str(run_dir.resolve()))
    prompt = prompt.replace("{SKILL_MODE}", skill_mode)

    session_id = str(uuid.uuid5(EVAL_NAMESPACE, f"aggregate-{run_id}"))

    cmd = [
        "claude", "-p",
        "--session-id", session_id,
        "--output-format", "json",
        "--max-turns", "50",
        "--disallowedTools", "mcp__*",
        "--allowedTools", "Bash,Read,Write,Edit,Glob,Grep",
        "--verbose",
        "--dangerously-skip-permissions",
    ]
    if model:
        cmd.extend(["--model", model])

    console.print(f"  [cyan]Aggregating recommendations[/cyan] from {len(rec_files)} evals...")

    try:
        exec_result = await _execute_claude(cmd, timeout=300, stdin_input=prompt)

        if exec_result["returncode"] == 0:
            console.print("[green]Aggregate recommendations written[/green]")
        else:
            console.print(f"[red]Aggregate step failed (exit {exec_result['returncode']})[/red]")
            if exec_result["stderr"]:
                console.print(f"  stderr: {exec_result['stderr'].decode()[:500]}")

    except Exception as e:
        console.print(f"[red]ERROR[/red] Aggregate step: {e}")


def print_results_table(results: list[dict]):
    """Print a summary table of eval results."""
    table = Table(title="Eval Results")
    table.add_column("Dataset", style="cyan")
    table.add_column("Status")
    table.add_column("Phases")
    table.add_column("Resumes", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("Turns", justify="right")

    for r in results:
        if r["success"]:
            status = "[green]PASS[/green]"
        elif r.get("phases_completed"):
            status = "[yellow]PARTIAL[/yellow]"
        else:
            status = "[red]FAIL[/red]"

        completed = r.get("phases_completed", [])
        missing = r.get("phases_missing", [])
        if not missing:
            phases = "[green]1,4,6[/green]"
        elif completed:
            parts = []
            for p in sorted(set(completed) | set(missing)):
                if p in completed:
                    parts.append(f"[green]{p}[/green]")
                else:
                    parts.append(f"[red]{p}[/red]")
            phases = ",".join(parts)
        else:
            phases = "[red]none[/red]"

        dur = f"{r.get('duration_seconds', 0):.0f}s"
        turns = str(r.get("num_turns", "?"))
        resumes = str(r.get("resume_attempts", 0))
        table.add_row(r["eval_name"], status, phases, resumes, dur, turns)

    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Eval pipeline orchestrator")
    parser.add_argument("--datasets", nargs="*", help="Specific datasets to run (default: all)")
    parser.add_argument("--parallel", type=int, default=DEFAULT_PARALLEL, help="Concurrency level")
    parser.add_argument("--skip-existing", action="store_true", help="Skip datasets with existing results")
    parser.add_argument(
        "--stage",
        choices=["run", "parse", "analyze", "aggregate", "all"],
        default="all",
        help="Pipeline stage to execute",
    )
    parser.add_argument("--model", help="Model override (e.g., sonnet, opus)")
    parser.add_argument("--run-id", help="Run ID (auto-generated if not specified)")
    parser.add_argument("--with-skills", action="store_true", help="Inject skill content into prompt")
    parser.add_argument("--compare", metavar="RUN_ID", help="Compare against another run (with --stage analyze)")
    parser.add_argument("--max-fix-iterations", type=int, default=3, help="Max fix loop iterations per eval (default: 3)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_SESSION_TIMEOUT, help=f"Timeout per claude -p attempt in seconds (default: {DEFAULT_SESSION_TIMEOUT})")
    parser.add_argument("--max-resume-attempts", type=int, default=DEFAULT_MAX_RESUME_ATTEMPTS, help=f"Max resume attempts for incomplete phases (default: {DEFAULT_MAX_RESUME_ATTEMPTS})")
    parser.add_argument("-n", "--count", type=int, help="Limit to first N datasets (by name order)")

    args = parser.parse_args()

    # Discover or validate datasets
    all_datasets = discover_datasets()
    datasets = args.datasets if args.datasets else all_datasets
    if args.count and not args.datasets:
        datasets = datasets[:args.count]
    invalid = set(datasets) - set(all_datasets)
    if invalid:
        console.print(f"[red]Unknown datasets: {invalid}[/red]")
        console.print(f"Available: {all_datasets}")
        sys.exit(1)

    run_id = args.run_id or generate_run_id()
    console.print(f"[bold]Run ID:[/bold] {run_id}")
    console.print(f"[bold]Datasets:[/bold] {len(datasets)}")
    console.print(f"[bold]Stage:[/bold] {args.stage}")

    if args.stage in ("run", "all"):
        results = asyncio.run(stage_run(
            datasets, run_id, args.parallel, args.model, args.with_skills,
            args.skip_existing, args.max_fix_iterations,
            args.timeout, args.max_resume_attempts,
        ))
        if results:
            print_results_table(results)

    if args.stage in ("parse", "all"):
        console.print("\n[bold]Parsing session logs...[/bold]")
        stage_parse(run_id, args.datasets)

    if args.stage in ("analyze", "all"):
        console.print("\n[bold]Analyzing results...[/bold]")
        stage_analyze(run_id, args.compare)

    if args.stage in ("aggregate", "all"):
        console.print("\n[bold]Aggregating skill recommendations...[/bold]")
        asyncio.run(stage_aggregate_recommendations(run_id, args.model))

    # Final status — warn about incomplete evals
    if args.stage in ("run", "all") and results:
        incomplete = [r for r in results if r.get("phases_missing")]
        if incomplete:
            names = ", ".join(r["eval_name"] for r in incomplete)
            console.print(
                f"\n[bold yellow]Warning:[/bold yellow] {len(incomplete)} eval(s) "
                f"did not complete all phases: {names}"
            )
            console.print(f"Results in: tools/evals/runs/{run_id}/")
        else:
            console.print(f"\n[bold green]Done.[/bold green] Results in: tools/evals/runs/{run_id}/")
    else:
        console.print(f"\n[bold green]Done.[/bold green] Results in: tools/evals/runs/{run_id}/")


if __name__ == "__main__":
    main()
