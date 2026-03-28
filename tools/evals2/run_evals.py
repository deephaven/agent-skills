"""Evals2 pipeline orchestrator.

Runs eval datasets through claude -p with and without the skill, then validates
outputs using dh render, parses session logs, and produces results compatible
with skill-creator's grading and viewer infrastructure.

Usage:
    uv run run-evals2                                # run all evals, both configs
    uv run run-evals2 --config with_skill            # only with-skill runs
    uv run run-evals2 --config without_skill         # only baseline runs
    uv run run-evals2 --evals 1 2 3                  # specific eval IDs
    uv run run-evals2 --parallel 5                   # concurrency level
    uv run run-evals2 --stage run                    # just run (no validate/parse)
    uv run run-evals2 --stage validate --run-id X    # validate existing run
    uv run run-evals2 --stage parse --run-id X       # parse existing run
    uv run run-evals2 --skip-existing                # resume interrupted run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()

TOOLS_DIR = Path(__file__).resolve().parent.parent  # tools/
EVALS2_DIR = Path(__file__).resolve().parent  # tools/evals2/
EVALS_DATA_DIR = TOOLS_DIR / "evals" / "data"
EVALS2_RUNS_DIR = EVALS2_DIR / "runs"
PROMPT_TEMPLATE_PATH = EVALS2_DIR / "prompt.md"
EVALS_JSON_PATH = EVALS2_DIR / "evals.json"
SKILL_DIR = TOOLS_DIR.parent / "skills" / "deephaven-core-query-writing"

# Import parse_session from sibling module
sys.path.insert(0, str(TOOLS_DIR))
from parse_session import parse_session_log  # noqa: E402

# Deterministic UUID namespace for session IDs
EVAL_NAMESPACE = uuid.UUID("b2c3d4e5-f6a7-8901-bcde-f12345678901")

DEFAULT_PARALLEL = 3
DEFAULT_MAX_TURNS = 100
DEFAULT_TIMEOUT = 600  # 10 minutes per claude -p attempt
CONFIGS = ["with_skill", "without_skill"]


def load_evals(eval_ids: list[int] | None = None) -> list[dict]:
    """Load eval definitions from evals.json."""
    data = json.loads(EVALS_JSON_PATH.read_text())
    evals = data["evals"]
    if eval_ids:
        evals = [e for e in evals if e["id"] in eval_ids]
    return evals


def build_prompt(eval_def: dict, output_dir: Path, config: str) -> str:
    """Build the eval prompt for a single run."""
    template = PROMPT_TEMPLATE_PATH.read_text()

    if config == "with_skill":
        preamble_path = EVALS2_DIR / "preamble-with-skill.md"
        skill_path = SKILL_DIR / "SKILL.md"
        preamble = preamble_path.read_text().replace("{SKILL_PATH}", str(skill_path.resolve()))
    else:
        preamble_path = EVALS2_DIR / "preamble-without-skill.md"
        preamble = preamble_path.read_text()

    task_prompt = eval_def["prompt"]

    prompt = template.replace("{SKILL_PREAMBLE}", preamble)
    prompt = prompt.replace("{TASK_PROMPT}", task_prompt)
    prompt = prompt.replace("{OUTPUT_DIR}", str(output_dir.resolve()))
    return prompt


def find_session_log(session_id: str) -> Path | None:
    """Find the JSONL session log by searching all project dirs."""
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


def delete_session_log(session_id: str) -> bool:
    """Delete a stale session log so claude -p won't resume it."""
    log_path = find_session_log(session_id)
    if log_path:
        log_path.unlink()
        return True
    return False


async def _execute_claude(cmd: list[str], timeout: int, stdin_input: str | None = None) -> dict:
    """Run a claude -p subprocess with timeout."""
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
    """Parse JSON output from claude -p."""
    if not stdout:
        return {}
    try:
        out = json.loads(stdout.decode())
        if isinstance(out, list):
            merged = {}
            for item in out:
                if isinstance(item, dict):
                    merged.update(item)
            return merged
        if isinstance(out, dict):
            return out
    except json.JSONDecodeError:
        pass
    return {}


