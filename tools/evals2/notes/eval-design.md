# Evals2 Design

## Architecture Overview

```
evals2/
├── notes/                    # Research and design docs (this folder)
├── data/                     # Symlink or reference to ../evals/data/
├── runs/                     # Run output directories
│   └── {RUN_ID}/
│       ├── run-config.json
│       ├── benchmark.json    # Aggregate scores
│       ├── eval-results.md   # Summary table
│       └── {dataset}/
│           ├── eval-result.json     # Per-eval metadata
│           ├── script.py            # Generated dashboard
│           ├── exec-output.txt      # dh exec stdout/stderr
│           ├── render-snapshot.txt  # Accessibility tree
│           ├── render-tables.json   # Table listing
│           ├── render-diagnose.json # Diagnostic report
│           ├── scores.json          # Automated scores
│           └── raw.jsonl            # Session log
├── run_evals.py              # Main orchestrator
├── score.py                  # Automated scoring from dh render outputs
├── prompt.md                 # Eval prompt template
└── pyproject.toml            # Or add entry points to parent pyproject.toml
```

## Eval Prompt (Simplified)

The agent prompt is dramatically simpler than v1 — no Playwright phases at all:

```
{SKILL_PREAMBLE}

## Phase 1: Read Manifest and Write Dashboard Script
1. Read manifest at {DATA_DIR}/manifest.json
2. Write a single Python script that:
   - Loads CSV data with deephaven.read_csv()
   - Performs meaningful data analysis
   - Creates a deephaven.ui dashboard with multiple views/charts
   - Has interactive elements (pickers, filters)
3. Write to {OUTPUT_DIR}/script.py

## Phase 2: Verify Script
Run: dh exec --vm {OUTPUT_DIR}/script.py --timeout 120
- Fix and retry up to 8 times if it fails
- Do not proceed until exit code 0

## Phase 3: Write Reflection
Write {OUTPUT_DIR}/skill-recommendations.md (max 40 lines):
- Errors encountered with exact messages
- Fixes applied
- What documentation would have prevented errors
```

That's it. 3 phases instead of 6. No Playwright, no dh serve, no fix loop.

## Validation (Harness-Side, Not Agent-Side)

After the agent finishes, the harness runs validation:

### Step 1: dh exec check
```bash
dh exec --vm {script} --timeout 120
```
- Exit code 0 = script runs
- Capture stderr for error analysis

### Step 2: dh render snapshot
```bash
dh render --vm {script} snapshot
```
- Parse accessibility tree
- Count components by type
- Check for dashboard structure

### Step 3: dh render tables
```bash
dh render --vm {script} tables --json
```
- List exported tables
- Verify tables have data

### Step 4: dh render table (per table)
```bash
dh render --vm {script} table {table_id} --json --rows 5
```
- Fetch actual data
- Verify columns match manifest expectations

### Step 5: dh render diagnose
```bash
dh render --vm {script} diagnose --json
```
- Check for runtime errors
- Catch lazy-evaluation failures

### Step 6: Interaction test (if applicable)
```bash
# Parse accessibility tree for interactive elements
# If picker found:
dh render --vm {script} select "PickerLabel" "SomeValue" wait 1000 snapshot
```
- Verify interactivity works
- Compare before/after snapshots

## Scoring Schema

```json
{
  "dataset": "abcsds--pokemon",
  "run_id": "20260325-120000",
  "config": "with_skill",
  "scores": {
    "script_executes": { "value": true, "attempts": 1 },
    "dashboard_renders": { "value": true },
    "component_count": { "value": 8 },
    "component_types": {
      "panels": 4,
      "charts": 3,
      "pickers": 1,
      "tables": 1,
      "tabs": 2
    },
    "tables_exported": { "value": 3, "names": ["t1", "t2", "t3"] },
    "tables_have_data": { "value": true },
    "render_errors": { "value": 0 },
    "interactivity_works": { "value": true, "tested": ["select Region northeast"] },
    "exec_attempts": { "value": 1 },
    "has_aggregations": { "value": true },
    "has_filters": { "value": true },
    "has_charts": { "value": true }
  },
  "pass_rate": 1.0,
  "cost_usd": 2.50,
  "duration_seconds": 120,
  "tokens": { "input": 5000, "output": 3000, "cache_read": 50000 }
}
```

## Comparison Strategy

Run each dataset twice:
1. **with_skill** — agent reads SKILL.md + references before coding
2. **without_skill** — agent uses only its own knowledge

Compare:
- `exec_attempts` — does the skill reduce retries?
- `component_count` — does the skill produce richer dashboards?
- `render_errors` — does the skill produce fewer runtime errors?
- `interactivity_works` — does the skill lead to working interactions?
- `pass_rate` — overall success rate
- `cost_usd` — efficiency

## Compatibility with skill-creator

Output benchmark.json in the format skill-creator's eval-viewer expects:
- `runs[]` with `eval_id`, `eval_name`, `configuration`, `result`
- `run_summary` with mean/stddev/delta per configuration
- Can use `generate_review.py` for human review

## Next Steps

1. Write the simplified prompt template
2. Write the harness (run_evals.py) that orchestrates claude -p + dh render validation
3. Write the scorer that parses dh render outputs into scores.json
4. Test on 2-3 datasets to validate the approach
5. Run full suite and compare with-skill vs without-skill
