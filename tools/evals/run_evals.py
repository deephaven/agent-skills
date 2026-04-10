"""Evals pipeline orchestrator.

Runs eval datasets through claude -p with and without the skill, then validates
outputs using dh render, parses session logs, and produces results compatible
with skill-creator's grading and viewer infrastructure.

Usage:
    uv run run-evals                                # run all evals, both configs
    uv run run-evals --config with_skill            # only with-skill runs
    uv run run-evals --config without_skill         # only baseline runs
    uv run run-evals --evals 1 2 3                  # specific eval IDs
    uv run run-evals --parallel 5                   # concurrency level
    uv run run-evals --stage run                    # just run (no validate/parse)
    uv run run-evals --stage validate --run-id X    # validate existing run
    uv run run-evals --stage parse --run-id X       # parse existing run
    uv run run-evals --skip-existing                # resume interrupted run
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
EVALS_DIR = Path(__file__).resolve().parent  # tools/evals/
EVALS_DATA_DIR = EVALS_DIR / "data"
EVALS_RUNS_DIR = EVALS_DIR / "runs"
PROMPT_TEMPLATE_PATH = EVALS_DIR / "prompt.md"
EVALS_JSON_PATH = EVALS_DIR / "evals.json"
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


def ensure_eval_datasets(evals: list[dict]) -> None:
    """Ensure all required datasets exist locally, downloading missing ones."""
    from download_eval_data import (
        KAGGLE_API,
        api_get,
        download_and_extract,
        write_folder_manifest,
    )

    needed: dict[str, str] = {}
    for e in evals:
        slug = e.get("dataset", "")
        if not slug:
            continue
        folder_name = slug.replace("/", "--")
        # slug in evals.json is already in folder format (owner--name)
        needed[folder_name] = slug

    EVALS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    missing = []
    for folder_name, slug in needed.items():
        dest = EVALS_DATA_DIR / folder_name
        csvs = list(dest.glob("*.csv")) if dest.exists() else []
        if not csvs:
            missing.append((folder_name, slug))

    if not missing:
        console.print(f"[green]All {len(needed)} eval datasets present[/green]")
        return

    console.print(
        f"[cyan]Downloading {len(missing)} missing dataset(s)...[/cyan]"
    )

    import httpx

    with httpx.Client() as client:
        for folder_name, slug in missing:
            # Convert folder format (owner--name) to API format (owner/name)
            ref = slug.replace("--", "/")
            dest = EVALS_DATA_DIR / folder_name
            console.print(f"  Downloading {ref}...", end=" ")
            csv_filenames = download_and_extract(client, ref, dest)
            if csv_filenames:
                owner, name = ref.split("/", 1)
                resp = api_get(
                    client, f"{KAGGLE_API}/datasets/view/{owner}/{name}"
                )
                ds = resp.json() if resp.status_code == 200 else {}
                write_folder_manifest(client, dest, ds, csv_filenames)
                console.print(f"OK ({len(csv_filenames)} CSV)")
            else:
                console.print("[red]FAILED[/red]")


def build_prompt(eval_def: dict, output_dir: Path, config: str) -> str:
    """Build the eval prompt for a single run."""
    template = PROMPT_TEMPLATE_PATH.read_text()

    if config == "with_skill":
        preamble_path = EVALS_DIR / "preamble-with-skill.md"
        skill_path = SKILL_DIR / "SKILL.md"
        preamble = preamble_path.read_text().replace(
            "{SKILL_PATH}", str(skill_path.resolve())
        )
    else:
        preamble_path = EVALS_DIR / "preamble-without-skill.md"
        preamble = preamble_path.read_text()

    task_prompt = eval_def["prompt"]

    # Resolve relative evals/data/ paths to absolute so CWD doesn't matter
    abs_data_dir = str((EVALS_DIR / "data").resolve())
    task_prompt = task_prompt.replace("evals/data/", f"{abs_data_dir}/")

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


async def _execute_claude(
    cmd: list[str], timeout: int, stdin_input: str | None = None
) -> dict:
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
            proc.communicate(input=input_bytes),
            timeout=timeout,
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
    effort: str | None,
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

        session_id = str(
            uuid.uuid5(EVAL_NAMESPACE, f"{eval_name}-{config}-{run_dir.name}")
        )

        # Delete any stale session log so claude -p starts fresh
        # instead of resuming a previous (possibly broken) session.
        delete_session_log(session_id)

        prompt = build_prompt(eval_def, outputs_dir, config)

        cmd = [
            "claude",
            "-p",
            "--session-id",
            session_id,
            "--output-format",
            "json",
            "--max-turns",
            str(DEFAULT_MAX_TURNS),
            "--tools",
            "Bash,Read,Write,Edit,Glob,Grep,WebFetch",
            "--verbose",
            "--dangerously-skip-permissions",
            "--strict-mcp-config",
        ]
        if config == "without_skill":
            cmd.append("--disable-slash-commands")
        if model:
            cmd.extend(["--model", model])
        if effort:
            cmd.extend(["--effort", effort])

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
                # Extract actual model used from modelUsage keys
                model_usage = claude_parsed.get("modelUsage", {})
                if model_usage:
                    result["model_used"] = next(iter(model_usage))

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


def _load_skill_content() -> str:
    """Read all skill files and concatenate them for injection into prompts."""
    parts = []
    skill_md = SKILL_DIR / "SKILL.md"
    if skill_md.exists():
        parts.append(f"### SKILL.md\n\n{skill_md.read_text()}")
    refs_dir = SKILL_DIR / "references"
    if refs_dir.is_dir():
        for ref_file in sorted(refs_dir.glob("*.md")):
            parts.append(f"### references/{ref_file.name}\n\n{ref_file.read_text()}")
    return "\n\n---\n\n".join(parts)


async def generate_recommendations(
    outputs_dir: Path, eval_name: str, config: str
) -> None:
    """Generate skill-recommendations.md from a session transcript using Sonnet."""
    transcript_path = outputs_dir / "transcript.md"
    output_path = outputs_dir / "skill-recommendations.md"

    if not transcript_path.exists():
        console.print(
            f"    [yellow]SKIP[/yellow] {eval_name} [{config}]: no transcript.md (run parse first)"
        )
        return

    skill_content = _load_skill_content()
    prompt = RECOMMEND_PROMPT.format(
        output_path=output_path,
        transcript_path=transcript_path,
        skill_content=skill_content,
    )

    result = await _execute_claude(
        [
            "claude",
            "-p",
            "--model",
            "sonnet",
            "--permission-mode",
            "acceptEdits",
            "--allowedTools",
            "Read,Write",
            "--max-turns",
            "10",
            "--strict-mcp-config",
        ],
        timeout=120,
        stdin_input=prompt,
    )

    if result["returncode"] == 0 and output_path.exists():
        console.print(
            f"    [green]OK[/green] {eval_name} [{config}]"
        )
    else:
        stderr = result.get("stderr", b"")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        detail = f" (exit {result['returncode']})"
        if result.get("timed_out"):
            detail = " (timed out)"
        if stderr:
            detail += f": {stderr[:200]}"
        console.print(
            f"    [red]FAIL[/red] {eval_name} [{config}]{detail}"
        )


async def stage_recommend(
    run_id: str,
    eval_names: list[str] | None = None,
    parallel: int = DEFAULT_PARALLEL,
):
    """Generate skill-recommendations.md for all runs (parallel)."""
    run_dir = EVALS_RUNS_DIR / run_id
    if not run_dir.exists():
        console.print(f"[red]Run directory not found: {run_dir}[/red]")
        return

    items = []
    for eval_dir in sorted(run_dir.iterdir()):
        if not eval_dir.is_dir() or eval_dir.name.startswith("."):
            continue
        if eval_names and eval_dir.name not in eval_names:
            continue
        for config in CONFIGS:
            outputs_dir = eval_dir / config / "run-1" / "outputs"
            raw_jsonl = outputs_dir / "raw.jsonl"
            if not raw_jsonl.exists():
                continue
            items.append((eval_dir.name, config, outputs_dir))

    if not items:
        console.print("  [dim]No session logs found[/dim]")
        return

    semaphore = asyncio.Semaphore(parallel)
    progress = [0]
    total = len(items)

    async def recommend_one(eval_name: str, config: str, outputs_dir: Path):
        async with semaphore:
            progress[0] += 1
            idx = progress[0]
            console.print(
                f"  [dim][{idx}/{total}][/dim] Recommending {eval_name} [{config}]..."
            )
            await generate_recommendations(outputs_dir, eval_name, config)

    tasks = [recommend_one(n, c, d) for n, c, d in items]
    await asyncio.gather(*tasks)


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

    # Step 1: dh exec verification (with retries)
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            exec_result = subprocess.run(
                ["dh", "exec", "--no-show-tables", str(script_path), "--timeout", "120"],
                capture_output=True,
                text=True,
                timeout=180,
            )
            validation["exec_success"] = exec_result.returncode == 0
            validation["exec_exit_code"] = exec_result.returncode
            if exec_result.returncode != 0:
                validation["exec_stderr"] = exec_result.stderr[:1000]
                if attempt < max_retries:
                    continue
                validation["errors"].append(
                    f"dh exec failed (exit {exec_result.returncode})"
                )
            # Save output (dh exec combines stdout/stderr)
            output = exec_result.stdout or exec_result.stderr or ""
            (outputs_dir / "exec-result.txt").write_text(output[:4000])
            break
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            if attempt < max_retries:
                continue
            validation["errors"].append(f"dh exec error: {e}")

    # Step 2: dh render snapshot (with retries)
    for attempt in range(1, max_retries + 1):
        try:
            snap_result = subprocess.run(
                [
                    "dh",
                    "render",
                    str(script_path),
                    *widget_args,
                    "snapshot",
                    "--timeout",
                    "30000",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            validation["render_success"] = snap_result.returncode == 0
            validation["render_exit_code"] = snap_result.returncode
            # Always save output to the same file regardless of pass/fail
            output = snap_result.stdout or snap_result.stderr or ""
            if output.strip():
                validation["render_snapshot"] = output
                (outputs_dir / "render-result.txt").write_text(output[:4000])
            if snap_result.returncode != 0:
                if attempt < max_retries:
                    continue
                err = snap_result.stderr[:500] if snap_result.stderr else "empty output"
                validation["errors"].append(f"dh render snapshot failed: {err}")
            break
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            if attempt < max_retries:
                continue
            validation["errors"].append(f"dh render snapshot error: {e}")

    # Save validation results
    (outputs_dir / "validation.json").write_text(json.dumps(validation, indent=2))
    return validation


def extract_token_usage(raw_jsonl: Path) -> dict:
    """Sum token usage from assistant events in a session log.

    Assistant events with the same message ID are streaming chunks of one API
    call.  We deduplicate by message ID and keep the last usage block per call
    (which carries the final token counts).
    """
    # Deduplicate by message ID — keep last usage per API call
    api_calls: dict[str, dict] = {}  # msg_id -> last usage dict
    user_turns = 0
    seen_assistant_ids: set[str] = set()
    assistant_turns = 0

    with open(raw_jsonl) as f:
        for line in f:
            event = json.loads(line)
            etype = event.get("type")
            if etype == "user":
                user_turns += 1
            elif etype == "assistant":
                msg_id = event.get("message", {}).get("id", "")
                usage = event.get("message", {}).get("usage", {})
                if msg_id:
                    if msg_id not in seen_assistant_ids:
                        seen_assistant_ids.add(msg_id)
                        assistant_turns += 1
                    api_calls[msg_id] = usage
                else:
                    api_calls[id(usage)] = usage
                    assistant_turns += 1

    input_tokens = 0
    output_tokens = 0
    cache_creation_tokens = 0
    cache_read_tokens = 0

    for usage in api_calls.values():
        input_tokens += usage.get("input_tokens", 0)
        output_tokens += usage.get("output_tokens", 0)
        cache_creation_tokens += usage.get("cache_creation_input_tokens", 0)
        cache_read_tokens += usage.get("cache_read_input_tokens", 0)

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_tokens": cache_creation_tokens,
        "cache_read_tokens": cache_read_tokens,
        "total_tokens": input_tokens
        + output_tokens
        + cache_creation_tokens
        + cache_read_tokens,
        "num_turns": user_turns + assistant_turns,
    }


async def parse_logs(
    run_dir: Path, eval_names: list[str] | None = None, parallel: int = DEFAULT_PARALLEL
):
    """Parse session logs for all runs (parallel)."""
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

    if not parse_items:
        return

    semaphore = asyncio.Semaphore(parallel)
    progress = [0]
    total = len(parse_items)

    async def parse_one(
        eval_dir: Path, config: str, run_1_dir: Path, outputs_dir: Path, raw_jsonl: Path
    ):
        async with semaphore:
            progress[0] += 1
            idx = progress[0]
            console.print(
                f"  [dim][{idx}/{total}][/dim] Parsing {eval_dir.name} [{config}]..."
            )
            await asyncio.to_thread(parse_session_log, raw_jsonl, outputs_dir)

            # Update timing.json with actual token counts
            token_usage = extract_token_usage(raw_jsonl)
            timing_path = run_1_dir / "timing.json"
            timing = json.loads(timing_path.read_text()) if timing_path.exists() else {}
            timing.update(token_usage)
            timing_path.write_text(json.dumps(timing, indent=2))

    tasks = [parse_one(*item) for item in parse_items]
    await asyncio.gather(*tasks)


async def stage_run(
    evals: list[dict],
    run_id: str,
    configs: list[str],
    parallel: int,
    model: str | None,
    effort: str | None,
    skip_existing: bool,
    timeout: int,
) -> list[dict]:
    """Run evals via claude -p."""
    run_dir = EVALS_RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Write run config
    config_data = {
        "run_id": run_id,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "effort": effort,
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
                console.print(f"  [dim]Skipping {eval_def['name']} [{config}][/dim]")
                continue
            pending.append((eval_def, config))

    # Shared mutable counter for progress tracking (safe in asyncio single-thread)
    progress = [0]
    total = len(pending)

    for eval_def, config in pending:
        tasks.append(
            run_single(
                eval_def,
                config,
                run_dir,
                model,
                effort,
                semaphore,
                timeout,
                progress=progress,
                total=total,
            )
        )

    if not tasks:
        console.print("[yellow]No evals to run (all skipped)[/yellow]")
        return []

    console.print(
        f"\n[bold]Stage: run[/bold] — {len(tasks)} eval runs (parallel={parallel})\n"
    )
    results = await asyncio.gather(*tasks)

    # Resolve actual model from eval results if not explicitly set
    if not config_data["model"]:
        for r in results:
            if r.get("model_used"):
                config_data["model"] = r["model_used"]
                break

    # Update run config
    config_data["end_time"] = datetime.now(timezone.utc).isoformat()
    config_data["results_summary"] = {
        "total": len(results),
        "succeeded": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
    }
    (run_dir / "run-config.json").write_text(json.dumps(config_data, indent=2))

    return results


async def stage_validate(
    run_id: str, eval_names: list[str] | None = None, parallel: int = DEFAULT_PARALLEL
):
    """Run dh render validation on completed runs (parallel)."""
    run_dir = EVALS_RUNS_DIR / run_id
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

    if not validate_items:
        return []

    semaphore = asyncio.Semaphore(parallel)
    progress = [0]
    total = len(validate_items)

    async def validate_one(eval_dir: Path, config: str) -> dict:
        async with semaphore:
            progress[0] += 1
            idx = progress[0]
            console.print(
                f"  [dim][{idx}/{total}][/dim] Validating {eval_dir.name} [{config}]..."
            )
            v = await asyncio.to_thread(validate_single, eval_dir.name, config, run_dir)
            status = "[green]OK[/green]" if v["render_success"] else "[red]FAIL[/red]"
            errs = f" ({len(v['errors'])} errors)" if v["errors"] else ""
            console.print(f"    {status}{errs}")
            return v

    tasks = [validate_one(d, c) for d, c in validate_items]
    return await asyncio.gather(*tasks)


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


RECOMMEND_PROMPT = """\
You are analyzing a session transcript from an AI agent that wrote a \
Deephaven dashboard script. Read the transcript and write a brief reflection.

