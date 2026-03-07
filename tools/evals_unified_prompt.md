# Unified Eval Task

{SKILL_PREAMBLE}

DO NOT explore the repository. DO NOT read CLAUDE.md, AGENTS.md, or any files outside the eval and skill directories. DO NOT perform any web searches. You only have the instructions in this prompt.

You will complete ALL phases below in this single session. Do not stop early.

---

## Phase 1: Read Manifest and Write Dashboard Script

1. Read the manifest file at: {DATA_DIR}/manifest.json

2. Based on the manifest (dataset title, description, column schemas, file names), write a SINGLE Python script that:
   a. Loads the CSV data using `deephaven.read_csv()`
   b. Performs meaningful data analysis using Deephaven table operations (filters, aggregations, joins, sorts, formulas, etc.)
   c. Creates a `deephaven.ui` dashboard: `dashboard = ui.dashboard(layout())`
   d. The dashboard should have different views/charts that reveal interesting patterns in the data
   e. Make the dashboard visually organized with clear labels

3. Write the script to: {OUTPUT_DIR}/{SCRIPT_NAME}

4. CSV file paths in the script must use the RELATIVE path from the project root. The CSV files are located at `{DATA_DIR}/`. For example, if the data dir is `evals/data/abcsds--pokemon` and it contains `Pokemon.csv`, use `deephaven.read_csv("evals/data/abcsds--pokemon/Pokemon.csv")`. Do NOT use absolute paths.

---

## Phase 2: Verify Script with dh exec

Run the script to verify it works:

```
dh exec --vm --no-show-tables {OUTPUT_DIR}/{SCRIPT_NAME} --timeout 120
```

- If it fails, read the error, fix the script, and retry
- You may retry up to 8 times
- After each fix, write the updated script and re-run

Do NOT proceed to Phase 3 until the script runs successfully (exit code 0), or you have exhausted all 8 retry attempts.

---

## Phase 3: Read Playwright Skill Files (MANDATORY)

Before writing any Playwright test, you MUST read these files and understand them:

- `.agents/skills/deephaven-playwright/SKILL.md` (main skill)
- `.agents/skills/deephaven-playwright/references/dom-selectors.md`
- `.agents/skills/deephaven-playwright/references/dashboard-patterns.md`
- `.agents/skills/deephaven-playwright/references/table-backed.md`

Do not proceed to Phase 4 until you have read all of these files. They contain critical information about DH-specific DOM selectors, Spectrum component pitfalls, panel/dashboard wait strategies, and table-backed component patterns.

---

## Phase 4: Serve Dashboard, Write and Run Playwright Test

### 4a. Start the dashboard server

Run the dashboard server in the background and save its PID:

```
dh serve {OUTPUT_DIR}/{SCRIPT_NAME} --no-browser --iframe dashboard &
echo $! > {OUTPUT_DIR}/dh-serve.pid
```

Wait a few seconds for it to start. The server will print a URL with a port number (e.g., `localhost:10000`). The dashboard URL will be:
`http://localhost:<PORT>/iframe/widget/?name=dashboard`

**IMPORTANT — Stopping the server safely:**
Multiple evals may run in parallel, each with its own `dh serve` process. You MUST stop the server using its saved PID — never use `pkill`, `killall`, or any pattern-based kill command, as those will kill other evals' servers too.

```
kill $(cat {OUTPUT_DIR}/dh-serve.pid) 2>/dev/null
```

### 4b. Write the Playwright test

Analyze the dashboard script from Phase 1. Identify all `@ui.component` decorated functions, the component tree, and every interactive element.

Write a Playwright Python test to: {OUTPUT_DIR}/playwright-test.py

The test must use `playwright.sync_api`. Structure:

```python
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

DASHBOARD_URL = "<the URL from 4a>"
OUTPUT_DIR = Path("{OUTPUT_DIR}").resolve()
SCREENSHOTS_DIR = OUTPUT_DIR / "screenshots"
RESULTS_FILE = OUTPUT_DIR / "playwright-results.json"


def retry(fn, *, timeout=15_000, interval=1_000):
    """Retry fn() until it succeeds or timeout (ms) is reached."""
    deadline = time.monotonic() + timeout / 1000
    last_error = None
    while time.monotonic() < deadline:
        try:
            fn()
            return
        except Exception as e:
            last_error = e
            time.sleep(interval / 1000)
    if last_error:
        raise last_error


def main():
    component_tests = []
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Navigate and wait for dashboard
        page.goto(DASHBOARD_URL)
        # ... wait for selectors, take screenshots, test components ...

        # Write results
        results = {
            "eval_name": "{EVAL_NAME}",
            "dashboard_url": DASHBOARD_URL,
            "initial_load": {
                "success": True,
                "screenshot": "screenshots/initial-load.png",
            },
            "component_tests": component_tests,
            "summary": {
                "total_components": len(component_tests),
                "tested": sum(
                    1 for t in component_tests if t["result"] != "not_found"
                ),
                "passed": sum(
                    1 for t in component_tests if t["result"] == "pass"
                ),
                "failed": sum(
                    1 for t in component_tests if t["result"] == "fail"
                ),
            },
        }
        RESULTS_FILE.write_text(json.dumps(results, indent=2))

        browser.close()


if __name__ == "__main__":
    main()
```

**Test flow:**

1. Navigate to DASHBOARD_URL
2. Wait for `.lm_stack` selector (dashboard layout) and `.dh-inner-react-panel`. Use 30s timeout. If timeout, take a screenshot anyway and record the failure.
3. Take initial screenshot: `screenshots/initial-load.png`
4. Test each interactive component:
   - Locate using correct selector strategy (see Playwright skill for ARIA roles)
   - Perform interaction (click, fill, select, toggle)
   - Wait for state updates (0.5-1s)
   - Take a screenshot
   - Record pass/fail

