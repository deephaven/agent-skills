# Deephaven Express (dx) Plotting

## Critical Import Rule

**ALWAYS use Deephaven Express. NEVER import plotly express directly.**

```python
# pseudo
# CORRECT
from deephaven.plot import express as dx

# WRONG - Never do this
# import plotly.express as px  # DO NOT USE
```

Deephaven Express is a drop-in replacement for Plotly Express that works with real-time Deephaven tables.

It must be imported before being used.

## Quick Reference

- **Full Documentation**: https://deephaven.io/core/plotly/docs.md
- **Docs Sitemap**: https://deephaven.io/sitemap/core/plotly/main/docs/sitemap.xml
- **Plot type docs**: `https://deephaven.io/core/plotly/docs/<plot_type>.md`
- **Example data**: `dx.data.stocks()`, `dx.data.iris()`, `dx.data.tips()`, `dx.data.gapminder()`

## Basic Pattern

```python
from deephaven.plot import express as dx

my_table = dx.data.stocks()
plot = dx.line(table=my_table, x="Timestamp", y="Price", by="Sym")
```

## Available Plot Types

### Basic Charts
| Function | Use Case | Docs |
|----------|----------|------|
| `dx.line` | Time series, trends | https://deephaven.io/core/plotly/docs/line.md |
| `dx.scatter` | Correlations, clusters | https://deephaven.io/core/plotly/docs/scatter.md |
| `dx.bar` | Category comparisons | https://deephaven.io/core/plotly/docs/bar.md |
| `dx.histogram` | Distributions | https://deephaven.io/core/plotly/docs/histogram.md |
| `dx.area` | Cumulative totals | https://deephaven.io/core/plotly/docs/area.md |
| `dx.pie` | Proportions | https://deephaven.io/core/plotly/docs/pie.md |

### Financial Charts
| Function | Use Case | Docs |
|----------|----------|------|
| `dx.candlestick` | OHLC with bodies | https://deephaven.io/core/plotly/docs/candlestick.md |
| `dx.ohlc` | OHLC with ticks | https://deephaven.io/core/plotly/docs/ohlc.md |

### Statistical Charts
| Function | Use Case | Docs |
|----------|----------|------|
| `dx.box` | Distribution summary | https://deephaven.io/core/plotly/docs/box.md |
| `dx.violin` | Full distribution shape | https://deephaven.io/core/plotly/docs/violin.md |
| `dx.density_heatmap` | Joint distributions | https://deephaven.io/core/plotly/docs/density_heatmap.md |
| `dx.strip` | Individual points | https://deephaven.io/core/plotly/docs/strip.md |

### Hierarchical Charts
| Function | Use Case | Docs |
|----------|----------|------|
| `dx.treemap` | Nested rectangles | https://deephaven.io/core/plotly/docs/treemap.md |
| `dx.sunburst` | Radial hierarchy | https://deephaven.io/core/plotly/docs/sunburst.md |
| `dx.icicle` | Hierarchical bars | https://deephaven.io/core/plotly/docs/icicle.md |

### 3D and Geo Charts
| Function | Docs |
|----------|------|
| `dx.scatter_3d` | https://deephaven.io/core/plotly/docs/scatter-3d.md |
| `dx.line_3d` | https://deephaven.io/core/plotly/docs/line-3d.md |
| `dx.scatter_geo` | https://deephaven.io/core/plotly/docs/scatter-geo.md |
| `dx.line_geo` | https://deephaven.io/core/plotly/docs/line-geo.md |

## Common Parameters

### Data Grouping
```python
from deephaven.plot import express as dx

table = dx.data.stocks()

# Group by column - creates separate traces per unique value
dx.line(table, x="Timestamp", y="Price", by="Sym")

# Multiple grouping columns
table2 = dx.data.iris()
dx.scatter(table2, x="SepalLength", y="SepalWidth", by=["Species"])
```

### Visual Mapping
```python
from deephaven.plot import express as dx

table = dx.data.iris()

dx.scatter(
    table,
    x="SepalLength",
    y="SepalWidth",
    color="Species",      # Color by column
    symbol="Species",     # Different markers
    size="PetalLength",   # Bubble size
)
```

### Axis Configuration
```python
from deephaven import empty_table
from deephaven.plot import express as dx

table = empty_table(100).update([
    "Timestamp = parseInstant(`2024-01-01T09:30:00 UTC`) + i * 'PT1m'",
    "Price = 150.0 + Math.sin(i * 0.1) * 10",
    "Volume = (int)(1000 + i * 50)",
])

dx.line(
    table,
    x="Timestamp", y=["Price", "Volume"],
    yaxis_sequence=[1, 2],  # Different Y axes
)
```