async def run_single(
    eval_def: dict,
    config: str,
    run_dir: Path,
    model: str | None,
    semaphore: asyncio.Semaphore,
    timeout: int = DEFAULT_TIMEOUT,
    progress: list[int] | None = None,
    total: int = 0,
) -> dict:
    """Run a single eval+config via claude -p."""
    async with semaphore:
        eval_name = eval_def["name"]
        eval_id = eval_def["id"]

        # Output dir: runs/{run_id}/{eval_name}/{config}/run-1/outputs/
        outputs_dir = run_dir / eval_name / config / "run-1" / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)

        session_id = str(uuid.uuid5(
            EVAL_NAMESPACE, f"{eval_name}-{config}-{run_dir.name}"
        ))

        # Delete any stale session log so claude -p starts fresh
        # instead of resuming a previous (possibly broken) session.
        delete_session_log(session_id)

        prompt = build_prompt(eval_def, outputs_dir, config)

        cmd = [
            "claude", "-p",
            "--session-id", session_id,
            "--output-format", "json",
            "--max-turns", str(DEFAULT_MAX_TURNS),
            "--tools", "Bash,Read,Write,Edit,Glob,Grep",
            "--verbose",
            "--dangerously-skip-permissions",
            "--strict-mcp-config",
        ]
        if config == "without_skill":
            cmd.append("--disable-slash-commands")
        if model:
            cmd.extend(["--model", model])

        # Increment shared progress counter
        if progress is not None:
            progress[0] += 1
            idx = progress[0]
            counter = f"[dim][{idx}/{total}][/dim] "
        else:
            counter = ""

        console.print(
            f"  {counter}[cyan]Starting[/cyan] {eval_name} [{config}] "
            f"(session: {session_id[:8]}...)"
        )

        start_time = datetime.now(timezone.utc)
        result = {
            "eval_id": eval_id,
            "eval_name": eval_name,
            "configuration": config,
            "session_id": session_id,
            "start_time": start_time.isoformat(),
            "success": False,
            "error": None,
        }

        try:
            exec_result = await _execute_claude(cmd, timeout, stdin_input=prompt)
            if exec_result["timed_out"]:
                console.print(f"  [yellow]Timeout[/yellow] {eval_name} [{config}]")
                result["timed_out"] = True

            result["exit_code"] = exec_result["returncode"]

            claude_parsed = _parse_claude_output(exec_result["stdout"])
            if claude_parsed:
                result["cost_usd"] = claude_parsed.get("cost_usd")
                result["num_turns"] = claude_parsed.get("num_turns")

            if exec_result["stderr"]:
                result["stderr"] = exec_result["stderr"].decode()[:2000]

            # Copy session log
            log_src = find_session_log(session_id)
            if log_src:
                shutil.copy2(log_src, outputs_dir / "raw.jsonl")
                result["session_log_copied"] = True
            else:
                result["session_log_copied"] = False

            # Check if script was produced
            result["script_produced"] = (outputs_dir / "script.py").exists()
            result["success"] = result["script_produced"]

        except Exception as e:
            result["error"] = str(e)
            console.print(f"  [red]ERROR[/red] {eval_name} [{config}]: {e}")

        end_time = datetime.now(timezone.utc)
        result["end_time"] = end_time.isoformat()
        result["duration_seconds"] = (end_time - start_time).total_seconds()

        # Write eval_metadata.json (skill-creator format)
        # Written at both the eval level and the run level so the
        # skill-creator viewer can find the prompt (it checks run_dir
        # and run_dir.parent only).
        meta = {
            "eval_id": eval_id,
            "eval_name": eval_name,
            "prompt": eval_def["prompt"],
            "assertions": eval_def.get("expectations", []),
        }
        meta_dir = run_dir / eval_name
        (meta_dir / "eval_metadata.json").write_text(json.dumps(meta, indent=2))
        run_level_dir = run_dir / eval_name / config / "run-1"
        (run_level_dir / "eval_metadata.json").write_text(json.dumps(meta, indent=2))

        # Write timing.json (skill-creator format)
        timing_dir = run_dir / eval_name / config / "run-1"
        timing = {
            "total_tokens": claude_parsed.get("num_turns", 0) if claude_parsed else 0,
            "duration_ms": int(result["duration_seconds"] * 1000),
            "total_duration_seconds": result["duration_seconds"],
        }
        (timing_dir / "timing.json").write_text(json.dumps(timing, indent=2))

        # Write eval-result.json
        (timing_dir / "eval-result.json").write_text(json.dumps(result, indent=2))

        status = "[green]OK[/green]" if result["success"] else "[red]FAIL[/red]"
        dur = result["duration_seconds"]
        console.print(f"  {counter}{status} {eval_name} [{config}] ({dur:.0f}s)")

        return result