Write your output to: {output_path}

Content (max 40 lines):

- **Errors encountered:** List every distinct error hit during script writing \
and verification. Include the exact error message, which attempt triggered it, \
and what code caused it.
- **Fixes applied:** For each error, what changed and why. Include before/after \
code snippets where helpful.
- **Skill gaps:** Identify what documentation or examples would have prevented \
these errors. Be specific about what is MISSING from the skill files below — \
do not recommend adding content that is already covered.
- **Metrics:** Number of `dh exec` attempts, number of `dh render` attempts, \
and average retry count for each.

Session transcript: {transcript_path}

## Current Skill Files

The agent had access to the following skill documentation. Use this to assess \
whether errors stem from gaps in the skill or from the agent ignoring existing \
guidance.

{skill_content}

Be concise and specific. Do not include generic advice. Do not recommend \
adding content that already exists in the skill files above.
"""

SUMMARIZE_PROMPT = """\
You are analyzing eval reflections from AI agents that wrote Deephaven dashboard scripts.

Below are the skill-recommendations.md files from {count} evals run **{config_label}**.
Each reflects on errors encountered, fixes applied, and skill gaps.

Produce a concise summary (markdown) with these sections:

## Common Errors
List the most frequent error patterns across evals. Group similar errors together.
For each, note how many evals hit it and give a representative error message.

