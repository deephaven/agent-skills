# Deephaven UI Dashboard Development

## Overview

`deephaven.ui` is a Python framework for data applications using a **React-like declarative model**. If you know React, the patterns will be familiar. State changes trigger re-renders, hooks must be called at the top level of components, and the UI is a function of state.

- **component docs**: `https://deephaven.io/core/ui/docs/components/<component_name>.md`
- **hook docs**: `https://deephaven.io/core/ui/docs/hooks/<hook_name>.md`

## Core Concepts

### Creating Components

Use the `@ui.component` decorator on Python functions:

```python
from deephaven import ui


@ui.component
def my_component():
    return ui.text("Content")


result = my_component()
```

### Hook Rules (Critical)

1. **Top-level only**: Never call hooks inside loops, conditions, or nested functions
2. **Component context only**: Hooks can only be called from `@ui.component` functions or custom hooks

```python
from deephaven import ui


# WRONG - hook in condition
@ui.component
def bad(show):
    if show:
        value, set_value = ui.use_state(0)  # Will break!


# CORRECT - hook at top level
@ui.component
def good(show):
    value, set_value = ui.use_state(0)  # Always at top
    if show:
        return ui.text(f"Value: {value}")
    return None
```

### Available Hooks

Data hooks re-render the component when their data changes. Use them to connect your UI to Deephaven tables and state.

| Hook | Purpose |
|------|---------|
| `use_state` | Component state that triggers re-renders |
| `use_memo` | Cache expensive computations |
| `use_callback` | Cache function definitions |
| `use_effect` | Side effects (data fetching, subscriptions) |
| `use_ref` | Mutable ref that doesn't trigger re-renders |
| `use_table_data` | Access full table contents |
| `use_column_data` | Access single column as list |
| `use_row_data` | Access single row as dict |
| `use_row_list` | Access single row as list |
| `use_cell_data` | Access specific cell |
| `use_table_listener` | Listen for table updates |
| `use_liveness_scope` | Manage table lifecycle in state |
| `use_render_queue` | Thread-safe state updates |

## Dashboard Structure

### Layout Hierarchy

```
ui.dashboard
└── ui.row or ui.column (root - exactly one)
    ├── ui.column or ui.row (alternating)
    │   └── ui.stack (tabbed container)
    │       └── ui.panel (content wrapper)
    └── ...
```

**Rules:**
- Dashboards must be at script root level, NOT inside `@ui.component`
- Dashboards require exactly one child (row or column)
- Columns go inside rows, rows go inside columns
- **`ui.panel` can ONLY be a child of `ui.row`, `ui.column`, or `ui.stack`** — never nest `row`, `column`, or `stack` inside a panel.
- Panels can never be children of other panels at any depth, they are only for wrapping content inside rows/columns/stacks
- Dashboard layout is controlled by width/height props on rows/columns, not panels
- **Panels are `ui.flex` by default** — no need to wrap content in `ui.flex` inside a panel, it is a flex `column` by default with the same flex properties (except width/height)
- **Use `ui.flex`** inside components for grouping elements within a panel
- **Separate panels for interacting components** — only group items in one panel if they don't need to interact with other panels via shared state
- **Use `ui.stack` for tabbed content** — place `ui.stack` directly in a `row`/`column`, with `ui.panel`s as its children
```python
from deephaven import ui

# WRONG - stack inside panel, panel inside panel
ui.panel(ui.stack(ui.panel("chart1", title="A"), ui.panel("chart2", title="B")))

# CORRECT - stack directly in row/column, panels inside stack
ui.stack(ui.panel("chart1", title="A"), ui.panel("chart2", title="B"))
```

### Sizing

Use `height` on rows and `width` on columns/stacks as proportional values:

```python
from deephaven import ui

ui.column(
    ui.row(ui.panel("Top"), height=25),  # 25% height
    ui.row(ui.panel("Bottom"), height=75),  # 75% height
)
```

## Stateful Dashboard Pattern

*** Always use the layout pattern for dashboards, as any dashboard may develop into a stateful dashboard. ***

To share state between panels, return `ui.row`/`ui.column` from a component, then wrap in dashboard:

```python
from deephaven import ui


@ui.component
def layout():
    message, set_message = ui.use_state("Hello world!")

    return ui.row(
        ui.panel(ui.text_field(value=message, on_change=set_message, width="100%")),
        ui.panel(message),
    )


dash_simple_state = ui.dashboard(layout())
```

## Components