def detect_widget_name(script_path: Path) -> str | None:
    """Detect the widget variable name from a script.

    Looks for patterns like:
        dashboard = ui.dashboard(...)
        my_widget = ui.dashboard(...)
        app = some_component()
    """
    import re

    text = script_path.read_text()
    # Look for `name = ui.dashboard(...)` — most common pattern
    match = re.search(r"^(\w+)\s*=\s*ui\.dashboard\(", text, re.MULTILINE)
    if match:
        return match.group(1)
    # Fallback: look for any top-level widget assignment
    match = re.search(r"^(\w+)\s*=\s*ui\.\w+\(", text, re.MULTILINE)
    if match:
        return match.group(1)
    return None


def validate_single(eval_name: str, config: str, run_dir: Path) -> dict:
    """Run dh render validation on a completed eval run."""
    outputs_dir = run_dir / eval_name / config / "run-1" / "outputs"
    script_path = outputs_dir / "script.py"

    validation = {
        "eval_name": eval_name,
        "configuration": config,
        "script_exists": script_path.exists(),
        "exec_success": False,
        "render_success": False,
        "render_snapshot": None,
        "errors": [],
    }

    if not script_path.exists():
        validation["errors"].append("No script.py produced")
        return validation

    # Detect widget name for --widget flag
    widget_name = detect_widget_name(script_path)
    widget_args = ["--widget", widget_name] if widget_name else []
    if widget_name:
        validation["widget_name"] = widget_name

    # Step 1: dh exec verification
    try:
        exec_result = subprocess.run(
            ["dh", "exec", "--vm", "--no-show-tables", str(script_path), "--timeout", "120"],
            capture_output=True, text=True, timeout=180,
        )
        validation["exec_success"] = exec_result.returncode == 0
        validation["exec_exit_code"] = exec_result.returncode
        if exec_result.returncode != 0:
            validation["exec_stderr"] = exec_result.stderr[:1000]
            validation["errors"].append(f"dh exec failed (exit {exec_result.returncode})")
        # Save output (dh exec combines stdout/stderr)
        output = exec_result.stdout or exec_result.stderr or ""
        (outputs_dir / "exec-result.txt").write_text(output[:4000])
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        validation["errors"].append(f"dh exec error: {e}")

    # Step 2: dh render snapshot
    try:
        snap_result = subprocess.run(
            ["dh", "render", str(script_path), *widget_args, "snapshot", "--timeout", "30000"],
            capture_output=True, text=True, timeout=60,
        )
        validation["render_success"] = snap_result.returncode == 0
        validation["render_exit_code"] = snap_result.returncode
        # Always save output to the same file regardless of pass/fail
        output = snap_result.stdout or snap_result.stderr or ""
        if output.strip():
            validation["render_snapshot"] = output
            (outputs_dir / "render-result.txt").write_text(output[:4000])
        if snap_result.returncode != 0:
            err = snap_result.stderr[:500] if snap_result.stderr else "empty output"
            validation["errors"].append(f"dh render snapshot failed: {err}")
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        validation["errors"].append(f"dh render snapshot error: {e}")





    # Save validation results
    (outputs_dir / "validation.json").write_text(json.dumps(validation, indent=2))
    return validation


