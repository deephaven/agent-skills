# Deephaven Express (dx) Plotting

**CRITICAL: ALWAYS use Deephaven Express. NEVER import plotly express directly.**

```python
# pseudo
# CORRECT
from deephaven.plot import express as dx

# WRONG - Never do this
# import plotly.express as px  # DO NOT USE
```

Deephaven Express mirrors the Plotly Express API for tables but is **not a full drop-in** — several Plotly Express kwargs are unsupported and will raise `TypeError: unexpected keyword argument`. Known unsupported: `trendline`, `marginal_x`, `marginal_y`, `facet_col`, `facet_row`, `animation_frame`. For trendlines, compute the regression as a column with `update`/`update_by` and overlay a second `dx.line` via `dx.layer`. For faceting, build one plot per group and arrange them with `dx.make_subplots` (see "Financial Charts, Subplots, and Layers" below). It must be imported before being used.

**Example ticking data**: `dx.data.stocks()`, `dx.data.iris()`, `dx.data.tips()`, `dx.data.gapminder()` and more.

## Basic Pattern

```python
from deephaven.plot import express as dx

my_table = dx.data.stocks()
plot = dx.line(table=my_table, x="Timestamp", y="Price", by="Sym")
```

## Available Plot Types

| Function | Use Case | Function | Use Case |
|---|---|---|---|
| `dx.line` | Time series, trends | `dx.scatter` | Correlations, clusters |
| `dx.bar` | Category comparisons | `dx.histogram` | Distributions (numeric only) |
| `dx.area` | Cumulative totals | `dx.pie` | Proportions |
| `dx.candlestick` | OHLC with bodies | `dx.ohlc` | OHLC with ticks |
| `dx.box` | Distribution summary | `dx.violin` | Full distribution shape |
| `dx.density_heatmap` | Joint distributions | `dx.density_map` | Geographic density |
| `dx.strip` | Individual points | `dx.indicator` | KPI / gauge |
| `dx.funnel` | Funnel stages | `dx.funnel_area` | Proportional funnel |
| `dx.timeline` | Gantt / time ranges | `dx.treemap` | Nested rectangles |
| `dx.sunburst` | Radial hierarchy | `dx.icicle` | Hierarchical bars |
| `dx.scatter_3d` | 3D scatter | `dx.line_3d` | 3D lines |
| `dx.scatter_geo` | Geographic scatter | `dx.line_geo` | Geographic lines |
| `dx.scatter_map` | Map scatter | `dx.line_map` | Map lines |
| `dx.scatter_polar` | Polar scatter | `dx.line_polar` | Polar lines |
| `dx.scatter_ternary` | Ternary scatter | `dx.line_ternary` | Ternary lines |

Docs for each: `https://deephaven.io/core/plotly/docs/<function_name>.md`

**`dx.bar` plots values as-is** — pre-aggregate with `agg_by`/`count_by` before plotting. `dx.histogram` only works on numeric columns; for categorical counts, pre-aggregate then use `dx.bar`. **String x-axis columns render in insertion order**, not sorted — sort the table first or parse date strings to `Instant` for a proper temporal axis (see `references/time-operations.md`).

**`dx.*` time axes require `Instant` (or `ZonedDateTime`), not `LocalDate`.** A `LocalDate` x-column renders as a numeric axis and the line silently fails to draw. Parse date strings with `parseInstant` (`parseInstant(date + \`T00:00:00 UTC\`)`); reserve `LocalDate` for date arithmetic and `where` filters, not plot axes.

```python
from deephaven import new_table
from deephaven.column import int_col, string_col
from deephaven.plot import express as dx

t = new_table(
    [
        string_col("Category", ["A", "A", "B", "B", "C", "C"]),
        string_col("Group", ["X", "Y", "X", "Y", "X", "Y"]),
        int_col("Count", [10, 20, 30, 15, 25, 35]),
    ]
)

# Basic bar chart from pre-aggregated data
dx.bar(t, x="Category", y="Count")

# Grouped by column — barmode: "group" (side-by-side), "stack", "overlay"
dx.bar(t, x="Category", y="Count", by="Group", barmode="group")
```

## Common Parameters

### Data Grouping

`by=`, `color=`, `symbol=`, `size=`, `line_dash=` all partition by column values into separate traces. `by=` is preferred for ticking data (uses server-side `partition_by`).

```python
from deephaven.plot import express as dx

table = dx.data.stocks()

# Group by column - creates separate traces per unique value
dx.line(table, x="Timestamp", y="Price", by="Sym")

# Multiple grouping columns
table2 = dx.data.iris()
dx.scatter(table2, x="SepalLength", y="SepalWidth", by=["Species", "PetalLength"])
```

### Visual Mapping

```python
from deephaven.plot import express as dx

table = dx.data.iris()

dx.scatter(
    table,
    x="SepalLength",
    y="SepalWidth",
    color="Species",  # Color by column
    symbol="Species",  # Different markers
    size="PetalLength",  # Bubble size
)
```

### Title and Axis Configuration

```python
from deephaven import empty_table
from deephaven.plot import express as dx

table = empty_table(100).update(
    [
        "Timestamp = parseInstant(`2024-01-01T09:30:00 UTC`) + i * 'PT1m'",
        "Price = 150.0 + Math.sin(i * 0.1) * 10",
        "Volume = (int)(1000 + i * 50)",
    ]
)

dx.line(
    table,
    x="Timestamp",
    y=["Price", "Volume"],
    title="Stock Prices",  # Can be added on any plot type
    yaxis_sequence=[1, 2],  # Different Y axes
)
```



