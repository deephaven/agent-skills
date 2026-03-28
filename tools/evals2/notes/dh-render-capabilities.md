# dh render Capabilities for Evals

## Core Insight

`dh render` replaces ALL of Playwright's role in the eval pipeline. It renders the widget
headlessly and exposes the same information Playwright was extracting (component tree,
interactivity, table data) but without requiring a test script.

## Action Reference

| Action | What it tells us | Eval use |
|--------|-----------------|----------|
| `snapshot` | Accessibility tree — all rendered components | Verify dashboard rendered, count components |
| `click <target>` | Whether click handler works | Test button interactions |
| `fill <target> <value>` | Whether text input works | Test text field inputs |
| `select <target> <value>` | Whether picker selection works | Test filter pickers |
| `tables` | List of all exported tables with metadata | Verify data pipeline |
| `table <id>` | Actual row data from a table | Verify data correctness |
| `html` | Full rendered HTML | Debug rendering issues |
| `wait <ms>` | Pause for async operations | Let components settle |
| `diagnose` | JSON diagnostic report | Catch runtime errors |

## Key Flags

- `--vm` — Run in Firecracker VM (consistent environment)
- `--json` — JSON output (parseable by eval harness)
- `--timeout <ms>` — Render timeout (default 15000ms)
- `--rows <n>` — Max table rows to fetch (default 10)
- `--widget <name>` — Target specific widget if multiple exported

## Chaining Actions

Actions execute left-to-right. This is powerful for eval:

```bash
# Basic: does it render?
dh render --vm script.py snapshot

# With interaction: select a filter, then check state
dh render --vm script.py select "Region" "northeast" wait 1000 snapshot

# Data verification: list tables and fetch one
dh render --vm script.py tables
dh render --vm script.py table my_table --rows 20

# Full diagnostic
dh render --vm script.py diagnose
```

## What the Accessibility Tree Contains

The `snapshot` action prints an accessibility tree showing:
- Component types (buttons, pickers, text fields, panels, tabs)
- Component labels/text
- Component states (selected, checked, expanded)
- Hierarchical structure (parent-child relationships)
- @ref identifiers for targeting

This gives us everything Playwright was checking:
- ✅ Dashboard loaded (tree is non-empty)
- ✅ Components present (parse tree for component types)
- ✅ Tab structure (tabs visible in tree)
- ✅ Picker options (options listed in tree)
- ✅ Interactive state (selected/checked states)

## What `diagnose` Reports

JSON report including:
- Rendering errors
- Component mount failures
- Missing widget references
- Timeout information

This catches the runtime errors that `dh exec` misses (lazy evaluation of @ui.component functions).

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Script error |
| 2 | Connection/file error |
| 3 | Timeout |
| 130 | Interrupted |

Non-zero exit code from `dh render` = the dashboard has problems.

## VM Pool for Parallel Evals

When running many evals in parallel:
```bash
dh vm pool scale 5  # pre-warm 5 VMs
```

Each VM uses 4GB RAM + 4 vCPUs. Scale responsibly for the machine.