def extract_token_usage(raw_jsonl: Path) -> dict:
    """Sum token usage from assistant events in a session log."""
    input_tokens = 0
    output_tokens = 0
    cache_creation_tokens = 0
    cache_read_tokens = 0
    num_turns = 0

    with open(raw_jsonl) as f:
        for line in f:
            event = json.loads(line)
            if event.get("type") != "assistant":
                continue
            num_turns += 1
            usage = event.get("message", {}).get("usage", {})
            input_tokens += usage.get("input_tokens", 0)
            output_tokens += usage.get("output_tokens", 0)
            cache_creation_tokens += usage.get("cache_creation_input_tokens", 0)
            cache_read_tokens += usage.get("cache_read_input_tokens", 0)

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_tokens": cache_creation_tokens,
        "cache_read_tokens": cache_read_tokens,
        "total_tokens": input_tokens + output_tokens + cache_creation_tokens + cache_read_tokens,
        "num_turns": num_turns,
    }


def parse_logs(run_dir: Path, eval_names: list[str] | None = None):
    """Parse session logs for all runs."""
    # Collect items to parse for accurate counting
    parse_items = []
    for eval_dir in sorted(run_dir.iterdir()):
        if not eval_dir.is_dir():
            continue
        if eval_names and eval_dir.name not in eval_names:
            continue
        for config in CONFIGS:
            run_1_dir = eval_dir / config / "run-1"
            outputs_dir = run_1_dir / "outputs"
            raw_jsonl = outputs_dir / "raw.jsonl"
            if not raw_jsonl.exists():
                continue
            parse_items.append((eval_dir, config, run_1_dir, outputs_dir, raw_jsonl))

    for i, (eval_dir, config, run_1_dir, outputs_dir, raw_jsonl) in enumerate(parse_items, 1):
        console.print(f"  [dim][{i}/{len(parse_items)}][/dim] Parsing {eval_dir.name} [{config}]...")
        parse_session_log(raw_jsonl, outputs_dir)

        # Update timing.json with actual token counts
        token_usage = extract_token_usage(raw_jsonl)
        timing_path = run_1_dir / "timing.json"
        timing = json.loads(timing_path.read_text()) if timing_path.exists() else {}
        timing.update(token_usage)
        timing_path.write_text(json.dumps(timing, indent=2))


def ensure_vm_pool(size: int = 2):
    """Start the dh VM pool if not running, and scale to the desired size."""
    try:
        status = subprocess.run(
            ["dh", "vm", "pool", "status"],
            capture_output=True, text=True, timeout=10,
        )
        if "not running" in status.stdout.lower():
            console.print(f"[cyan]Starting VM pool (size={size})...[/cyan]")
            # Pool start can take a while on first cold boot
            result = subprocess.run(
                ["dh", "vm", "pool", "start", "-n", str(size)],
                capture_output=True, text=True, timeout=180,
            )
            if result.returncode == 0:
                console.print(f"[cyan]VM pool started (size={size})[/cyan]")
            else:
                console.print(f"[yellow]VM pool start returned {result.returncode}[/yellow]")
        elif status.returncode == 0:
            # Pool is running — scale to desired size
            console.print(f"[cyan]VM pool already running, scaling to {size}...[/cyan]")
            subprocess.run(
                ["dh", "vm", "pool", "scale", str(size)],
                capture_output=True, timeout=10,
            )
            console.print(f"[cyan]VM pool ready[/cyan]")
        else:
            console.print(f"[yellow]VM pool status unclear, continuing[/yellow]")
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        console.print(f"[yellow]VM pool setup skipped: {e}[/yellow]")