### Titles and Labels
```python
from deephaven.plot import express as dx

table = dx.data.stocks()

dx.line(
    table,
    x="Timestamp", y="Price",
    title="Stock Prices",
    xaxis_titles="Time",
    yaxis_titles="Price ($)",
)
```

## Financial Charts (OHLC/Candlestick)

```python
import datetime

from deephaven import new_table
from deephaven.column import datetime_col, double_col
from deephaven.plot import express as dx

table = new_table([
    datetime_col("Timestamp", [
        datetime.datetime(
            2024, 6, 1, 10, i,
            tzinfo=datetime.timezone.utc,
        ) for i in range(5)
    ]),
    double_col("Open", [150.0, 152.0, 148.0, 155.0, 153.0]),
    double_col("High", [155.0, 156.0, 152.0, 158.0, 157.0]),
    double_col("Low", [148.0, 150.0, 146.0, 153.0, 151.0]),
    double_col("Close", [152.0, 148.0, 151.0, 153.0, 156.0]),
])

dx.candlestick(
    table,
    x="Timestamp",
    open="Open",
    high="High",
    low="Low",
    close="Close",
    increasing_color_sequence=["green"],
    decreasing_color_sequence=["red"],
)

dx.ohlc(
    table,
    x="Timestamp",
    open="Open",
    high="High",
    low="Low",
    close="Close",
)
```

## Advanced Features

### Subplots - Multiple Plots in Grid
```python
from deephaven import empty_table
from deephaven.plot import express as dx

# Docs: https://deephaven.io/core/plotly/docs/sub-plots.md
table = empty_table(100).update([
    "X = i",
    "Y = Math.sin(i * 0.1) * 10",
    "Category = i % 3 == 0 ? `A` : i % 3 == 1 ? `B` : `C`",
    "Value = randomDouble(0, 100)",
])

plot1 = dx.line(table, x="X", y="Y")
plot2 = dx.scatter(table, x="X", y="Y")
plot3 = dx.bar(table, x="Category", y="Value")
plot4 = dx.histogram(table, x="Value")

combined = dx.make_subplots(
    plot1, plot2, plot3, plot4,
    rows=2, cols=2,
    shared_xaxes="columns",
)
```

### Layer Plots - Stack Different Plot Types
```python
import datetime

from deephaven import new_table
from deephaven.column import datetime_col, double_col
from deephaven.plot import express as dx

# Docs: https://deephaven.io/core/plotly/docs/layer-plots.md
table = new_table([
    datetime_col("Timestamp", [
        datetime.datetime(
            2024, 6, 1, 10, i,
            tzinfo=datetime.timezone.utc,
        ) for i in range(5)
    ]),
    double_col("Open", [150.0, 152.0, 148.0, 155.0, 153.0]),
    double_col("High", [155.0, 156.0, 152.0, 158.0, 157.0]),
    double_col("Low", [148.0, 150.0, 146.0, 153.0, 151.0]),
    double_col("Close", [152.0, 148.0, 151.0, 153.0, 156.0]),
    double_col("MovingAvg", [151.0, 150.5, 150.0, 151.5, 152.0]),
])

layered = dx.layer(
    dx.candlestick(
        table, x="Timestamp", open="Open",
        high="High", low="Low", close="Close",
    ),
    dx.line(table, x="Timestamp", y="MovingAvg"),
)
```

### Interactive Filtering

**UI-driven filtering** (with deephaven.ui):
```python
# Docs: https://deephaven.io/core/ui/docs/add-interactivity/plot-with-deephaven-ui.md
from deephaven import ui
from deephaven.plot import express as dx


@ui.component
def filtered_plot(table, initial_sym):
    sym, set_sym = ui.use_state(initial_sym)

    # Memoize filtered table
    filtered = ui.use_memo(
        lambda: table.where(f"Sym = `{sym.upper()}`"), [table, sym]
    )

    # Memoize plot creation
    plot = ui.use_memo(
        lambda: dx.line(filtered, x="Timestamp", y="Price"), [filtered]
    )

    return ui.flex(
        ui.text_field(value=sym, on_change=set_sym, label="Symbol"),
        plot,
        direction="column"
    )

stocks = dx.data.stocks()
result = filtered_plot(stocks, "AAPL")
```

**Partitioned table approach** (more efficient for repeated filtering):
```python
from deephaven import ui
from deephaven.plot import express as dx


@ui.component
def partitioned_plot(table, initial_sym):
    sym, set_sym = ui.use_state(initial_sym)

    # Partition once, then select constituents
    partitioned = ui.use_memo(lambda: table.partition_by(["Sym"]), [table])
    constituent = ui.use_memo(
        lambda: partitioned.get_constituent(sym.upper()), [partitioned, sym]
    )

    plot = ui.use_memo(
        lambda: dx.line(constituent, x="Timestamp", y="Price"), [constituent]
    )

    return [ui.text_field(value=sym, on_change=set_sym), plot]

stocks = dx.data.stocks()
result = partitioned_plot(stocks, "AAPL")
```

