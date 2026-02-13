# Deephaven Skill Eval Runner

Run this plan to evaluate Claude's ability to analyze CSV datasets and build Deephaven dashboards **without** loading any skills.

## Prerequisites

- Eval datasets must already exist in `tools/evals/data/` (run `cd tools && uv run download-eval-data` first if empty)
- `dh` CLI must be installed and working
- Chrome/Chromium available for Playwright screenshots

## Execution Plan

### Step 1: Discover eval datasets

List the directories in `tools/evals/data/`. Each directory is one eval. Store the list of directory names. Do NOT explore the rest of the repo, load skills, or read any files outside of `tools/evals/data/`.

### Step 2: Launch one sub-agent per eval dataset (in parallel)

For each eval directory, spawn a `general-purpose` sub-agent via the Task tool with `run_in_background: true`. Use model `opus` for the sub-agents.

Each sub-agent receives the prompt below. Replace `{EVAL_NAME}` with the directory name for each eval.

---BEGIN SUB-AGENT PROMPT---

You are evaluating your ability to write Deephaven data analysis code WITHOUT any skills or references loaded.

DO NOT explore the repository. DO NOT look for or load any skill files. DO NOT read CLAUDE.md, AGENTS.md, or any files outside the eval directory. DO NOT perform any web searches. You only have the instructions in this prompt.

## Your task

1. Read the manifest file at: tools/evals/data/{EVAL_NAME}/manifest.json
2. Based on the manifest (dataset title, description, column schemas, file names), write a SINGLE Python script that:
   a. Loads the CSV data using `deephaven.read_csv()`
   b. Performs meaningful data analysis using Deephaven table operations (filters, aggregations, joins, sorts, formulas, etc.)
   c. Creates a `deephaven.ui` dashboard, the dashboard must be created as `dashboard = ui.dashboard(layout())`
   d. The dashboard should have different views/charts that reveal interesting patterns in the data
   e. Make the dashboard visually organized with clear labels

3. Write the script to: tools/evals/data/{EVAL_NAME}/no-skill-script.py

4. CSV file paths in the script must be ABSOLUTE paths. The CSV files are located at:
   /home/dsmmcken/git/dsmmcken/agent-skills/tools/evals/data/{EVAL_NAME}/

5. Test the script by running: dh exec tools/evals/data/{EVAL_NAME}/no-skill-script.py --timeout 120
   - If it fails, read the error, fix the script, and retry
   - You may retry up to 5 times
   - After each fix, write the updated script and re-run

6. VERBOSE LOGGING — You MUST maintain a detailed agent log at: tools/evals/data/{EVAL_NAME}/agent-log.md
   Write to this file continuously as you work, appending after each phase. Log EVERYTHING:
   - The manifest contents you read (summary of dataset, columns, files)
   - Your reasoning about what analysis to perform and why
   - The full script you wrote (each version, clearly labeled)
   - Every `dh exec` command you ran and its COMPLETE stdout and stderr output (copy-paste the full output, do not summarize)
   - For failures: the full error traceback, your diagnosis of what went wrong, and exactly what you changed to fix it
   - For retries: clearly label each attempt (## Attempt 1, ## Attempt 2, etc.)
   Use markdown with clear `##` headers for each phase (Manifest Analysis, Script v1, Attempt 1, Attempt 2, etc.)

7. Once the script runs successfully (exit code 0), append a ## Final Summary section to the log and report back:
   - Whether the script succeeded or failed after all attempts
   - Number of attempts needed
   - A brief description of what analysis and charts you created


---END SUB-AGENT PROMPT---

### Step 3: Wait for all sub-agents to complete

Monitor the background agents. Read each agent's output file to collect results. Allow up to 10 minutes per agent.

### Step 4: Verify agent logs

Each sub-agent writes its own verbose log to `tools/evals/data/{EVAL_NAME}/agent-log.md` as it works. After all agents complete, verify each log file exists. If a sub-agent crashed before writing its log, write the agent's returned result/error to that path as a fallback.

### Step 5: Serve each dashboard and capture screenshots

For each eval where `no-skill-script.py` was created successfully:

1. Start the server: `dh serve tools/evals/data/{EVAL_NAME}/no-skill-script.py --no-browser --port {PORT} --iframe dashboard` (use ports 10001-10010, one per eval, run in background)
2. Wait for the server to print the port/URL it is listening on (look for the line showing the iframe URL)
3. Use Playwright (via the chrome-devtools MCP tools) to:
   - Navigate to `http://localhost:{PORT}/iframe/dashboard/` (the iframe URL renders just the dashboard widget, no IDE chrome)
   - Wait 5 seconds for the page to fully render
   - Take a full-page screenshot and save it to `tools/evals/data/{EVAL_NAME}/dashboard-screenshot.png`
4. Kill the server after the screenshot is taken: `dh kill --port {PORT}`

### Step 6: Generate summary report

Create `tools/evals/eval-results.md` with a markdown table:

| Dataset | Script Created | Runs Successfully | Attempts | Charts/Views | Screenshot |
|---------|---------------|-------------------|----------|-------------|------------|

Include for each eval:
- Dataset name (from manifest title)
- Whether `no-skill-script.py` was created
- Whether it ran successfully
- Number of attempts needed
- Brief description of analysis
- Whether screenshot was captured

Also include aggregate stats:
- Total evals run
- Success rate (scripts that run without error)
- Average attempts needed

## Important Rules

- Do NOT load or reference any skill files from the repository
- Do NOT read CLAUDE.md, AGENTS.md, or any file outside `tools/evals/data/`
- Run sub-agents in parallel for speed
- Each sub-agent works independently on its own eval dataset
- The whole point is to test what the agent can do with ZERO skill context