async def stage_run(
    evals: list[dict],
    run_id: str,
    configs: list[str],
    parallel: int,
    model: str | None,
    skip_existing: bool,
    timeout: int,
) -> list[dict]:
    """Run evals via claude -p."""
    run_dir = EVALS2_RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Ensure VM pool is warm for dh exec inside claude -p sessions.
    # Scale to parallel count so concurrent evals don't cold-start.
    ensure_vm_pool(size=max(parallel, 2))

    # Write run config
    config_data = {
        "run_id": run_id,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "model": model or "default",
        "configs": configs,
        "parallel": parallel,
        "timeout": timeout,
        "eval_count": len(evals),
        "eval_ids": [e["id"] for e in evals],
    }
    (run_dir / "run-config.json").write_text(json.dumps(config_data, indent=2))

    semaphore = asyncio.Semaphore(parallel)
    tasks = []

    # Collect tasks first to know total count
    pending = []
    for eval_def in evals:
        for config in configs:
            result_path = (
                run_dir / eval_def["name"] / config / "run-1" / "eval-result.json"
            )
            if skip_existing and result_path.exists():
                console.print(
                    f"  [dim]Skipping {eval_def['name']} [{config}][/dim]"
                )
                continue
            pending.append((eval_def, config))

    # Shared mutable counter for progress tracking (safe in asyncio single-thread)
    progress = [0]
    total = len(pending)

    for eval_def, config in pending:
        tasks.append(run_single(
            eval_def, config, run_dir, model, semaphore, timeout,
            progress=progress, total=total,
        ))

    if not tasks:
        console.print("[yellow]No evals to run (all skipped)[/yellow]")
        return []

    console.print(
        f"\n[bold]Stage: run[/bold] — {len(tasks)} eval runs "
        f"(parallel={parallel})\n"
    )
    results = await asyncio.gather(*tasks)

    # Update run config
    config_data["end_time"] = datetime.now(timezone.utc).isoformat()
    config_data["results_summary"] = {
        "total": len(results),
        "succeeded": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
    }
    (run_dir / "run-config.json").write_text(json.dumps(config_data, indent=2))

    return results


def stage_validate(run_id: str, eval_names: list[str] | None = None):
    """Run dh render validation on completed runs."""
    run_dir = EVALS2_RUNS_DIR / run_id
    if not run_dir.exists():
        console.print(f"[red]Run directory not found: {run_dir}[/red]")
        sys.exit(1)

    # Collect items to validate for accurate counting
    validate_items = []
    for eval_dir in sorted(run_dir.iterdir()):
        if not eval_dir.is_dir() or eval_dir.name.endswith(".json"):
            continue
        if eval_names and eval_dir.name not in eval_names:
            continue
        for config in CONFIGS:
            script = eval_dir / config / "run-1" / "outputs" / "script.py"
            if not script.exists():
                continue
            validate_items.append((eval_dir, config))

    results = []
    for i, (eval_dir, config) in enumerate(validate_items, 1):
        console.print(f"  [dim][{i}/{len(validate_items)}][/dim] Validating {eval_dir.name} [{config}]...")
        v = validate_single(eval_dir.name, config, run_dir)
        results.append(v)
        status = "[green]OK[/green]" if v["render_success"] else "[red]FAIL[/red]"
        errs = f" ({len(v['errors'])} errors)" if v["errors"] else ""
        console.print(f"    {status}{errs}")

    return results


def print_results_table(results: list[dict]):
    """Print a summary table of eval results."""
    table = Table(title="Eval Results")
    table.add_column("Eval", style="cyan")
    table.add_column("Config")
    table.add_column("Status")
    table.add_column("Script")
    table.add_column("Duration", justify="right")

    for r in results:
        status = "[green]OK[/green]" if r["success"] else "[red]FAIL[/red]"
        script = "[green]yes[/green]" if r.get("script_produced") else "[red]no[/red]"
        dur = f"{r.get('duration_seconds', 0):.0f}s"
        config_label = r["configuration"].replace("_", " ")
        table.add_row(r["eval_name"], config_label, status, script, dur)

    console.print(table)


