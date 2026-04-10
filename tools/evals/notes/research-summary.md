# Evals2 Research Summary

## What We're Building

A new eval pipeline for the `deephaven-core-query-writing` skill that replaces Playwright-based UI testing with `dh render`-based validation. The goal is quantifiable, systematic skill improvement.

## Key Problems with Evals v1

### 1. Playwright is the bottleneck
- Phases 3-5 (read playwright skill, write test, fix loop) consume ~60% of eval time and tokens
- The agent must read 4 Playwright skill files, write a custom test script, debug DOM selectors
- Playwright tests are flaky: cold-start races, overlay rendering issues, table-backed picker timing
- Fix loop iterations often fix Playwright issues, not dashboard issues
- The eval measures "can the agent write Playwright tests" as much as "can the agent write Deephaven code"

### 2. `dh exec` doesn't catch runtime errors
- Errors inside `@ui.component` render functions only surface when the dashboard renders
- `dh exec` validates script load-time only — lazy evaluation means plots/components aren't exercised
- 2/12 evals in the latest run had errors only found via Playwright screenshots

### 3. Signal-to-noise ratio
- Playwright test pass/fail conflates UI testing skill with Deephaven coding skill
- Hard to attribute failures: was it a bad dashboard or a bad test?
- Cost: ~$5-10 per eval, 200-10000+ seconds per eval

## How `dh render` Changes Everything

`dh render script.py` renders a deephaven.ui widget headlessly and provides:

### What it gives us (replacing Playwright entirely):
1. **`snapshot`** — Prints accessibility tree (what components rendered, their state)
2. **`click <target>`** — Click by text or @ref (interactive component testing)
3. **`fill <target> <value>`** — Fill text fields
4. **`select <target> <value>`** — Select picker options
5. **`tables`** — List all exported tables
6. **`table <id>`** — Fetch actual table data (row values!)
7. **`html`** — Dump rendered HTML
8. **`wait <ms>`** — Pause for async effects
9. **`diagnose`** — JSON diagnostic report for rendering issues
10. **Actions chain** — `dh render script.py fill "Name" "Alice" click "Submit" snapshot`

### Critical advantages:
- **No browser needed** — runs headlessly in a VM
- **No test script needed** — actions are CLI arguments, not a Python test
- **Catches runtime errors** — actually renders the UI components, exercising lazy evaluation
- **Table data verification** — can fetch actual table contents and verify values
- **Deterministic** — no CSS timing, no DOM race conditions
- **Fast** — ~15s timeout vs minutes for Playwright
- **Composable** — chain actions left-to-right

## New Eval Design Philosophy

### From skill-creator best practices:
1. **Assertions must be discriminating** — pass when skill genuinely helps, fail when it doesn't
2. **Binary pass/fail per assertion** with evidence
3. **With-skill vs without-skill baseline** comparison
4. **Focus on the skill's domain** — Deephaven coding quality, not test-writing ability
5. **Quantitative + qualitative** — automated metrics + human review

### Proposed eval phases (replacing 6-phase approach):

#### Phase 1: Write Dashboard Script (same as v1)
- Read manifest.json, write a dashboard script
- With-skill variant reads SKILL.md + references first

#### Phase 2: Verify with `dh exec` (same as v1)
- `dh exec script.py` — validates script loads without error
- Up to N retries on failure

#### Phase 3: Render Validation with `dh render` (NEW — replaces Phases 3-5)
- `dh render script.py snapshot` — get accessibility tree, verify components rendered
- `dh render script.py tables` — list exported tables, verify data pipeline works
- `dh render script.py table <id>` — fetch actual data, verify correctness
- `dh render script.py select "Filter" "value" snapshot` — test interactivity
- `dh render script.py diagnose` — get diagnostic report if issues found

#### Phase 4: Structured Scoring (NEW — replaces Phase 6)
- Score the dashboard on multiple dimensions using dh render output
- No LLM-in-the-loop for scoring — deterministic checks where possible

### What we can check deterministically:
1. **Script executes** — `dh exec` exit code 0
2. **Dashboard renders** — `dh render snapshot` produces accessibility tree
3. **Components present** — parse accessibility tree for expected component types
4. **Tables have data** — `dh render tables` lists tables, `table <id>` returns rows
5. **Interactivity works** — `dh render select/click/fill` doesn't error
6. **No runtime errors** — `dh render diagnose` reports no errors
7. **Data correctness** — fetch table data and verify expected columns/values exist

### What needs LLM grading:
1. **Dashboard quality** — is the analysis meaningful/insightful?
2. **Code quality** — idiomatic Deephaven patterns, clean structure
3. **Visualization choices** — appropriate chart types for the data

## Scoring Dimensions

### Tier 1: Automated (deterministic, cheap)
- `script_runs`: Does `dh exec` succeed? (bool)
- `dashboard_renders`: Does `dh render snapshot` succeed? (bool)
- `component_count`: How many UI components rendered? (int)
- `table_count`: How many tables exported? (int)
- `tables_have_data`: Do tables have non-zero rows? (bool)
- `interactivity_works`: Do select/click actions succeed? (bool)
- `exec_attempts`: How many `dh exec` retries needed? (int, lower is better)
- `render_errors`: Count of errors from `dh render diagnose` (int, 0 is best)

### Tier 2: Data verification (deterministic, medium cost)
- `uses_csv_data`: Does the dashboard actually load and display the CSV data? (bool)
- `has_aggregations`: Does it perform meaningful data transformations? (bool — check table schemas)
- `has_filters`: Are there interactive filters? (bool — check for picker/select in accessibility tree)
- `has_charts`: Are there visualizations? (bool — check for plot components)

### Tier 3: LLM-graded (expensive, run optionally)
- `analysis_quality`: 1-5 score of how insightful the dashboard is
- `code_quality`: 1-5 score of Deephaven API usage
- `ux_quality`: 1-5 score of dashboard layout/organization

## Token/Cost Reduction

v1: ~$5-10 per eval, mostly from Playwright phases
v2 target: ~$2-4 per eval by eliminating Playwright test writing entirely

The agent's job is simplified to:
1. Read manifest + (optionally) skill references
2. Write a dashboard script
3. Fix it if `dh exec` fails

The eval harness (not the agent) handles validation via `dh render`.

## Implementation Plan

1. Create eval runner that uses `dh render` for validation
2. Define assertion schema compatible with skill-creator's grading system
3. Reuse existing datasets and manifests from evals/data/
4. Support `--with-skills` / baseline comparison
5. Produce benchmark.json compatible with skill-creator's eval-viewer
6. Build automated scoring from `dh render` outputs
7. Optional LLM grading pass for quality scores

## Open Questions

- Should we still have the agent write skill-recommendations.md, or derive recommendations from automated metrics?
- How many `dh render` actions should we run per eval? (snapshot + tables + one interaction seems like a good default)
- Should the eval harness pre-analyze the manifest to determine expected interactions (e.g., if the script has a picker, try selecting)?
- What's the right threshold for "component_count" — is 3 components enough for a good dashboard?
