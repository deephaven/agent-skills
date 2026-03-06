# Aggregate Skill Recommendations

You are generating a top-level skill recommendations report by reading per-eval recommendations and deterministic analysis reports.

**Mode:** {SKILL_MODE}

## Step 1: Read All Per-Eval Recommendations

Read each of these per-eval skill recommendation files:

{RECOMMENDATION_FILES_LIST}

## Step 2: Read Deterministic Reports

Read the following aggregate analysis files for grounding:

- `{RUN_DIR}/aggregate-metrics.json` — cross-eval token usage, tool metrics, error frequency
- `{RUN_DIR}/failure-modes.md` — error rankings with affected evals
- `{RUN_DIR}/eval-results.md` — per-dataset summary table

## Step 3: Synthesize and Write Report

Analyze all per-eval recommendations and deterministic reports. Write a consolidated report to:

`{RUN_DIR}/skill-recommendations.md`

The report should contain:

Focus ONLY on scripting errors (script writing, dh exec failures, script fixes). Do NOT include Playwright test failures, UI selectors, or component interaction issues — those are tracked separately.

### Structure

1. **Executive Summary** (3-5 bullets)
   - Overall success rate, average attempts, key patterns
   - Whether this was a no-skill or with-skill run and what that means
   - Aggregate metric highlights (token usage breakdown)

2. **Error Categories** (ranked by frequency)
   - Group scripting errors by root cause (e.g., query language syntax, Figure API misuse, column type handling, UI component API misuse, import errors)
   - For each category: how many evals affected, the **actual error messages** (copy from per-eval reports), what the agent typically did to fix it
   - Include the exact traceback line or error text — e.g. `TypeError: got an unexpected keyword argument 'label'` — not just a paraphrase. The reader must be able to identify the root cause from the report alone.
   - Cross-reference with the failure-modes.md rankings

3. **Skill Improvement Recommendations** (ranked by impact)
   - What documentation or examples would prevent the most common scripting errors
   - Specific Deephaven API patterns that need better coverage
   - Before/after examples where possible
   - Each recommendation should reference which evals it would help

### Guidelines

- Be specific and actionable — "add examples of plot_xy with filtered tables" not "improve plotting docs"
- Reference specific evals by name when citing patterns
- Prioritize by frequency × impact (an error affecting 8/10 evals matters more than one affecting 1/10)
- Keep the total report under 200 lines
- Do NOT fabricate data — only report what you find in the files
- Do NOT recommend Playwright or testing improvements — only Deephaven scripting skill improvements
