# Eval Task

{SKILL_PREAMBLE}

DO NOT explore the repository. DO NOT read CLAUDE.md, AGENTS.md, or any files outside the eval and skill directories. DO NOT perform any web searches. You only have the instructions in this prompt.

You will complete ALL phases below in this single session. Do not stop early.

---

## Phase 1: Write Dashboard Script

{TASK_PROMPT}

Write a SINGLE Python script that uses Deephaven APIs:

- Load CSV data using the ABSOLUTE path exactly as given in the task
- Use `deephaven.read_csv()` to load the data into a Deephaven table
- Perform the data analysis described in the task
- Create a `deephaven.ui` dashboard: `dashboard = ui.dashboard(layout())`
- Organize the dashboard with clear labels and logical layout

Example CSV loading (use the path from the task, not this exact path):

```python
from deephaven import read_csv
# do not use a /workspace/tools/evals/data/... path, use the exact path given in the task
data = read_csv("/home/sandbox/agent-skills/tools/evals/data/some-dataset/file.csv")
```

Write the script to: {OUTPUT_DIR}/script.py

---

## Phase 2: Verify Script

Run the script to verify it works:

```
dh exec {OUTPUT_DIR}/script.py --timeout 120
```

and if that succeeds, check the dashboard snapshot works as expected:

```
dh render {OUTPUT_DIR}/script.py --widget dashboard --timeout 30000
```

- If either fails, read the error, fix the script, and retry
- You may retry up to a total of 8 times
- After each fix, write the updated script and re-run

Stop once the script runs successfully (exit code 0), or you have exhausted a total of 8 retry attempts.