## Financial Charts, Subplots, and Layers

```python
import datetime

from deephaven import empty_table, new_table
from deephaven.column import datetime_col, double_col
from deephaven.plot import express as dx

# OHLC data for financial charts and layering
ohlc = new_table(
    [
        datetime_col(
            "Timestamp",
            [
                datetime.datetime(2024, 6, 1, 10, i, tzinfo=datetime.timezone.utc)
                for i in range(5)
            ],
        ),
        double_col("Open", [150.0, 152.0, 148.0, 155.0, 153.0]),
        double_col("High", [155.0, 156.0, 152.0, 158.0, 157.0]),
        double_col("Low", [148.0, 150.0, 146.0, 153.0, 151.0]),
        double_col("Close", [152.0, 148.0, 151.0, 153.0, 156.0]),
        double_col("MovingAvg", [151.0, 150.5, 150.0, 151.5, 152.0]),
    ]
)

# Candlestick
dx.candlestick(
    ohlc,
    x="Timestamp",
    open="Open",
    high="High",
    low="Low",
    close="Close",
    increasing_color_sequence=["green"],
    decreasing_color_sequence=["red"],
)

# dx.layer — stack different plot types on top of one chart
layered = dx.layer(
    dx.candlestick(
        ohlc, x="Timestamp", open="Open", high="High", low="Low", close="Close"
    ),
    dx.line(ohlc, x="Timestamp", y="MovingAvg"),
)

# dx.make_subplots — arrange multiple plots in a grid
t = empty_table(100).update(
    ["X = i", "Y = Math.sin(i * 0.1) * 10", "Value = randomDouble(0, 100)"]
)
combined = dx.make_subplots(
    dx.line(t, x="X", y="Y"),
    dx.scatter(t, x="X", y="Y"),
    dx.histogram(t, x="Value"),
    rows=2,
    cols=2,
)
```

### Interactive Filtering

Patterns for plots with `deephaven.ui`. dx handles liveness internally — no explicit scope management needed.

```python
from deephaven import ui
from deephaven.plot import express as dx

stocks = dx.data.stocks()


# Pattern 1: use_memo + where (simple)
@ui.component
def filtered_plot(t):
    sym, set_sym = ui.use_state("AAPL")
    filtered = ui.use_memo(lambda: t.where(f"Sym = `{sym}`"), [sym])
    plot = ui.use_memo(lambda: dx.line(filtered, x="Timestamp", y="Price"), [filtered])
    return [ui.text_field(value=sym, on_change=set_sym, label="Symbol"), plot]


# Pattern 2: partition_by (more efficient for repeated filtering, uses more memory)
@ui.component
def partitioned_plot(t):
    sym, set_sym = ui.use_state("AAPL")
    partitioned = ui.use_memo(lambda: t.partition_by(["Sym"]), [])
    constituent = ui.use_memo(lambda: partitioned.get_constituent(sym), [sym])
    plot = ui.use_memo(
        lambda: dx.line(constituent, x="Timestamp", y="Price"),
        [constituent],
    )
    return [ui.text_field(value=sym, on_change=set_sym, label="Symbol"), plot]


# Pattern 3: dynamic plot type via dict lookup
@ui.component
def dynamic_plot(t):
    plot_type, set_plot_type = ui.use_state("Line")
    plot_fn = {"Line": dx.line, "Scatter": dx.scatter, "Area": dx.area}
    fn = plot_fn[plot_type]
    plot = ui.use_memo(
        lambda: fn(t, x="Timestamp", y="Price"),
        [plot_type],
    )
    return [
        ui.picker(
            "Line",
            "Scatter",
            "Area",
            selected_key=plot_type,
            on_change=set_plot_type,
        ),
        plot,
    ]


result = filtered_plot(stocks)
```

### Multiple Axes

```python
from deephaven import empty_table
from deephaven.plot import express as dx

# Docs: https://deephaven.io/core/plotly/docs/multiple-axes.md
table = empty_table(100).update(
    [
        "Timestamp = parseInstant(`2024-01-01T09:30:00 UTC`) + i * 'PT1m'",
        "Price = 150.0 + Math.sin(i * 0.1) * 10",
        "Volume = (int)(1000 + i * 50)",
    ]
)

dx.line(
    table,
    x="Timestamp",
    y=["Price", "Volume"],
    yaxis_sequence=[1, 2],  # Separate Y axes
)
```

## unsafe_update_figure - Advanced Customization

Use `unsafe_update_figure` to access the underlying Plotly Figure for advanced customization.

**Docs**: https://deephaven.io/core/plotly/docs/unsafe-update-figure.md

```python
from deephaven import empty_table
from deephaven.plot import express as dx

table = empty_table(50).update(
    [
        "X = i",
        "Y = Math.sin(i * 0.1) * 10",
        "Category = i % 3 == 0 ? `A` : i % 3 == 1 ? `B` : `C`",
    ]
)


def customize(fig):
    fig.update_traces(marker_line_width=2, marker_line_color="black")
    fig.add_vline(x=20, line_dash="dash", line_color="red")
    fig.add_hline(y=5, line_dash="dot", line_color="blue")
    fig.update_layout(
        showlegend=True,  # False to hide
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.2,
            xanchor="center",
            x=0.5,
        ),
    )


dx.line(table, x="X", y="Y", by="Category", unsafe_update_figure=customize)
```

### unsafe_update_figure Warnings

- **DO NOT remove traces** - dx maps table columns to trace indices
- **DO NOT reorder traces** - will break the figure
- **Add new traces at the end only**
- Some modifications can break figures entirely
