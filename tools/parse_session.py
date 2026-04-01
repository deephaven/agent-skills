"""Parse Claude Code JSONL session logs into transcripts and metrics.

Reads raw.jsonl files produced by Claude Code and generates:
- transcript.md: human-readable conversation transcript
- metrics.json: structured metrics (tokens, tools, errors, timeline)

Usage:
    uv run parse-session <raw.jsonl> [--output-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Pricing per million tokens (Claude Opus 4.6 as of 2026-03)
PRICING = {
    "input": 5.0,
    "output": 25.0,
    "cache_read": 0.50,
    "cache_creation_5m": 6.25,
    "cache_creation_1h": 10.0,
}


def parse_timestamp(ts: str) -> datetime:
    """Parse an ISO timestamp string."""
    # Handle both Z and +00:00 suffixes
    ts = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)


def load_session(jsonl_path: Path) -> list[dict]:
    """Load and return all events from a JSONL session log."""
    events = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def extract_content_text(content) -> str:
    """Extract plain text from a message content field."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_result":
                    c = block.get("content", "")
                    if isinstance(c, str):
                        parts.append(c)
                    elif isinstance(c, list):
                        for sub in c:
                            if isinstance(sub, dict) and sub.get("type") == "text":
                                parts.append(sub.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


def truncate(text: str, max_len: int) -> str:
    """Truncate text with a note about total length."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"\n... ({len(text)} chars total)"


def detect_error_type(text: str) -> str | None:
    """Try to detect the Python error type from a traceback."""
    # Look for the last exception line in a traceback
    match = re.search(r"(\w+Error|\w+Exception|\w+Warning): (.+?)(?:\n|$)", text)
    if match:
        return match.group(1)
    if "Traceback (most recent call last)" in text:
        return "UnknownError"
    return None


def has_traceback(text: str) -> bool:
    """Check if text contains a Python traceback.

    Only matches actual tracebacks, not mentions of error types in prose/code.
    Requires 'Traceback (most recent call last)' or a non-zero exit code pattern.
    """
    return "Traceback (most recent call last)" in text or "exit code 1" in text.lower()


def generate_transcript(events: list[dict], eval_name: str) -> str:
    """Generate a human-readable markdown transcript."""
    lines: list[str] = []

    # Find first and last timestamps
    timestamps = [
        parse_timestamp(e["timestamp"])
        for e in events
        if "timestamp" in e
    ]
    if not timestamps:
        return "# Empty session\n"

    first_ts = min(timestamps)
    last_ts = max(timestamps)
    elapsed = last_ts - first_ts

    # Find session ID and model
    session_id = ""
    model = ""
    for e in events:
        if "sessionId" in e:
            session_id = e["sessionId"]
        if e.get("type") == "assistant":
            msg = e.get("message", {})
            if "model" in msg:
                model = msg["model"]
                break

    lines.append(f"# Session Transcript: {eval_name}")
    lines.append(f"**Session ID:** {session_id}")
    lines.append(f"**Model:** {model}")
    lines.append(f"**Duration:** {first_ts.isoformat()} → {last_ts.isoformat()} ({elapsed})")
    lines.append("")
    lines.append("---")
    lines.append("")

    turn_num = 0
    for event in events:
        event_type = event.get("type")
        ts = event.get("timestamp")
        relative = ""
        if ts:
            rel_ms = int((parse_timestamp(ts) - first_ts).total_seconds() * 1000)
            relative = f" *(+{rel_ms}ms)*"

        if event_type == "user" and not event.get("isMeta"):
            turn_num += 1
            msg = event.get("message", {})
            content = msg.get("content", "")
            text = extract_content_text(content)

            # Check for tool results
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_id = block.get("tool_use_id", "")
                        is_err = block.get("is_error", False)
                        result_text = extract_content_text(block.get("content", ""))
                        status = "**ERROR**" if is_err or has_traceback(result_text) else "success"
                        lines.append(f"### Tool Result{relative}")
                        lines.append(f"**Status:** {status}")
                        lines.append(f"**Output:**")
                        lines.append("```")
                        lines.append(truncate(result_text, 500))
                        lines.append("```")
                        lines.append("")
                if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                    continue

            lines.append(f"## Turn {turn_num} — User{relative}")
            lines.append(truncate(text, 1000))
            lines.append("")

        elif event_type == "assistant":
            turn_num += 1
            msg = event.get("message", {})
            content = msg.get("content", [])
            usage = msg.get("usage", {})

            lines.append(f"## Turn {turn_num} — Assistant{relative}")

            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")

                    if btype == "thinking":
                        thinking_text = block.get("thinking", "")
                        tokens = len(thinking_text.split())  # rough estimate
                        lines.append(f"### Thinking (~{tokens} words)")
                        lines.append(truncate(thinking_text, 500))
                        lines.append("")

                    elif btype == "text":
                        text = block.get("text", "")
                        if text.strip():
                            lines.append("### Response")
                            lines.append(truncate(text, 1000))
                            lines.append("")

                    elif btype == "tool_use":
                        name = block.get("name", "unknown")
                        inp = block.get("input", {})
                        inp_str = json.dumps(inp) if isinstance(inp, dict) else str(inp)
                        lines.append(f"### Tool Use: {name}")
                        lines.append(f"**Input:** {truncate(inp_str, 200)}")
                        lines.append("")

            if usage:
                in_tok = usage.get("input_tokens", 0)
                out_tok = usage.get("output_tokens", 0)
                lines.append(f"*Tokens: in={in_tok}, out={out_tok}*")
                lines.append("")

    return "\n".join(lines)


def extract_metrics(events: list[dict], eval_name: str) -> dict:
    """Extract structured metrics from session events."""
    timestamps = [
        parse_timestamp(e["timestamp"])
        for e in events
        if "timestamp" in e
    ]

    first_ts = min(timestamps) if timestamps else None
    last_ts = max(timestamps) if timestamps else None

    session_id = ""
    model = ""
    total_turns = 0

    # Token accumulators
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_creation_5m = 0
    total_cache_creation_1h = 0

    # Tool tracking
    tool_metrics: dict[str, dict] = {}
    pending_tool_uses: dict[str, dict] = {}  # tool_use_id -> {name, timestamp, input_size}

    # Thinking tracking
    thinking_sequences: list[dict] = []

    # Error tracking
    errors: list[dict] = []

    # Timeline
    timeline: list[dict] = []

    # Script attempt tracking
    dh_exec_attempts: list[dict] = []

    # Track seen assistant message IDs to deduplicate streaming chunks
    seen_assistant_msg_ids: set[str] = set()

    # File read tracking — which files did the agent read?
    files_read: list[dict] = []

    for event in events:
        event_type = event.get("type")
        ts = event.get("timestamp")
        rel_ms = 0
        if ts and first_ts:
            rel_ms = int((parse_timestamp(ts) - first_ts).total_seconds() * 1000)

        if "sessionId" in event:
            session_id = event["sessionId"]

        if event_type == "user" and not event.get("isMeta"):
            total_turns += 1
            msg = event.get("message", {})
            content = msg.get("content", [])

            timeline.append({
                "turn": total_turns,
                "timestamp_relative_ms": rel_ms,
                "type": "user",
                "event": "message",
            })

            # Process tool results
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_use_id = block.get("tool_use_id", "")
                        is_err = block.get("is_error", False)
                        result_text = extract_content_text(block.get("content", ""))

                        # Match to pending tool use
                        tool_info = pending_tool_uses.pop(tool_use_id, None)
                        tool_name = tool_info["name"] if tool_info else "unknown"

                        if tool_name not in tool_metrics:
                            tool_metrics[tool_name] = {
                                "invocation_count": 0,
                                "success_count": 0,
                                "error_count": 0,
                                "total_input_size_chars": 0,
                                "total_output_size_chars": 0,
                                "durations_ms": [],
                            }

                        tm = tool_metrics[tool_name]
                        tm["invocation_count"] += 1
                        tm["total_output_size_chars"] += len(result_text)

                        if tool_info:
                            tm["total_input_size_chars"] += tool_info.get("input_size", 0)
                            if tool_info.get("timestamp_ms"):
                                duration = rel_ms - tool_info["timestamp_ms"]
                                tm["durations_ms"].append(duration)

                        has_err = is_err or has_traceback(result_text)
                        if has_err:
                            tm["error_count"] += 1
                            err_type = detect_error_type(result_text)

                            # Track dh exec errors
                            if tool_name == "Bash" and "dh exec" in (tool_info or {}).get("input_text", ""):
                                error_msg = result_text[:200]
                                match = re.search(r"(\w+Error|\w+Exception): (.+?)(?:\n|$)", result_text)
                                error_msg = match.group(0).strip() if match else error_msg[:100]
                                dh_exec_attempts.append({
                                    "turn": total_turns,
                                    "success": False,
                                    "error_type": err_type,
                                    "error_message": error_msg,
                                })

                            errors.append({
                                "turn": total_turns,
                                "tool": tool_name,
                                "error_type": err_type or "Unknown",
                                "message": result_text[:200],
                            })
                        else:
                            tm["success_count"] += 1
                            # Track successful dh exec
                            if tool_name == "Bash" and "dh exec" in (tool_info or {}).get("input_text", ""):
                                dh_exec_attempts.append({
                                    "turn": total_turns,
                                    "success": True,
                                })

        elif event_type == "assistant":
            msg = event.get("message", {})
            msg_id = msg.get("id", "")
            is_new_call = True
            if msg_id:
                if msg_id in seen_assistant_msg_ids:
                    is_new_call = False
                else:
                    seen_assistant_msg_ids.add(msg_id)
            if is_new_call:
                total_turns += 1
            content = msg.get("content", [])
            usage = msg.get("usage", {})

            if not model and "model" in msg:
                model = msg["model"]

            # Accumulate tokens
            total_input += usage.get("input_tokens", 0)
            total_output += usage.get("output_tokens", 0)
            total_cache_read += usage.get("cache_read_input_tokens", 0)
            cache_creation = usage.get("cache_creation", {})
            total_cache_creation_5m += cache_creation.get("ephemeral_5m_input_tokens", 0)
            total_cache_creation_1h += cache_creation.get("ephemeral_1h_input_tokens", 0)

            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")

                    if btype == "thinking":
                        thinking_text = block.get("thinking", "")
                        thinking_sequences.append({
                            "turn": total_turns,
                            "char_length": len(thinking_text),
                            "word_count": len(thinking_text.split()),
                        })
                        timeline.append({
                            "turn": total_turns,
                            "timestamp_relative_ms": rel_ms,
                            "type": "assistant",
                            "event": "thinking",
                            "words": len(thinking_text.split()),
                        })

                    elif btype == "text":
                        text = block.get("text", "")
                        if text.strip():
                            timeline.append({
                                "turn": total_turns,
                                "timestamp_relative_ms": rel_ms,
                                "type": "assistant",
                                "event": "text",
                            })

                    elif btype == "tool_use":
                        tool_name = block.get("name", "unknown")
                        tool_id = block.get("id", "")
                        inp = block.get("input", {})
                        inp_str = json.dumps(inp) if isinstance(inp, dict) else str(inp)

                        pending_tool_uses[tool_id] = {
                            "name": tool_name,
                            "timestamp_ms": rel_ms,
                            "input_size": len(inp_str),
                            "input_text": inp_str[:500],
                        }

                        target = ""
                        if isinstance(inp, dict):
                            target = inp.get("file_path", inp.get("pattern", inp.get("command", "")))
                            if isinstance(target, str) and len(target) > 100:
                                target = target[:100]

                        timeline.append({
                            "turn": total_turns,
                            "timestamp_relative_ms": rel_ms,
                            "type": "assistant",
                            "event": "tool_use",
                            "tool": tool_name,
                            "target": str(target),
                        })

                        # Track file reads (Read tool with file_path, Glob with pattern)
                        if tool_name == "Read" and isinstance(inp, dict):
                            fp = inp.get("file_path", "")
                            if fp:
                                files_read.append({
                                    "turn": total_turns,
                                    "tool": "Read",
                                    "path": fp,
                                    "timestamp_relative_ms": rel_ms,
                                })
                        elif tool_name == "Glob" and isinstance(inp, dict):
                            pat = inp.get("pattern", "")
                            if pat:
                                files_read.append({
                                    "turn": total_turns,
                                    "tool": "Glob",
                                    "path": pat,
                                    "timestamp_relative_ms": rel_ms,
                                })

    # Compute derived metrics
    duration_seconds = 0.0
    if first_ts and last_ts:
        duration_seconds = (last_ts - first_ts).total_seconds()

    estimated_cost = (
        (total_input / 1_000_000) * PRICING["input"]
        + (total_output / 1_000_000) * PRICING["output"]
        + (total_cache_read / 1_000_000) * PRICING["cache_read"]
        + (total_cache_creation_5m / 1_000_000) * PRICING["cache_creation_5m"]
        + (total_cache_creation_1h / 1_000_000) * PRICING["cache_creation_1h"]
    )

    # Finalize tool metrics
    tool_metrics_final = {}
    for name, tm in tool_metrics.items():
        count = tm["invocation_count"]
        tool_metrics_final[name] = {
            "invocation_count": count,
            "success_count": tm["success_count"],
            "error_count": tm["error_count"],
            "avg_input_size_chars": tm["total_input_size_chars"] // count if count else 0,
            "avg_output_size_chars": tm["total_output_size_chars"] // count if count else 0,
            "durations_ms": tm["durations_ms"],
        }

    # Error type frequency
    error_types: dict[str, int] = {}
    for err in errors:
        et = err["error_type"]
        error_types[et] = error_types.get(et, 0) + 1

    # Recovery tracking
    for i, err in enumerate(errors):
        # Look for next successful dh exec after this error
        err_turn = err["turn"]
        recovered = False
        recovery_turns = 0
        for attempt in dh_exec_attempts:
            if attempt["turn"] > err_turn and attempt["success"]:
                recovered = True
                recovery_turns = attempt["turn"] - err_turn
                break
        err["recovered"] = recovered
        err["recovery_turns"] = recovery_turns

    recovery_count = sum(1 for e in errors if e.get("recovered"))
    recovery_rate = recovery_count / len(errors) if errors else 1.0

    # Script attempts
    script_attempts = {
        "total_attempts": len(dh_exec_attempts),
        "first_success_attempt": None,
        "errors_per_attempt": {},
    }
    for i, attempt in enumerate(dh_exec_attempts, 1):
        if attempt["success"] and script_attempts["first_success_attempt"] is None:
            script_attempts["first_success_attempt"] = i
        if not attempt["success"]:
            script_attempts["errors_per_attempt"][str(i)] = [
                attempt.get("error_message", "unknown")
            ]
        else:
            script_attempts["errors_per_attempt"][str(i)] = []

    # Thinking summary
    total_thinking_words = sum(t["word_count"] for t in thinking_sequences)

    # Classify files read — identify skill files vs other
    # Only count actual skill directory reads (not tools/, plans/, etc.)
    def is_skill_file(path: str) -> bool:
        """Check if a path points to a file inside a skill directory."""
        # Must be a concrete file read (not a glob pattern)
        if "*" in path or "?" in path:
            return False
        # Match paths like skills/*/SKILL.md, skills/*/references/*.md,
        # .agents/skills/*/SKILL.md, .agents/skills/*/references/*.md
        parts = path.replace("\\", "/").split("/")
        for i, part in enumerate(parts):
            if part in ("skills", ".agents") and i + 1 < len(parts):
                # Look for a skill directory structure after skills/ or .agents/skills/
                remaining = "/".join(parts[i:])
                if "SKILL.md" in remaining or "/references/" in remaining:
                    return True
        return False

    skill_files_read = []
    other_files_read = []
    for fr in files_read:
        path = fr["path"]
        entry = {"path": path, "turn": fr["turn"], "tool": fr["tool"]}
        if is_skill_file(path):
            skill_files_read.append(entry)
        else:
            other_files_read.append(entry)

    # Deduplicated list of unique skill file paths read
    skill_paths_read = sorted(set(fr["path"] for fr in skill_files_read))

    return {
        "session_id": session_id,
        "eval_name": eval_name,
        "model": model,
        "duration_seconds": round(duration_seconds, 1),
        "total_turns": total_turns,
        "token_usage": {
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cache_read_tokens": total_cache_read,
            "total_cache_creation_5m_tokens": total_cache_creation_5m,
            "total_cache_creation_1h_tokens": total_cache_creation_1h,
            "estimated_cost_usd": round(estimated_cost, 2),
        },
        "tool_metrics": tool_metrics_final,
        "thinking_metrics": {
            "total_thinking_sequences": len(thinking_sequences),
            "total_thinking_words": total_thinking_words,
            "avg_words_per_sequence": (
                total_thinking_words // len(thinking_sequences) if thinking_sequences else 0
            ),
            "max_words_single_sequence": (
                max(t["word_count"] for t in thinking_sequences) if thinking_sequences else 0
            ),
        },
        "error_metrics": {
            "total_errors": len(errors),
            "error_types": error_types,
            "errors": errors,
            "recovery_success_rate": round(recovery_rate, 2),
        },
        "timeline": timeline,
        "script_attempts": script_attempts,
        "files_read": {
            "total_files_read": len(files_read),
            "skill_files_read": skill_paths_read,
            "skill_files_count": len(skill_paths_read),
            "all_reads": [{"path": fr["path"], "turn": fr["turn"], "tool": fr["tool"]} for fr in files_read],
        },
    }


def parse_session_log(jsonl_path: Path, output_dir: Path):
    """Parse a session log and write transcript + metrics."""
    events = load_session(jsonl_path)
    eval_name = output_dir.name

    transcript = generate_transcript(events, eval_name)
    (output_dir / "transcript.md").write_text(transcript)

    metrics = extract_metrics(events, eval_name)
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Parse Claude Code session logs")
    parser.add_argument("jsonl_path", type=Path, help="Path to raw.jsonl file")
    parser.add_argument("--output-dir", type=Path, help="Output directory (default: same as input)")

    args = parser.parse_args()

    if not args.jsonl_path.exists():
        print(f"Error: {args.jsonl_path} not found", file=sys.stderr)
        sys.exit(1)

    output_dir = args.output_dir or args.jsonl_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    parse_session_log(args.jsonl_path, output_dir)
    print(f"Wrote: {output_dir / 'transcript.md'}")
    print(f"Wrote: {output_dir / 'metrics.json'}")


if __name__ == "__main__":
    main()