## Common Skill Gaps
What documentation or examples were most frequently missing or unclear?
Rank by how many evals mentioned the gap.

## Key Metrics
- Evals analyzed: N
- Average dh exec/render retry count (if reported)
- Most common root cause category (API misuse, import errors, data handling, etc.)

Be specific and quantitative. Do NOT include generic advice.

---

{reflections}
"""


def stage_summarize(
    run_dir: Path, benchmark_path: Path, configs: list[str]
) -> None:
    """Summarize skill-recommendations across configs using Sonnet."""
    benchmark = json.loads(benchmark_path.read_text())

    summaries: dict[str, str] = {}
    for config in configs:
        # Collect all skill-recommendations.md for this config
        reflections: list[str] = []
        for eval_dir in sorted(run_dir.iterdir()):
            if not eval_dir.is_dir() or eval_dir.name.startswith("."):
                continue
            rec_path = (
                eval_dir / config / "run-1" / "outputs" / "skill-recommendations.md"
            )
            if rec_path.exists():
                text = rec_path.read_text(errors="replace").strip()
                if text:
                    reflections.append(
                        f"### {eval_dir.name}\n\n{text}"
                    )

        if not reflections:
            console.print(f"  [dim]{config}:[/dim] no recommendations found")
            continue

        config_label = config.replace("_", " ")
        prompt = SUMMARIZE_PROMPT.format(
            count=len(reflections),
            config_label=config_label,
            reflections="\n\n---\n\n".join(reflections),
        )

        console.print(
            f"  [dim]{config}:[/dim] summarizing {len(reflections)} recommendations..."
        )
        result = subprocess.run(
            ["claude", "-p", "--model", "sonnet", "--output-format", "text"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0 and result.stdout.strip():
            summaries[config] = result.stdout.strip()
            console.print(f"  [green]{config}:[/green] summary generated")
        else:
            console.print(
                f"  [red]{config}:[/red] summarization failed (exit {result.returncode})"
            )

    if summaries:
        benchmark["recommendation_summaries"] = summaries
        benchmark_path.write_text(json.dumps(benchmark, indent=2))
        console.print(f"  [green]Updated:[/green] {benchmark_path}")


async def stage_grade(
    run_id: str,
    evals: list[dict],
    configs: list[str],
    eval_ids: list[int] | None = None,
    parallel: int = DEFAULT_PARALLEL,
):
    """Grade eval runs in parallel."""
    from evals.grade import grade_run, load_evals_map

    evals_map = load_evals_map()
    run_dir = EVALS_RUNS_DIR / run_id

    grade_items = []
    for eval_dir in sorted(run_dir.iterdir()):
        if not eval_dir.is_dir() or eval_dir.name not in evals_map:
            continue
        if eval_ids:
            matching = [e for e in evals if e["name"] == eval_dir.name]
            if not matching:
                continue
        eval_def = evals_map[eval_dir.name]
        for config in configs:
            outputs_dir = eval_dir / config / "run-1" / "outputs"
            if not outputs_dir.exists():
                continue
            grade_items.append((eval_dir, config, eval_def))

    if not grade_items:
        return

    semaphore = asyncio.Semaphore(parallel)
    progress = [0]
    total = len(grade_items)

    async def grade_one(eval_dir: Path, config: str, eval_def: dict):
        async with semaphore:
            grading = await asyncio.to_thread(
                grade_run, eval_dir.name, config, run_dir, eval_def
            )
            progress[0] += 1
            idx = progress[0]
            s = grading["summary"]
            status = (
                "[green]"
                if s["pass_rate"] >= 0.8
                else "[yellow]"
                if s["pass_rate"] >= 0.5
                else "[red]"
            )
            console.print(
                f"  [dim][{idx}/{total}][/dim] {status}{eval_dir.name}[/] [{config}]: {s['passed']}/{s['total']} ({s['pass_rate']:.0%})"
            )
            return grading

    tasks = [grade_one(d, c, e) for d, c, e in grade_items]
    await asyncio.gather(*tasks)


async def async_main(args):
    """Async entry point for the pipeline."""
    evals = load_evals(args.evals)
    if not evals:
        console.print("[red]No evals found[/red]")
        sys.exit(1)

    # Ensure all required datasets are downloaded before running
    ensure_eval_datasets(evals)

    configs = CONFIGS if args.config == "both" else [args.config]
    run_id = args.run_id or generate_run_id()

    console.print(f"[bold]Run ID:[/bold] {run_id}")
    console.print(f"[bold]Evals:[/bold] {len(evals)}")
    console.print(f"[bold]Configs:[/bold] {', '.join(configs)}")
    console.print(f"[bold]Stage:[/bold] {args.stage}")

    if args.stage in ("run", "all"):
        results = await stage_run(
            evals,
            run_id,
            configs,
            args.parallel,
            args.model,
            args.effort,
            args.skip_existing,
            args.timeout,
        )
        if results:
            print_results_table(results)

    # Parse must run before recommend (recommend reads transcript.md).
    # Validate is independent and can run in parallel with parse.
    if args.stage in ("validate", "parse") or args.stage == "all":
        eval_names = [e["name"] for e in evals] if args.evals else None
        parallel_tasks = []

        if args.stage in ("validate", "all"):
            console.print(f"\n[bold]Stage: validate[/bold] (parallel={args.parallel})")
            parallel_tasks.append(stage_validate(run_id, eval_names, args.parallel))

        if args.stage in ("parse", "all"):
            console.print(f"\n[bold]Stage: parse[/bold] (parallel={args.parallel})")
            parallel_tasks.append(
                parse_logs(EVALS_RUNS_DIR / run_id, eval_names, args.parallel)
            )

        if parallel_tasks:
            await asyncio.gather(*parallel_tasks)

    # Recommend runs after parse (needs transcript.md) but before grade.
    if args.stage in ("recommend", "all"):
        eval_names = [e["name"] for e in evals] if args.evals else None
        console.print(f"\n[bold]Stage: recommend[/bold] (parallel={args.parallel})")
        await stage_recommend(run_id, eval_names, args.parallel)

    if args.stage in ("grade", "all"):
        console.print(f"\n[bold]Stage: grade[/bold] (parallel={args.parallel})")
        await stage_grade(run_id, evals, configs, args.evals, args.parallel)

    if args.stage in ("aggregate", "all"):
        console.print("\n[bold]Stage: aggregate[/bold]")
        from evals.aggregate import main as aggregate_main

        sys.argv = ["aggregate-evals", "--run-id", run_id]
        aggregate_main()

    if args.stage in ("summarize", "all"):
        run_dir = EVALS_RUNS_DIR / run_id
        benchmark_path = run_dir / "benchmark.json"
        if benchmark_path.exists():
            console.print("\n[bold]Stage: summarize[/bold]")
            stage_summarize(run_dir, benchmark_path, configs)

    if args.stage in ("viewer", "all"):
        run_dir = EVALS_RUNS_DIR / run_id
        benchmark_path = run_dir / "benchmark.json"
        review_path = run_dir / "review.html"
        if benchmark_path.exists():
            console.print("\n[bold]Stage: viewer[/bold]")
            viewer_script = EVALS_DIR / "generate_review.py"
            subprocess.run(
                [
                    sys.executable,
                    str(viewer_script),
                    str(run_dir),
                    "--skill-name",
                    "deephaven-core-query-writing",
                    "--benchmark",
                    str(benchmark_path),
                    "--static",
                    str(review_path),
                ],
                check=False,
            )
            if review_path.exists():
                console.print(f"  [green]Review:[/green] {review_path}")

    run_dir = EVALS_RUNS_DIR / run_id
    console.print(f"\n[bold green]Done.[/bold green] Results in: {run_dir}")


def main():
    parser = argparse.ArgumentParser(description="Evals pipeline orchestrator")
    parser.add_argument(
        "--evals",
        nargs="*",
        type=int,
        help="Specific eval IDs to run (default: all)",
    )
    parser.add_argument(
        "--config",
        choices=["with_skill", "without_skill", "both"],
        default="both",
        help="Which configuration(s) to run",
    )
    parser.add_argument("--parallel", type=int, default=DEFAULT_PARALLEL)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument(
        "--stage",
        choices=["run", "recommend", "validate", "parse", "grade", "aggregate", "summarize", "viewer", "all"],
        default="all",
    )
    parser.add_argument("--model", help="Model override (e.g., sonnet, opus)")
    parser.add_argument(
        "--effort",
        choices=["low", "medium", "high", "max"],
        help="Thinking effort level for claude -p",
    )
    parser.add_argument("--run-id", help="Run ID (auto-generated if not specified)")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Timeout per claude -p attempt in seconds (default: {DEFAULT_TIMEOUT})",
    )

    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