`dashboard`, `row`, `column`, `stack`, `panel`, `flex`, `grid`, `fragment`, `text_field`, `text_area`, `number_field`, `checkbox`, `checkbox_group`, `radio_group`, `switch`, `slider`, `range_slider`, `picker`, `combo_box`, `date_picker`, `date_field`, `date_range_picker`, `time_field`, `search_field`, `toggle_button`, `button`, `action_button`, `action_group`, `action_menu`, `button_group`, `menu_trigger`, `dialog_trigger`, `text`, `heading`, `markdown`, `badge`, `meter`, `progress_bar`, `progress_circle`, `illustrated_message`, `inline_alert`, `toast`, `icon`, `image`, `table`, `tabs`, `list_view`, `accordion`, `tag_group`, `labeled_value`, `link`, `divider`, `view`, `dialog`, `contextual_help`, `disclosure`, `form`

## Selection Components: picker, combo_box, list_view

For letting users choose from a set of options. Use `picker` (dropdown) for most cases, `combo_box` for searchable/free-text, `list_view` for always-visible multi-select. All share the same `on_selection_change` callback pattern.

**Table-backed options (default):** Pass a Table directly — uses first column as key + label. **Duplicates cause an error**, so always use `select_distinct`. **Keys must be string type** — numeric columns silently produce 0 options; cast first with `.update_view(["Col = `` + Col"])`. For custom column mapping, use `ui.item_table_source(table, key_column="Id", label_column="Name")`. Use `selected_key=None` for a "show all" default — filter with `t if selected is None else t.where(...)`.

**Static options:** Only when the choices are fixed in code — e.g. a hardcoded enum, or when you need to inject extra entries like "All" alongside table values. Use `ui.item()` for each. For an "All" option, use `None` state with a filter guard:
`selected, set_selected = ui.use_state(None)` → `filtered = t if selected is None else t.where(...)` → `ui.picker(ui.item("All", key="All"), ui.item("A"), ..., selected_key=selected or "All", on_selection_change=lambda v: set_selected(None if v == "All" else v))`.

**Do NOT mix `ui.item()` and a Table in the same picker call** — items are silently dropped. To combine table values with extras like "All", use `ui.use_column_data(t, "Col")` to materialize the column as a list, then unpack as `ui.item` entries: `ui.picker(ui.item("All", key="All"), *[ui.item(v) for v in ui.use_column_data(t, "Sym")], ...)`.

```python
from deephaven import new_table, ui
from deephaven.column import double_col, string_col
from deephaven.plot import express as dx

source = new_table(
    [
        string_col(
            "Sym",
            ["AAPL", "AAPL", "GOOG", "GOOG", "MSFT", "MSFT"],
        ),
        double_col("Price", [150.0, 152.0, 140.0, 142.0, 200.0, 198.0]),
    ]
)


@ui.component
def filtered_dashboard(t):
    selected, set_selected = ui.use_state("AAPL")

    # Pass table directly to picker — select_distinct to avoid duplicate key errors
    sym_picker = ui.picker(
        t.select_distinct(["Sym"]),
        label="Symbol",
        selected_key=selected,
        on_selection_change=set_selected,
    )

    # Derive filtered table with use_memo (recalculates when selected changes)
    filtered = ui.use_memo(
        lambda: t.where(f"Sym = `{selected}`"),
        [selected],
    )

    chart = ui.use_memo(
        lambda: dx.line(filtered, x="Price", y="Price"),
        [filtered],
    )

    return ui.column(
        ui.row(ui.panel(sym_picker, title="Filters"), height=15),
        ui.row(
            ui.panel(chart, title="Price Chart"),
            ui.panel(ui.table(filtered), title="Data"),
            height=85,
        ),
    )


dashboard = ui.dashboard(filtered_dashboard(source))
```

**`use_column_data`** — for small tables, extracts a column as a Python list. Useful when you need values as data (e.g. generating buttons dynamically):

```python
from deephaven import new_table, ui
from deephaven.column import string_col

actions = new_table([string_col("Buy", ["AAPL", "TSLA", "GOOG"])])


@ui.component
def action_bar(t):
    items = ui.use_column_data(t, "Buy")
    return ui.flex(*[ui.action_button(a, on_press=lambda a=a: print(a)) for a in items])


result = action_bar(actions)
```

## Button Types

| Component | Use For |
|-----------|---------|
| `button` | Primary actions (`variant="accent"` for emphasis) |
| `action_button` | Secondary actions, icon-only buttons (`is_quiet=True`) |
| `toggle_button` | Binary on/off state |