def generate_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def main():
    parser = argparse.ArgumentParser(description="Evals2 pipeline orchestrator")
    parser.add_argument(
        "--evals", nargs="*", type=int,
        help="Specific eval IDs to run (default: all)",
    )
    parser.add_argument(
        "--config", choices=["with_skill", "without_skill", "both"],
        default="both", help="Which configuration(s) to run",
    )
    parser.add_argument("--parallel", type=int, default=DEFAULT_PARALLEL)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument(
        "--stage", choices=["run", "validate", "parse", "grade", "aggregate", "viewer", "all"],
        default="all",
    )
    parser.add_argument("--model", help="Model override (e.g., sonnet, opus)")
    parser.add_argument("--run-id", help="Run ID (auto-generated if not specified)")
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT,
        help=f"Timeout per claude -p attempt in seconds (default: {DEFAULT_TIMEOUT})",
    )

    args = parser.parse_args()

    evals = load_evals(args.evals)
    if not evals:
        console.print("[red]No evals found[/red]")
        sys.exit(1)

    configs = CONFIGS if args.config == "both" else [args.config]
    run_id = args.run_id or generate_run_id()

    console.print(f"[bold]Run ID:[/bold] {run_id}")
    console.print(f"[bold]Evals:[/bold] {len(evals)}")
    console.print(f"[bold]Configs:[/bold] {', '.join(configs)}")
    console.print(f"[bold]Stage:[/bold] {args.stage}")

    if args.stage in ("run", "all"):
        results = asyncio.run(stage_run(
            evals, run_id, configs, args.parallel, args.model,
            args.skip_existing, args.timeout,
        ))
        if results:
            print_results_table(results)

    if args.stage in ("validate", "all"):
        console.print("\n[bold]Stage: validate[/bold]")
        eval_names = [e["name"] for e in evals] if args.evals else None
        stage_validate(run_id, eval_names)

    if args.stage in ("parse", "all"):
        console.print("\n[bold]Stage: parse[/bold]")
        eval_names = [e["name"] for e in evals] if args.evals else None
        parse_logs(EVALS2_RUNS_DIR / run_id, eval_names)

    if args.stage in ("grade", "all"):
        console.print("\n[bold]Stage: grade[/bold]")
        from evals2.grade import grade_run, load_evals_map
        evals_map = load_evals_map()
        run_dir = EVALS2_RUNS_DIR / run_id
        # Collect items to grade for accurate counting
        grade_items = []
        for eval_dir in sorted(run_dir.iterdir()):
            if not eval_dir.is_dir() or eval_dir.name not in evals_map:
                continue
            if args.evals:
                matching = [e for e in evals if e["name"] == eval_dir.name]
                if not matching:
                    continue
            eval_def = evals_map[eval_dir.name]
            for config in configs:
                outputs_dir = eval_dir / config / "run-1" / "outputs"
                if not outputs_dir.exists():
                    continue
                grade_items.append((eval_dir, config, eval_def))

        for i, (eval_dir, config, eval_def) in enumerate(grade_items, 1):
            grading = grade_run(eval_dir.name, config, run_dir, eval_def)
            s = grading["summary"]
            status = "[green]" if s["pass_rate"] >= 0.8 else "[yellow]" if s["pass_rate"] >= 0.5 else "[red]"
            console.print(f"  [dim][{i}/{len(grade_items)}][/dim] {status}{eval_dir.name}[/] [{config}]: {s['passed']}/{s['total']} ({s['pass_rate']:.0%})")

    if args.stage in ("aggregate", "all"):
        console.print("\n[bold]Stage: aggregate[/bold]")
        from evals2.aggregate import main as aggregate_main
        sys.argv = ["aggregate-evals2", "--run-id", run_id]
        aggregate_main()

    if args.stage in ("viewer", "all"):
        run_dir = EVALS2_RUNS_DIR / run_id
        benchmark_path = run_dir / "benchmark.json"
        review_path = run_dir / "review.html"
        if benchmark_path.exists():
            console.print("\n[bold]Stage: viewer[/bold]")
            viewer_script = EVALS2_DIR / "generate_review.py"
            subprocess.run([
                sys.executable, str(viewer_script),
                str(run_dir),
                "--skill-name", "deephaven-core-query-writing",
                "--benchmark", str(benchmark_path),
                "--static", str(review_path),
            ], check=False)
            if review_path.exists():
                console.print(f"  [green]Review:[/green] {review_path}")

    run_dir = EVALS2_RUNS_DIR / run_id
    console.print(f"\n[bold green]Done.[/bold green] Results in: {run_dir}")


if __name__ == "__main__":
    main()
