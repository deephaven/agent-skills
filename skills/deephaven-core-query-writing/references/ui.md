# Deephaven UI Dashboard Development

## Overview

`deephaven.ui` is a Python framework for building interactive data applications using a **React-like declarative model**. Components are Python functions decorated with `@ui.component` that return UI elements. The framework uses:

- **Hooks** (`use_state`, `use_memo`, `use_effect`, etc.) for state management and side effects
- **Declarative rendering** - describe what the UI should look like, not how to update it
- **Automatic re-rendering** - when state changes, affected components re-render automatically
- **Real-time data integration** - seamlessly works with live Deephaven tables

If you know React, the patterns will be familiar. State changes trigger re-renders, hooks must be called at the top level of components, and the UI is a function of state.

## Quick Reference

- **Components Overview**: https://deephaven.io/core/ui/docs/components/overview.md
- **Full Documentation**: https://deephaven.io/sitemap/core/ui/main/docs/sitemap.xml
- **All component docs**: `https://deephaven.io/core/ui/docs/components/<component_name>.md`
- **All hook docs**: `https://deephaven.io/core/ui/docs/hooks/<hook_name>.md`

When building dashboards, read relevant `.md` files from the documentation as needed.

## Core Concepts

### Creating Components

Use the `@ui.component` decorator on Python functions:

```python
from deephaven import ui


@ui.component
def my_component():
    return ui.flex(
        ui.heading("Title"),
        ui.text("Content"),
        direction="column",
    )

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

```python
from deephaven import ui

# WRONG - stack inside panel, panel inside panel
ui.panel(ui.stack(ui.panel("chart1", title="A"), ui.panel("chart2", title="B")))

# CORRECT - stack directly in row/column, panels inside stack
ui.stack(ui.panel("chart1", title="A"), ui.panel("chart2", title="B"))
```

### Layout Best Practices

- **Prefer `row`, `column`, and `panel`** for dashboard layout structure
- **Panels are `ui.flex` by default** - no need to wrap content in `ui.flex` inside a panel, it is a flex `column` by default, but has the same flex properties available
- **Use `ui.flex`** inside components for grouping elements within a panel, it follows flexbox rules and has flex box properties
- **Separate panels for interacting components** - only group items in one panel if they don't need to interact with other panels via shared state
- **Use `ui.stack` for tabbed content** - place `ui.stack` directly in a `row`/`column`, with `ui.panel`s as its children

```python
from deephaven import ui


# GOOD - separate panels for components that share state
@ui.component
def layout():
    value, set_value = ui.use_state("")
    return ui.row(
        ui.panel(ui.text_field(value=value, on_change=set_value)),  # Input panel
        ui.panel(ui.text(f"You typed: {value}")),                   # Display panel
    )

result = layout()

# GOOD - ui.panel is a flex container, no need for extra ui.flex
ui.panel(
    ui.heading("Controls"),
    ui.button("Action 1", on_press=lambda: None),
    ui.button("Action 2", on_press=lambda: None),
    direction="column"  # Panel accepts flex props directly
)
```

### Sizing

Use `height` on rows and `width` on columns/stacks as proportional values:

```python
from deephaven import ui

