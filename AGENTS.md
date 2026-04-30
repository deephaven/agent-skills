# Agent Contributor Guide

This file is for AI agents working on this repository itself (not the skill content).

## Repository Structure

- `skills/` — Skill definitions following the [agentskills.io spec](https://agentskills.io/specification)
- `skills/deephaven-core-query-writing/SKILL.md` — Main skill file with YAML frontmatter and content
- `skills/deephaven-core-query-writing/references/` — Detailed topic guides referenced from SKILL.md
- `tools/` — Python validation tooling (uses `uv`)
- `.github/workflows/` — CI/CD workflows


## Package Management

This project uses [astral uv](https://github.com/astral-sh/uv) for Python package and project management. Always use `uv` commands instead of `pip` or other package managers:

- `uv sync` - Install dependencies from pyproject.toml/uv.lock
- `uv add <package>` - Add a new dependency
- `uv remove <package>` - Remove a dependency
- `uv run <command>` - Run a command in the project environment
- `uv pip install` - If pip-style installation is needed

## Plan File Location

When creating plans in plan mode, always save them to the `plans/` directory in this project.

**IMPORTANT:** Do NOT use the default three-random-words naming convention. Instead, always name plan files with a clear, descriptive name that reflects the plan's purpose (e.g., `plans/add_user_authentication.md`, `plans/refactor_database_layer.md`, `plans/fix_video_encoding_bug.md`).


## Adding or Editing References

1. Create/edit the markdown file in `skills/deephaven-core-query-writing/references/`
2. Add the reference to the table in `skills/deephaven-core-query-writing/SKILL.md` under "Mandatory Reference Reading"
3. Run validation: `cd tools && uv run validate`
4. Run link check: `cd tools && uv run check-links`
5. If the reference contains Python code blocks, run: `uv run check-python`

## Local Testing

Install the skill into your current repo from a local checkout:

```bash
npx skills add .
```

## Running Validation

All validation tools are in `tools/`. From that directory:

```bash
uv sync                              # Install dependencies
uv run validate                      # Structure + frontmatter validation
uv run check-python                  # Python syntax in code blocks
uv run check-links                   # Internal link resolution
uv sync --all-extras                 # Install httpx for external link checks
uv run check-external-links          # External URL checks (slow, needs network)
```

### lint-blocks

Runs `ruff check` on every Python code block extracted from the skill markdown files. Each block is linted in isolation. Blocks tagged with `# pseudo` or `# incomplete` are skipped.

```bash
uv run lint-blocks                     # lint all blocks
uv run lint-blocks joins.md            # lint blocks from one file
uv run lint-blocks --fix               # auto-fix and write changes back to markdown
uv run lint-blocks --stop-on-fail      # stop at first failure
```

### run-each-block

Executes every Python code block from skill markdown files against a live Deephaven instance using `dh exec`. Each block runs in its own isolated process so no state leaks between blocks. Blocks tagged with `# pseudo` or `# incomplete` are skipped.

Requires the `dh` CLI to be installed and on PATH.

```bash
uv run run-each-block                  # run all blocks in parallel
uv run run-each-block joins.md         # run blocks from one reference file
uv run run-each-block --timeout 45     # custom per-block timeout (default: 30s)
uv run run-each-block --workers 4      # limit parallelism (default: 8)
uv run run-each-block --sequential     # disable parallelism
uv run run-each-block --stop-on-fail   # stop at first failure
```

### count-tokens

Counts tokens (tiktoken `cl100k_base`) across `SKILL.md` and every `references/*.md`. Use this — not character/word estimates — when measuring the cost of a wording change. With two commit hashes it produces a per-file diff so you can see exactly which file moved.

```bash
uv run count-tokens                    # working tree
uv run count-tokens <hash>             # files at a commit
uv run count-tokens <hash1> <hash2>    # compare two commits, per-file delta
```

There is also `uv run token-tui` for an interactive terminal UI over the same data.

## Conventions

- Reference files are plain markdown with no frontmatter
- Python code blocks use triple-backtick with `python` language tag
- Code blocks tagged with `# pseudo` or `# incomplete` comments are skipped during syntax validation
- SKILL.md frontmatter must include: name, description, license, metadata.author, metadata.version
- The skill name must match the directory name and use lowercase with hyphens

---

## Running Code (dh CLI)

CLI tool for running Python code with Deephaven real-time data capabilities, only applies if **dh** is installed and configured properly. This is used for ad-hoc testing and validation of code snippets, especially those that interact with Deephaven.

**IMPORTANT:** Always use `dh` directly, never `uv run dh`. The CLI is installed as a standalone tool.

### Execution Pattern: Always Use Temp Scripts when doing ad-hoc runs and checks

1. Write code to `./tmp/<name>.py` using the Write tool
2. Execute with `dh exec ./tmp/<name>.py` this is the only way to execute scripts. 

**Script files will always print out table previews, you never need to print the tables** 


### Common Options

- `--timeout SECONDS` - Max execution time
- `--verbose` / `-v` - Show startup messages

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Script error (exception) |
| 2 | Connection/file error |
| 3 | Timeout exceeded |
| 130 | Interrupted (Ctrl+C) |

---

## Evals

The eval pipeline measures how well agents write Deephaven dashboards with and without the skill loaded. Each eval runs as a single `claude -p` session that handles all phases (write → verify → reflect). Required datasets are downloaded automatically before runs begin.

Requires: `claude` CLI on PATH, `dh` CLI for script verification.

```bash
cd tools
uv sync

# Download eval datasets (10 most-voted Kaggle CSVs < 3MB, ≤3 CSVs each)
uv run download-eval-data
uv run download-eval-data -n 20               # download top 20 instead of 10
uv run download-eval-data --refresh-manifests  # regenerate manifests for existing datasets

# Full pipeline: run evals → validate → parse → grade → aggregate → viewer
uv run run-evals

# Only with-skill or without-skill
uv run run-evals --config with_skill
uv run run-evals --config without_skill

# Individual stages against an existing run
uv run run-evals --stage validate --run-id 20260305-162133
uv run run-evals --stage parse --run-id 20260305-162133
uv run run-evals --stage grade --run-id 20260305-162133
uv run run-evals --stage screenshot --run-id 20260305-162133    # Playwright PNGs of each dashboard
uv run run-evals --stage aggregate --run-id 20260305-162133
uv run run-evals --stage summarize --run-id 20260305-162133

# Options
uv run run-evals --parallel 5                 # concurrency (default: 3)
uv run run-evals --model sonnet               # model override
uv run run-evals --evals 1 2 3                # specific eval IDs
uv run run-evals --skip-existing              # resume interrupted run

# Grade and aggregate standalone
uv run grade-evals --run-id 20260305-162133
uv run aggregate-evals --run-id 20260305-162133

# Parse a single session log
uv run parse-session path/to/raw.jsonl
```

### Eval Output Structure

Output is written to `tools/evals/runs/{RUN_ID}/`:

```
run-config.json              # run metadata
benchmark.json               # aggregate scores (skill-creator format)
benchmark.md                 # summary table
review.html                  # self-contained review page
{DATASET}/
  eval_metadata.json         # eval definition snapshot
  {CONFIG}/run-1/
    eval-result.json         # per-eval result from claude -p
    eval_metadata.json       # eval definition snapshot
    timing.json              # token usage and duration
    grading.json             # expectation-level pass/fail
    outputs/
      script.py              # generated dashboard script
      raw.jsonl              # session log
      transcript.md          # human-readable conversation
      metrics.json           # token usage, tool metrics
      exec-result.txt        # dh exec output
      render-result.txt      # dh render snapshot
      validation.json        # structured exec/render results
      screenshot.png         # settled Playwright capture of the dashboard
      skill-recommendations.md  # per-eval reflection
```
