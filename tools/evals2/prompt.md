# Eval Task

{SKILL_PREAMBLE}

DO NOT explore the repository. DO NOT read CLAUDE.md, AGENTS.md, or any files outside the eval and skill directories. DO NOT perform any web searches. You only have the instructions in this prompt.

You will complete ALL phases below in this single session. Do not stop early.

---

## Phase 1: Write Dashboard Script

{TASK_PROMPT}

Write a SINGLE Python script that uses Deephaven APIs:
- Load CSV data using the RELATIVE path exactly as given in the task (e.g. `evals/data/...`)
- Use `deephaven.read_csv()` or `pandas.read_csv()` + `deephaven.pandas.to_table()`
- Do NOT convert relative paths to absolute paths — the script runs inside a VM where absolute host paths like `/home/...` do not exist
- Perform the data analysis described in the task
- Create a `deephaven.ui` dashboard: `dashboard = ui.dashboard(layout())`
- Organize the dashboard with clear labels and logical layout

Example CSV loading (use the path from the task, not this exact path):
```python
from deephaven import read_csv
data = read_csv("evals/data/some-dataset/file.csv")
```

Write the script to: {OUTPUT_DIR}/script.py

---

## Phase 2: Verify Script

Run the script to verify it works:

```
dh exec --vm {OUTPUT_DIR}/script.py --timeout 120
```

and if that succeeds, check the dashboard snapshot works as expected:

```
dh render --vm {OUTPUT_DIR}/script.py --timeout 120 
```

- If either fails, read the error, fix the script, and retry
- You may retry up to a total of 8 times
- After each fix, write the updated script and re-run

Do NOT proceed to Phase 3 until the script runs successfully (exit code 0), or you have exhausted a total of 8 retry attempts.

---

## Phase 3: Write Reflection

Write a brief reflection to: {OUTPUT_DIR}/skill-recommendations.md

Content (max 40 lines):
- **Errors encountered:** List every distinct error you hit during script writing and verification. Include the exact error message, which attempt triggered it, and what code caused it.
- **Fixes applied:** For each error, what you changed and why. Include before/after code snippets where helpful.
- **Skill gaps:** What documentation or examples would have prevented these errors?
- **Metrics:** Number of dh exec attempts used