ui.column(
    ui.row(ui.panel("Top"), height=25),      # 25% height
    ui.row(ui.panel("Bottom"), height=75),   # 75% height
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

## Component Categories

### Layout
`flex`, `grid`, `fragment`

### Dashboard Layout
`dashboard`, `row`, `column`, `stack`, `panel`

### Input
`text_field`, `text_area`, `number_field`, `checkbox`, `checkbox_group`, `radio_group`, `switch`, `slider`, `range_slider`, `picker`, `combo_box`, `date_picker`, `date_field`, `date_range_picker`, `time_field`, `color_picker`, `search_field`, `toggle_button`

### Action
`button`, `action_button`, `action_group`, `action_menu`, `button_group`, `logic_button`, `menu_trigger`, `dialog_trigger`

### Display
`text`, `heading`, `markdown`, `badge`, `meter`, `progress_bar`, `progress_circle`, `illustrated_message`, `inline_alert`, `toast`, `avatar`, `icon`, `image`, `table`, `tabs`, `list_view`, `accordion`, `calendar`, `range_calendar`, `breadcrumbs`, `tag_group`, `labeled_value`, `link`, `divider`, `view`

### Container
`dialog`, `contextual_help`, `disclosure`, `form`

## Button Types: When to Use Each

| Component | Use For |
|-----------|---------|
| `button` | Primary actions, navigation, important call-to-actions |
| `action_button` | Secondary/tertiary actions, table operations, icon-only buttons, quiet/de-emphasized actions |
| `toggle_button` | Binary on/off state, enabling/disabling features on a ui.table |

```python
from deephaven import ui


@ui.component
def button_examples():
    selected, set_selected = ui.use_state(False)

    return ui.flex(
        # button - important primary action
        ui.button("Submit", variant="accent", on_press=lambda: None),

        # action_button - secondary action, can be quiet or icon-only
        ui.action_button("Filter", on_press=lambda: None, is_quiet=True),
        ui.action_button(ui.icon("account"), aria_label="Edit", on_press=lambda: None),

        # toggle_button - tracks selected state
        ui.toggle_button(
            "Pin", is_selected=selected,
            on_change=set_selected, is_emphasized=True,
        ),
        direction="row",
        gap="size-100",
    )

result = button_examples()
```

*** Icon names are from the Deephaven icon set: https://deephaven.io/core/ui/docs/components/icon.md they are lowercase names like `account`, `filter`, `arrow_left` check literals from docs for full list. ***

## ui.flex Component

`ui.flex` is a flexbox container for arranging child elements. Use it inside panels for grouping elements.

**Docs**: https://deephaven.io/core/ui/docs/components/flex.md

### Direction & Wrap
```python
from deephaven import ui

ui.flex(
    ui.text("A"), ui.text("B"), ui.text("C"),
    direction="row",      # "row" (default), "column", "row-reverse", "column-reverse"
    # Allow wrapping: True, False, "wrap", "nowrap", "wrap-reverse"
    wrap=True,
)
```

### Alignment

| Property | Axis | Purpose |
|----------|------|---------|
| `justify_content` | Main axis | Distribute space along direction |
| `align_items` | Cross axis | Align items perpendicular to direction |
| `align_content` | Cross axis | Distribute wrapped lines |

```python
from deephaven import ui

ui.flex(
    ui.text("A"), ui.text("B"),
    direction="row",
    # Values: "start", "end", "center", "space-between",
    #         "space-around", "space-evenly"
    justify_content="space-between",
    # Values: "start", "end", "center", "stretch" (default),
    #         "baseline"
    align_items="center",
)
```

### Gap (Spacing)
```python
from deephaven import ui

ui.flex(
    ui.text("A"), ui.text("B"),
    gap="size-200",        # Space between all items (default: "size-100")
    column_gap="size-100", # Horizontal gap only
    row_gap="size-200",    # Vertical gap only
)
```

### Common Patterns

```python
from deephaven import ui

# Horizontal toolbar
ui.flex(
    ui.action_button("Save"),
    ui.action_button("Cancel"),
    gap="size-100",
    justify_content="end",
)

# Vertical form layout
ui.flex(
    ui.text_field(label="Name"),
    ui.text_field(label="Email"),
    ui.button("Submit"),
    direction="column",
    gap="size-200",
)

# Centered content
ui.flex(
    ui.text("Centered"),
    justify_content="center",
    align_items="center",
    height="100%",
)

# Space between with wrap
ui.flex(
    *[
        ui.view(
            f"Item {i}",
            background_color="gray-200",
            padding="size-100",
        )
        for i in range(6)
    ],
    wrap=True,
    gap="size-100",
    justify_content="space-between",
)
```

## Common Props

Most components share these properties for layout, sizing, and styling.

### Layout (Flex/Grid)
```python
from deephaven import ui

ui.text("Hello",
    flex=1,              # Flex grow factor
    flex_grow=1,         # How much to grow
    flex_shrink=0,       # How much to shrink
    align_self="center", # Cross-axis alignment
    order=1,             # Display order
)
```

### Sizing
```python
from deephaven import ui

ui.view(
    width="100%",        # Or "size-1000", 200, etc.
    height="auto",
    min_width=100,
    max_width="100%",
    min_height=50,
    max_height=500,
)
```

### Spacing
```python
from deephaven import ui

# Margin works on most components (flex, view, etc.)
ui.flex(
    margin="size-100",        # All sides
    margin_x="size-200",      # Left and right
    margin_y="size-100",      # Top and bottom
    margin_top="size-50",     # Individual sides
)

# Padding works on ui.view (not ui.flex)
ui.view(
    padding="size-100",       # All sides
    padding_start="size-200", # Logical (respects RTL)
)
```

### Colors

Colors auto-adjust with the user's light/dark theme.

**Semantic colors** (preferred — meaning-based, consistent across themes):
`positive`, `negative`, `notice`, `info`, `accent`

**palette** — `{name}-{index}` where index is `100` to `1400` (steps of 100):
`red`, `orange`, `yellow`, `chartreuse`, `celery`, `green`, `seafoam`, `cyan`, `blue`, `indigo`, `purple`, `fuchsia`, `magenta`

Examples: `"blue-400"`, `"red-900"`, `"seafoam-1100"`

**Gray scale**: `gray-50` through `gray-900`

**Raw values**: hex `"#FF0000"`, CSS names `"red"`, `"blue"`

```python
from deephaven import ui

ui.view(
    background_color="blue-600",
    border_color="accent",
)
```

### Dimension Values

Components auto-size based on layout. For manual sizing, use dimension values on `width`, `height`, `min_width`, `min_height`, `max_width`, `max_height`, `gap`, `margin`, `padding`, etc. Standard CSS units (`100px`, `50%`, `20em`) also work, but size tokens are preferred for consistency and theme-awareness.

Available `size-*` values:
`size-0`, `size-10`, `size-25`, `size-40`, `size-50`, `size-65`, `size-75`, `size-85`, `size-100`, `size-115`, `size-125`, `size-130`, `size-150`, `size-160`, `size-175`, `size-200`, `size-225`, `size-250`, `size-275`, `size-300`, `size-325`, `size-350`, `size-400`, `size-450`, `size-500`, `size-550`, `size-600`, `size-675`, `size-700`, `size-800`, `size-900`, `size-1000`, `size-1200`, `size-1250`, `size-1600`, `size-1700`, `size-2000`, `size-2400`, `size-3000`, `size-3400`, `size-3600`, `size-4600`, `size-5000`, `size-6000`

```python
from deephaven import ui

# size-100 ≈ 8px, size-200 ≈ 16px, size-300 ≈ 24px
ui.flex(
    ui.text_field(label="Name", width="size-3400"),
    ui.button("Go", width="size-1000"),
    gap="size-100",
)
```

### Borders
```python
from deephaven import ui

ui.view(
    border_width="thin",           # Or "thick", pixel value
    border_radius="medium",        # Or "small", "large"
    border_top_width="thick",
    border_top_start_radius="large",   # Logical (respects RTL)
)
```

### Positioning
```python
from deephaven import ui

ui.view(
    position="absolute",  # Or "relative", "fixed", "sticky"
    top=0, left=0,
    z_index=100,
)
```

### Visibility & Accessibility
```python
from deephaven import ui

ui.button("Click",
    id="my-button",
    is_hidden=False,
    is_disabled=False,
    UNSAFE_class_name="custom-class",
    UNSAFE_style={"customProperty": "value"},
)
```

## ui.table Component

`ui.table` wraps Deephaven tables for customized display and interactivity.

**Docs**: https://deephaven.io/core/ui/docs/components/table.md

### Basic Usage
```python
from deephaven import empty_table, ui

my_table = empty_table(100).update(["X = i", "Y = X * 2"])

# Simple - just pass the table
ui.table(my_table)

# With options
ui.table(
    my_table,
    show_search=True,
    show_quick_filters=True,
    reverse=True,               # Reverse row order for ticking tables is useful
)
```

### Column Management
```python
from deephaven import new_table, ui
from deephaven.column import double_col, int_col, string_col

my_table = new_table([
    string_col("Symbol", ["AAPL", "GOOG"]),
    string_col("Name", ["Apple", "Google"]),
    double_col("Price", [150.0, 140.0]),
    string_col("Notes", ["note1", "note2"]),
    int_col("InternalId", [1, 2]),
])

ui.table(
    my_table,
    front_columns=["Symbol", "Name"],     # Pin to front
    back_columns=["Notes"],               # Pin to back
    frozen_columns=["Symbol"],            # Freeze during scroll
    hidden_columns=["InternalId"],        # Hidden by default
    column_display_names={"Symbol": "Sym", "Price": "Current Price"},
)
```

### Formatting
```python
from deephaven import new_table, ui
from deephaven.column import double_col, string_col

my_table = new_table([
    string_col("Sym", ["AAPL", "GOOG", "MSFT"]),
    double_col("Price", [150.0, 40.0, 200.0]),
    string_col("Status", ["Active", "Inactive", "Active"]),
])

ui.table(
    my_table,
    format_=[
        # Number format
        ui.TableFormat(cols="Price", value="$#,##0.00"),
        # Conditional coloring
        ui.TableFormat(if_="Price > 100", background_color="positive"),
        ui.TableFormat(if_="Price < 50", background_color="negative"),
        # Column-specific color
        ui.TableFormat(cols="Status", color="accent"),
    ]
)
```

### Quick Filters
```python
from deephaven import new_table, ui
from deephaven.column import double_col, string_col

my_table = new_table([
    string_col("Sym", ["AAPL", "GOOG", "MSFT"]),
    double_col("Price", [150.0, 140.0, 200.0]),
    string_col("Exchange", ["NYSE", "NASDAQ", "NYSE"]),
])

ui.table(
    my_table,
    show_quick_filters=True,
    quick_filters={
        "Sym": "AAPL",
        "Price": ">=100",
        "Exchange": "NYSE",
    }
)
```

### Event Handling
```python
from deephaven import new_table, ui
from deephaven.column import double_col, string_col

my_table = new_table([
    string_col("Sym", ["AAPL", "GOOG"]),
    double_col("Price", [150.0, 140.0]),
])

@ui.component
def interactive_table(t):
    selected, set_selected = ui.use_state(None)

    return ui.table(
        t,
        on_row_press=lambda row: print(f"Clicked: {row['Sym']}"),
        on_row_double_press=lambda row: print(f"Double-clicked: {row}"),
        always_fetch_columns=["Sym", "Price"],  # Ensure these are in callbacks
    )

result = interactive_table(my_table)
```

### Context Menus
```python
from deephaven import new_table, ui
from deephaven.column import double_col, string_col

my_table = new_table([
    string_col("Sym", ["AAPL", "GOOG"]),
    double_col("Price", [150.0, 140.0]),
])

ui.table(
    my_table,
    context_menu=[
        {"title": "View Details", "action": lambda data: print(f"View: {data}")},
        {"title": "Delete", "action": lambda data: print(f"Delete: {data}")},
    ],
    context_header_menu=[
        {"title": "Sort Ascending", "action": lambda col: print(f"Sort: {col}")},
    ],
)
```

### Aggregations
```python
from deephaven import new_table, ui
from deephaven.column import double_col, int_col, string_col

my_table = new_table([
    string_col("Sym", ["AAPL", "AAPL", "GOOG"]),
    double_col("Price", [150.0, 152.0, 140.0]),
    int_col("Quantity", [100, 200, 150]),
    double_col("Total", [15000.0, 30400.0, 21000.0]),
])

ui.table(
    my_table,
    aggregations=[
        ui.TableAgg(agg="Sum", cols=["Quantity", "Total"]),
        ui.TableAgg(agg="Avg", cols=["Price"]),
        ui.TableAgg(agg="Count"),
    ],
    aggregations_position="top",  # Or "bottom"
)
```

## Tables in State

When storing Deephaven tables in state, use `use_liveness_scope` or `use_memo`:

```python
from deephaven import time_table, ui


# Option 1: use_memo (recommended for tables created in component)
@ui.component
def table_component():
    iteration, set_iteration = ui.use_state(0)
    table = ui.use_memo(lambda: time_table("PT1s"), [iteration])

    return ui.flex(
        ui.button("Reset", on_press=lambda: set_iteration(iteration + 1)),
        ui.table(table)
    )

# Option 2: use_liveness_scope (for external tables)
@ui.component
def table_component_v2():
    table, set_table = ui.use_state(lambda: time_table("PT1s"))
    handle_reset = ui.use_liveness_scope(
        lambda _: set_table(time_table("PT1s")), []
    )

    return ui.flex(
        ui.button("Reset", on_press=handle_reset),
        ui.table(table)
    )

result = table_component()
```

## Further Reading

Fetch these `.md` files as needed:
- Layout overview: `https://deephaven.io/core/ui/docs/creating-layouts/layout-overview.md`
- Creating dashboards: `https://deephaven.io/core/ui/docs/creating-layouts/creating-dashboards.md`
- State management: `https://deephaven.io/core/ui/docs/managing-state/share-state-between-components.md`
- Tutorial: `https://deephaven.io/core/ui/docs/tutorial.md`
- Any component: `https://deephaven.io/core/ui/docs/components/<name>.md`
- Any hook: `https://deephaven.io/core/ui/docs/hooks/<name>.md`