Icon names from the Deephaven icon set: https://deephaven.io/core/ui/docs/components/icon.md — lowercase names like `account`, `filter`, `arrow_left`.

## ui.flex Component

`ui.flex` is a CSS flexbox container. Use it inside panels for grouping elements. Follows standard CSS flexbox semantics (`direction`, `wrap`, `justify_content`, `align_items`, `gap`).

**Docs**: https://deephaven.io/core/ui/docs/components/flex.md

```python
from deephaven import ui

ui.flex(
    ui.text("A"),
    ui.text("B"),
    direction="row",  # "row" (default), "column", "row-reverse", "column-reverse"
    wrap=True,
    gap="size-200",  # or column_gap / row_gap separately
    justify_content="space-between",  # start, end, center, space-around, space-evenly
    align_items="center",  # start, end, center, stretch (default), baseline
)
```

## Common Props

Most components accept standard layout/styling props. Use `size-*` tokens for theme-consistent sizing (commonly `size-100` through `size-300`; range: `size-0` to `size-6000`).

### Colors

Colors auto-adjust with the user's light/dark theme.

**Semantic colors** (preferred): `positive`, `negative`, `notice`, `info`, `accent`
**Palette** — `{name}-{index}` where index is `100`–`1400` (steps of 100):
`red`, `orange`, `yellow`, `chartreuse`, `celery`, `green`, `seafoam`, `cyan`, `blue`, `indigo`, `purple`, `fuchsia`, `magenta`
**Gray scale**: `gray-50` through `gray-900`
**Raw values**: hex `"#FF0000"`, CSS names `"red"`

```python
from deephaven import ui

ui.view(
    background_color="blue-600",
    border_color="accent",
)
```

## ui.table Component

`ui.table` wraps Deephaven tables for customized display and interactivity. You do not need to use `ui.table` to display tables in dashboards. Use `ui.table` only when you need its specific features, beyond what the query language provides. Formatting and interactivity requires `ui.table`. Passing in a Deephaven table is the only required prop, use others only when needed.

**Docs**: https://deephaven.io/core/ui/docs/components/table.md

```python
from deephaven import new_table, ui
from deephaven.column import double_col, int_col, string_col

t = new_table(
    [
        string_col("Sym", ["AAPL", "AAPL", "GOOG"]),
        string_col("Exchange", ["NYSE", "NYSE", "NASDAQ"]),
        double_col("Price", [150.0, 152.0, 140.0]),
        int_col("Qty", [100, 200, 150]),
        double_col("Total", [15000.0, 30400.0, 21000.0]),
    ]
)

ui.table(
    t,
    # Column management
    front_columns=["Sym"],  # Pin to front
    back_columns=["Exchange"],  # Pin to back
    frozen_columns=["Sym"],  # Freeze during scroll
    hidden_columns=["Total"],  # Hidden by default
    column_display_names={"Sym": "Symbol", "Qty": "Quantity"},
    reverse=True,  # Reverse row order (useful for ticking tables)
    # Formatting
    format_=[
        ui.TableFormat(cols="Price", value="$#,##0.00"),
        ui.TableFormat(if_="Price > 145", background_color="positive"),
        ui.TableFormat(if_="Price < 145", background_color="negative"),
    ],
    # Quick filters
    show_quick_filters=True,
    quick_filters={"Sym": "AAPL", "Price": ">=100"},
    # Aggregations
    aggregations=[
        ui.TableAgg(agg="Sum", cols=["Qty", "Total"]),
        ui.TableAgg(agg="Avg", cols=["Price"]),
        ui.TableAgg(agg="Count"),
    ],
    aggregations_position="top",  # Or "bottom"
    # Context menus
    context_menu=[
        {"title": "View", "action": lambda data: print(data)},
    ],
    context_header_menu=[
        {"title": "Sort", "action": lambda col: print(col)},
    ],
    # Event handling (use always_fetch_columns to ensure data in callbacks)
    on_row_press=lambda row: print(row),
    always_fetch_columns=["Sym", "Price"],
)
```

## Tables in State

When storing Deephaven tables in state, use `use_memo`:

```python
from deephaven import time_table, ui


#  use_memo (recommended for tables created in component)
@ui.component
def table_component():
    iteration, set_iteration = ui.use_state(0)
    table = ui.use_memo(lambda: time_table("PT1s"), [iteration])

    return ui.flex(
        ui.button("Reset", on_press=lambda: set_iteration(iteration + 1)),
        ui.table(table),
    )


result = table_component()
```
