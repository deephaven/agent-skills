# Deephaven Agent Skills

Agent skills for working with [Deephaven Core](https://deephaven.io) real-time data processing, following the [agentskills.io specification](https://agentskills.io/specification).

> [!CAUTION]
> These skills are in early development and may give incomplete or inaccurate recommendations to agents. It is not recommended for production use at this time. Feedback and contributions are welcome to help improve these skills. Kafka and Iceberg sections are particularly in need of review and expansion. Evals are being developed to help identify areas for improvement.

## Installation

```bash
npx skills add deephaven/agent-skills
```

## Skills

### deephaven-core-query-writing

Comprehensive skill for Deephaven real-time data processing covering:

- Table operations (select, update, view, filter, sort)
- Joins (natural, exact, as-of, reverse as-of, range, cross)
- Aggregations (sum, avg, count, first/last, weighted, combined)
- Time-series operations (parsing, binning, calendars, timezones)
- Update-by operations (rolling, cumulative, EMA)
- Kafka streaming (consume, produce, table types)
- Iceberg integration (catalogs, read/write, partitioned tables)
- UI dashboards (components, hooks, layouts, styling)
- Plotting with Deephaven Express (dx)

## Supported Agents

Skills are agent-agnostic—the same skill works across all supported AI coding assistants:

## Repository Structure

```
skills/
  deephaven-core-query-writing/
    SKILL.md              # Main skill definition
    references/           # Detailed topic guides
      aggregations.md
      iceberg.md
      joins.md
      kafka.md
      plotting.md
      sitemap.md
      time-operations.md
      ui.md
      updateby.md
tools/                    # Validation tooling
```

## Development

### Local Testing

Install the skill into your current repo from a local checkout:

```bash
npx skills add .
```

### Validation

Lint and run requires dh cli private tool that is not yet available.

```bash
cd tools
uv sync
uv run validate                   # Validate structure and frontmatter
uv run check-python               # Check Python code block syntax
uv run check-links                # Check internal markdown links
uv run check-external-links       # Check external URLs
uv run lint-blocks                # Ruff lint Python code blocks
uv run run-each-block             # Run each Python block against Deephaven (requires dh CLI)
```

#### lint-blocks

Runs `ruff check` on every Python code block extracted from the skill markdown files. Each block is linted in isolation. Blocks tagged with `# pseudo` or `# incomplete` are skipped.

```bash
uv run lint-blocks                     # lint all blocks
uv run lint-blocks joins.md            # lint blocks from one file
uv run lint-blocks --fix               # auto-fix and write changes back to markdown
uv run lint-blocks --stop-on-fail      # stop at first failure
```

#### run-each-block

Executes every Python code block from skill markdown files against a live Deephaven instance using experimental `dh exec`. Each block runs in its own isolated process so no state leaks between blocks. Blocks tagged with `# pseudo` or `# incomplete` are skipped.

Requires the `dh` cli to be installed and on PATH.

```bash
uv run run-each-block                  # run all blocks in parallel
uv run run-each-block joins.md         # run blocks from one reference file
uv run run-each-block --timeout 45     # custom per-block timeout (default: 30s)
uv run run-each-block --workers 4      # limit parallelism (default: 8)
uv run run-each-block --sequential     # disable parallelism
uv run run-each-block --stop-on-fail   # stop at first failure
```

### Evals

The eval pipeline measures how well agents write Deephaven dashboards with and without the skill loaded. Each eval runs as a single `claude -p` session that handles all phases (write → verify → test → fix → reflect). LLM-driven skill recommendations replace heuristic analysis.

Requires: `claude` CLI on PATH, `dh` CLI for Playwright testing.

```bash
cd tools
uv sync

# Download eval datasets (10 most-voted Kaggle CSVs < 3MB, ≤3 CSVs each)
uv run download-eval-data
uv run download-eval-data -n 20               # download top 20 instead of 10
uv run download-eval-data --refresh-manifests  # regenerate manifests for existing datasets

# Full pipeline: run evals → parse logs → analyze → aggregate recommendations
uv run run-evals

# Run with skill loaded (agent reads SKILL.md itself)
uv run run-evals --with-skills

# Individual stages against an existing run
uv run run-evals --stage parse --run-id 20260305-162133
uv run run-evals --stage analyze --run-id 20260305-162133
uv run run-evals --stage aggregate --run-id 20260305-162133

# Options
uv run run-evals --parallel 5                 # concurrency (default: 3)
uv run run-evals --model sonnet               # model override
uv run run-evals --datasets ds1 ds2           # specific datasets only
uv run run-evals --count 10                   # run on the first N evals (default: all)
uv run run-evals --skip-existing              # resume interrupted run
uv run run-evals --max-fix-iterations 5       # fix loop iterations (default: 3)

# Compare two runs (e.g. no-skill vs with-skill)
uv run analyze-evals --run-id run-a --compare run-b

# Parse a single session log
uv run parse-session path/to/raw.jsonl
```

Output is written to `tools/evals/runs/{RUN_ID}/`:

```
run-config.json              # run metadata
aggregate-metrics.json       # cross-eval token/cost/tool aggregation
failure-modes.md             # error rankings with affected evals
eval-results.md              # per-dataset summary table
skill-recommendations.md     # LLM-generated aggregate recommendations (aggregate stage)
{DATASET}/
  eval-result.json           # per-eval result from claude -p
  no-skill-script.py         # generated dashboard script
  raw.jsonl                  # single session log (all phases)
  transcript.md              # human-readable conversation
  metrics.json               # token usage, tool metrics, errors
  playwright-test.py         # generated Playwright test
  playwright-results.json    # structured test results
  screenshots/               # per-interaction screenshots
  skill-recommendations.md   # per-eval LLM reflection (brief)
```

## License

Apache-2.0