**Do NOT capture console logs or page errors.** They are not meaningful for eval results and waste context space. Do not set up `page.on("console", ...)` or `page.on("pageerror", ...)` handlers.

**Deephaven-specific patterns (from the Playwright skill):**
- Overlays render OUTSIDE the panel — use `page.get_by_role()` not `panel.get_by_role()` for dialogs/dropdowns
- Use `click()` not `check()`/`uncheck()` for Spectrum checkboxes/switches
- Visit every tab in every stack. Use `.lm_tab` selectors and check `.lm_active` class
- Table-backed pickers: use `retry()` loop (retries with 1s interval, 15s total timeout)
- Cold-start race: tab click handlers may not be attached on first load — retry tab clicks

**Test structure** — use a single `main()` function that tests all components sequentially and writes results at the end:

```python
def main():
    component_tests = []
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Navigate and wait for dashboard
        page.goto(DASHBOARD_URL)
        # ... wait for selectors, take screenshots, test components ...

        # Write results
        results = {
            "eval_name": "{EVAL_NAME}",
            "dashboard_url": DASHBOARD_URL,
            "initial_load": {"success": True, "screenshot": "screenshots/initial-load.png"},
            "component_tests": component_tests,
            "summary": {
                "total_components": len(component_tests),
                "tested": sum(1 for t in component_tests if t["result"] != "not_found"),
                "passed": sum(1 for t in component_tests if t["result"] == "pass"),
                "failed": sum(1 for t in component_tests if t["result"] == "fail"),
            },
        }
        RESULTS_FILE.write_text(json.dumps(results, indent=2))

        browser.close()


if __name__ == "__main__":
    main()
```

**Results format** — write to `playwright-results.json`:

```json
{
  "eval_name": "{EVAL_NAME}",
  "dashboard_url": "DASHBOARD_URL",
  "initial_load": {
    "success": true,
    "screenshot": "screenshots/initial-load.png"
  },
  "component_tests": [
    {
      "component": "component_name",
      "type": "ui.picker",
      "action": "select_option",
      "result": "pass",
      "error": "",
      "screenshot": "screenshots/component-action.png"
    }
  ],
  "summary": {
    "total_components": 0,
    "tested": 0,
    "passed": 0,
    "failed": 0
  }
}
```

**Constraints:**
- Do NOT modify the dashboard script
- Do NOT use Deephaven APIs in the test — pure Playwright against the browser DOM
- Use `playwright.sync_api` only
- Create `screenshots/` directory before saving screenshots using `SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)`
- Wrap each component test in try/except so one failure doesn't abort all tests
- If a component can't be located, record it as `"not_found"` rather than failing

### 4c. Run the test

Playwright and its browsers are pre-installed in the tools environment. No per-eval installation needed.

Run the test:
```
python {OUTPUT_DIR}/playwright-test.py
```

If the test script itself has errors (not component failures), fix the test script and re-run up to 3 times.

---

## Phase 5: Fix Loop

Read `{OUTPUT_DIR}/playwright-results.json`. Check for actionable failures:
- `initial_load.success` is False
- Any `component_tests` with `"result": "fail"` or `"result": "not_found"`
- `summary.failed > 0`

If there are no actionable failures, skip to Phase 6.

If there ARE failures, iterate up to {MAX_FIX_ITERATIONS} times:

1. Read the Playwright results to identify failures
2. Make **minimal, targeted fixes** to `{OUTPUT_DIR}/{SCRIPT_NAME}` — only change what is necessary
3. Verify the fix: `dh exec --vm --no-show-tables {OUTPUT_DIR}/{SCRIPT_NAME} --timeout 120`
4. If dh exec fails, fix and retry (up to 3 sub-attempts)
5. Stop your server by PID: `kill $(cat {OUTPUT_DIR}/dh-serve.pid) 2>/dev/null`, then re-serve: `dh serve {OUTPUT_DIR}/{SCRIPT_NAME} --no-browser --iframe dashboard & echo $! > {OUTPUT_DIR}/dh-serve.pid`
6. Update `DASHBOARD_URL` in `{OUTPUT_DIR}/playwright-test.py` if the port changed
7. Re-run: `python {OUTPUT_DIR}/playwright-test.py`
8. If no more actionable failures, stop the loop

After the loop ends, stop your server: `kill $(cat {OUTPUT_DIR}/dh-serve.pid) 2>/dev/null`

---

## Phase 6: Write Skill Recommendations

Write a brief reflection to: {OUTPUT_DIR}/skill-recommendations.md

Focus ONLY on scripting errors (Phases 1-2 and the script-fix parts of Phase 5). Do NOT include Playwright test failures, selectors, or UI testing issues — those are tracked separately.

Content (max 60 lines):
- **Errors encountered:** List every distinct error you hit during script writing and verification (Phase 2) and script fixes (Phase 5). For each error include:
  - The exact error message or traceback (copy-paste the key line, e.g. `TypeError: table.__init__() got an unexpected keyword argument 'label'`)
  - Which dh exec attempt number triggered it
  - What code caused it (the offending line or pattern)
- **Fixes applied:** For each error above, what you changed and why. Include before/after code snippets where helpful.
- **Skill gaps:** What documentation or examples would have prevented these scripting errors? What Deephaven API patterns were unclear or missing?
- **Metrics:** Number of dh exec attempts, number of fix loop iterations

Keep it factual. This will be aggregated across evals to identify patterns — the actual error messages are essential for diagnosis.