**Dynamic plot type selection**:
```python
from deephaven import ui
from deephaven.plot import express as dx


@ui.component
def dynamic_plot(table):
    plot_type, set_plot_type = ui.use_state("Line")

    def create_plot(t, pt):
        match pt:
            case "Line":
                return dx.line(t, x="Timestamp", y="Price")
            case "Scatter":
                return dx.scatter(t, x="Timestamp", y="Price")
            case "Area":
                return dx.area(t, x="Timestamp", y="Price")

    plot = ui.use_memo(lambda: create_plot(table, plot_type), [table, plot_type])

    return ui.flex(
        ui.picker(
            "Line", "Scatter", "Area",
            selected_key=plot_type,
            on_change=set_plot_type,
        ),
        plot,
        direction="column"
    )

stocks = dx.data.stocks().where("Sym = `AAPL`")
result = dynamic_plot(stocks)
```

**Note**: Deephaven Express handles liveness internally - no explicit scope management needed for plots.

### Multiple Axes
```python
from deephaven import empty_table
from deephaven.plot import express as dx

# Docs: https://deephaven.io/core/plotly/docs/multiple-axes.md
table = empty_table(100).update([
    "Timestamp = parseInstant(`2024-01-01T09:30:00 UTC`) + i * 'PT1m'",
    "Price = 150.0 + Math.sin(i * 0.1) * 10",
    "Volume = (int)(1000 + i * 50)",
])

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

table = empty_table(50).update([
    "X = i",
    "Y = Math.sin(i * 0.1) * 10",
])

def customize(figure):
    # Modify traces
    figure.update_traces(marker_line_width=2, marker_line_color="black")

    # Add annotations
    figure.add_vline(x=20, line_dash="dash", line_color="red")
    figure.add_hline(y=100, line_dash="dot", line_color="blue")

    # Customize layout
    figure.update_layout(
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        showlegend=True,
    )
    return figure

plot = dx.scatter(table, x="X", y="Y", unsafe_update_figure=customize)
```

### Common unsafe_update_figure Patterns

**Add border to bars:**
```python
from deephaven import new_table
from deephaven.column import double_col, string_col
from deephaven.plot import express as dx

table = new_table([
    string_col("Category", ["A", "B", "C"]),
    double_col("Value", [10.0, 20.0, 30.0]),
])

def update(fig):
    fig.update_traces(marker_line_width=3, marker_line_color="gray")

dx.bar(table, x="Category", y="Value", unsafe_update_figure=update)
```

**Position legend:**
```python
from deephaven import empty_table
from deephaven.plot import express as dx

table = empty_table(30).update([
    "X = i",
    "Y = Math.sin(i * 0.1) * 10",
    "Category = i % 3 == 0 ? `A` : i % 3 == 1 ? `B` : `C`",
])

def update(fig):
    fig.update_layout(legend=dict(
        orientation="h",
        yanchor="bottom", y=-0.2,
        xanchor="center", x=0.5
    ))

dx.line(table, x="X", y="Y", by="Category", unsafe_update_figure=update)
```

**Hide legend:**
```python
def update(fig):
    fig.update_layout(showlegend=False)
```

### unsafe_update_figure Warnings

- **DO NOT remove traces** - dx maps table columns to trace indices
- **DO NOT reorder traces** - will break the figure
- **Add new traces at the end only**
- Some modifications can break figures entirely

## Complete Example

```python
import deephaven.plot.express as dx
from deephaven import time_table

# Create real-time data
source = time_table("PT1s").update([
    "X = i",
    "Y1 = Math.sin(i * 0.1) * 10",
    "Y2 = Math.cos(i * 0.1) * 10",
    "Category = i % 3 == 0 ? `A` : i % 3 == 1 ? `B` : `C`"
])

# Line plot with multiple series
line_plot = dx.line(
    source,
    x="X",
    y=["Y1", "Y2"],
    title="Sine and Cosine Waves",
)

# Scatter with grouping
scatter_plot = dx.scatter(
    source,
    x="Y1",
    y="Y2",
    by="Category",
    title="Phase Plot by Category",
)

# Customize with unsafe_update_figure
def add_grid(fig):
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor="lightgray")
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="lightgray")
    return fig

styled_plot = dx.scatter(
    source, x="Y1", y="Y2",
    unsafe_update_figure=add_grid
)
```

## Further Reading

Fetch these `.md` files as needed:
- Plot by grouping: https://deephaven.io/core/plotly/docs/plot-by.md
- Titles and legends: https://deephaven.io/core/plotly/docs/titles-legends.md
- Example data: https://deephaven.io/core/plotly/docs/example-data.md
