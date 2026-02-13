# Deephaven Aggregations Reference

## Dedicated Aggregations

Single-operation aggregations optimized for common use cases.

```python
from deephaven import new_table
from deephaven.column import double_col, int_col, string_col

t = new_table([
    string_col("Sym", ["AAPL", "AAPL", "GOOG", "GOOG", "MSFT", "MSFT"]),
    double_col("Price", [150.0, 152.0, 140.0, 142.0, 200.0, 198.0]),
    int_col("Qty", [100, 200, 150, 250, 300, 100]),
    double_col("Weight", [0.5, 0.3, 0.7, 0.2, 0.4, 0.6]),
    double_col("Value", [1500.0, 3040.0, 2100.0, 3550.0, 6000.0, 1980.0]),
])

# Group by key columns, aggregate all numeric columns
t.sum_by("Sym")              # Sum
t.avg_by("Sym")              # Average
t.min_by("Sym")              # Minimum
t.max_by("Sym")              # Maximum
t.median_by("Sym")           # Median
t.std_by("Sym")              # Standard deviation
t.var_by("Sym")              # Variance
t.abs_sum_by("Sym")          # Sum of absolute values

# Counting
t.count_by("Count", "Sym")   # Count rows per group

# Row selection
t.first_by("Sym")            # First row per group
t.last_by("Sym")             # Last row per group
t.head_by(5, "Sym")          # First 5 rows per group
t.tail_by(5, "Sym")          # Last 5 rows per group

# Weighted operations
t.weighted_avg_by("Weight", "Sym")    # Weighted average
t.weighted_sum_by("Weight", "Sym")    # Weighted sum

# No grouping key = aggregate entire table (only works if all columns are numeric)
t.sum_by("Sym")
```

**Warning:** Without explicit column selection, dedicated aggregations attempt to aggregate ALL numeric columns. This fails if the table contains non-aggregable types (Timestamp, String, etc.). Use `select` first or `agg_by` with explicit `cols` for safety:
```python
from deephaven import agg, new_table
from deephaven.column import double_col, string_col

t = new_table([
    string_col("Sym", ["AAPL", "AAPL", "GOOG"]),
    double_col("Price", [150.0, 152.0, 140.0]),
])

# Safe - select columns first, then aggregate
t.view(["Sym", "Total = Price"]).sum_by("Sym")
# Or use agg_by with explicit cols
t.agg_by([agg.sum_(cols=["Total = Price"])], by=["Sym"])
```

**Specify columns to aggregate with select + dedicated agg:**
```python
from deephaven import new_table
from deephaven.column import double_col, int_col, string_col

t = new_table([
    string_col("Sym", ["AAPL", "AAPL", "GOOG"]),
    int_col("Qty", [100, 200, 150]),
    double_col("Value", [1500.0, 3040.0, 2100.0]),
])

t.select(["Sym", "TotalQty = Qty", "TotalValue = Value"]).sum_by("Sym")
```

## Combined Aggregations (agg_by)

Multiple aggregations in a single pass - more efficient than separate calls.

```python
import datetime

from deephaven import agg, new_table
from deephaven.column import datetime_col, double_col, int_col, string_col

t = new_table([
    string_col("Sym", ["AAPL", "AAPL", "GOOG", "GOOG"]),
    double_col("Price", [150.0, 152.0, 140.0, 142.0]),
    int_col("Qty", [100, 200, 150, 250]),
    datetime_col("Timestamp", [
        datetime.datetime(2024, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
        datetime.datetime(2024, 6, 1, 11, 0, tzinfo=datetime.timezone.utc),
        datetime.datetime(2024, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
        datetime.datetime(2024, 6, 1, 11, 0, tzinfo=datetime.timezone.utc),
    ]),
])

result = t.agg_by([
    agg.avg(cols=["AvgPrice = Price"]),
    agg.sum_(cols=["TotalQty = Qty"]),
    agg.count_(col="Count"),
    agg.first(cols=["FirstTime = Timestamp"]),
    agg.last(cols=["LastTime = Timestamp"]),
    agg.max_(cols=["MaxPrice = Price"]),
    agg.min_(cols=["MinPrice = Price"]),
], by=["Sym"])
```

## Available Aggregators

### Statistical
```python
from deephaven import agg, new_table
from deephaven.column import double_col, string_col

t = new_table([
    string_col("Group", ["A", "A", "B", "B"]),
    double_col("SourceCol", [10.0, 20.0, 30.0, 40.0]),
    double_col("Col", [1.0, -2.0, 3.0, -4.0]),
])

t.agg_by([
    agg.avg(cols=["AvgCol = SourceCol"]),      # Average
    agg.sum_(cols=["SumCol = SourceCol"]),     # Sum (note underscore)
    agg.abs_sum(cols=["AbsSumCol = Col"]),     # Sum of absolute values
    agg.var(cols=["VarCol = SourceCol"]),      # Variance
    agg.std(cols=["StdCol = SourceCol"]),      # Standard deviation
    agg.median(cols=["MedCol = SourceCol"]),   # Median
], by=["Group"])
```

### Extremes
```python
from deephaven import agg, new_table
from deephaven.column import double_col, int_col, string_col

t = new_table([
    string_col("Group", ["A", "A", "B", "B"]),
    double_col("SourceCol", [10.0, 20.0, 30.0, 40.0]),
    int_col("SortCol", [2, 1, 4, 3]),
    double_col("Col", [100.0, 200.0, 300.0, 400.0]),
])

t.agg_by([
    agg.min_(cols=["MinCol = SourceCol"]),     # Minimum (note underscore)
    agg.max_(cols=["MaxCol = SourceCol"]),     # Maximum (note underscore)
    agg.sorted_first(  # First by sort order
        order_by="SortCol", cols=["FirstVal = Col"]
    ),
    agg.sorted_last(order_by="SortCol", cols=["LastVal = Col"]),    # Last by sort order
], by=["Group"])
```

### Value Selection
```python
from deephaven import agg, new_table
from deephaven.column import double_col, string_col

t = new_table([
    string_col("Group", ["A", "A", "B", "B"]),
    double_col("Col", [10.0, 20.0, 30.0, 40.0]),
])

t.agg_by([
    agg.first(cols=["FirstVal = Col"]),        # First value
    agg.last(cols=["LastVal = Col"]),          # Last value
    agg.group(cols=["AllVals = Col"]),         # Collect into array
    agg.distinct(cols=["UniqueVals = Col"]),   # Distinct values as array
], by=["Group"])
```

### Counting
```python
from deephaven import agg, new_table
from deephaven.column import double_col, string_col

t = new_table([
    string_col("Group", ["A", "A", "A", "B", "B"]),
    double_col("Col", [10.0, 10.0, 20.0, 30.0, 30.0]),
    double_col("Price", [50.0, 150.0, 200.0, 75.0, 125.0]),
])

t.agg_by([
    agg.count_(col="RowCount"),                           # Count rows
    agg.count_distinct(cols=["NumUnique = Col"]),         # Count distinct values
    agg.count_where(col="FilteredCount", filters="Price > 100"),  # Conditional count
], by=["Group"])
```

### Weighted
```python
from deephaven import agg, new_table
from deephaven.column import double_col, string_col

t = new_table([
    string_col("Group", ["A", "A", "B", "B"]),
    double_col("Weight", [0.5, 0.5, 0.3, 0.7]),
    double_col("Value", [100.0, 200.0, 300.0, 400.0]),
])

t.agg_by([
    agg.weighted_avg(wcol="Weight", cols=["WAvg = Value"]),  # Weighted average
    agg.weighted_sum(wcol="Weight", cols=["WSum = Value"]),  # Weighted sum
], by=["Group"])
```

### Percentiles
```python
from deephaven import agg, new_table
from deephaven.column import double_col, string_col

t = new_table([
    string_col("Group", ["A"] * 10 + ["B"] * 10),
    double_col("Value", [float(i) for i in range(20)]),
])

t.agg_by([
    agg.pct(percentile=0.5, cols=["P50 = Value"]),   # 50th percentile
    agg.pct(percentile=0.95, cols=["P95 = Value"]),  # 95th percentile
], by=["Group"])
```

### Advanced
```python
from deephaven import agg, new_table
from deephaven.column import double_col, string_col

t = new_table([
    string_col("Group", ["A", "A", "B", "B"]),
    double_col("Col1", [10.0, 20.0, 30.0, 40.0]),
])

# Custom formula aggregation
# (formula_param names the variable, cols maps Result = Source)
t.agg_by([
    agg.formula(
        formula="max(each) - min(each)",
        formula_param="each",
        cols=["Range = Col1"]
    ),
], by=["Group"])

# Partition into sub-tables
t.agg_by([
    agg.partition(col="SubTable", include_by_columns=False),
], by=["Group"])
```

## agg_by Options

```python
from deephaven import agg, new_table
from deephaven.column import double_col, string_col

t = new_table([
    string_col("GroupCol1", ["A", "A", "B", "B"]),
    string_col("GroupCol2", ["X", "Y", "X", "Y"]),
    double_col("Value", [10.0, 20.0, 30.0, 40.0]),
])

groups_table = new_table([
    string_col("GroupCol1", ["A", "A", "B", "B"]),
    string_col("GroupCol2", ["X", "Y", "X", "Y"]),
])

t.agg_by(
    aggs=[agg.sum_(cols=["Total = Value"])],
    by=["GroupCol1", "GroupCol2"],      # Grouping columns
    preserve_empty=True,                 # Keep empty groups
    initial_groups=groups_table,         # Pre-define group keys
)
```

**preserve_empty**: Keeps result rows for groups that become empty after updates.

**initial_groups**: Table defining all possible group combinations upfront.

## Grouping and Ungrouping

```python
from deephaven import new_table
from deephaven.column import double_col, int_col, string_col

t = new_table([
    string_col("Sym", ["AAPL", "AAPL", "GOOG", "GOOG"]),
    double_col("Price", [150.0, 152.0, 140.0, 142.0]),
    int_col("Qty", [100, 200, 150, 250]),
])

# Group into arrays
grouped = t.group_by("Sym")  # Each column becomes an array

# Ungroup arrays back to rows
ungrouped = grouped.ungroup(["Price", "Qty"])  # Explode specific columns
ungrouped = grouped.ungroup()  # Explode all array columns
```

## Partitioned Tables

```python
from deephaven import new_table
from deephaven.column import double_col, string_col

t = new_table([
    string_col("Sym", ["AAPL", "AAPL", "GOOG", "GOOG"]),
    double_col("Price", [150.0, 152.0, 140.0, 142.0]),
])

# Split table by key into constituent tables
partitioned = t.partition_by("Sym")

# Access constituents
constituents = partitioned.constituent_tables
single = partitioned.get_constituent(["AAPL"])

# Get partition keys
keys = partitioned.keys()

# Merge back together
merged = partitioned.merge()
```

**Transform** applies a function to every constituent. The function must run inside an execution context:
```python
from deephaven import new_table
from deephaven.column import double_col, string_col
from deephaven.execution_context import get_exec_ctx

t = new_table([
    string_col("Sym", ["AAPL", "AAPL", "GOOG", "GOOG"]),
    double_col("Price", [150.0, 152.0, 140.0, 142.0]),
])

partitioned = t.partition_by("Sym")
ctx = get_exec_ctx()

def add_rank(t):
    with ctx:
        return t.update(["Rank = ii + 1"])

transformed = partitioned.transform(add_rank)
merged = transformed.merge()
```

## Partitioned Aggregation

```python
from deephaven import agg, new_table
from deephaven.column import double_col, string_col

t = new_table([
    string_col("Sym", ["AAPL", "AAPL", "GOOG", "GOOG"]),
    string_col("Exchange", ["NYSE", "NYSE", "NASDAQ", "NASDAQ"]),
    double_col("Price", [150.0, 152.0, 140.0, 142.0]),
])

# Aggregate and partition by key columns → returns PartitionedTable
result = t.partitioned_agg_by(
    aggs=[agg.avg(cols=["AvgPrice = Price"])],
    by=["Sym"],
)
```

## Common Patterns

**OHLCV (Candlestick) aggregation:**
```python
from deephaven import agg, new_table
from deephaven.column import double_col, int_col, string_col

t = new_table([
    string_col("Sym", ["AAPL", "AAPL", "AAPL", "GOOG", "GOOG", "GOOG"]),
    string_col("TimeBucket", ["10:00", "10:00", "10:00", "10:00", "10:00", "10:00"]),
    double_col("Price", [150.0, 152.0, 148.0, 140.0, 142.0, 138.0]),
    int_col("Qty", [100, 200, 150, 250, 300, 100]),
])

ohlcv = t.agg_by([
    agg.first(cols=["Open = Price"]),
    agg.max_(cols=["High = Price"]),
    agg.min_(cols=["Low = Price"]),
    agg.last(cols=["Close = Price"]),
    agg.sum_(cols=["Volume = Qty"]),
], by=["Sym", "TimeBucket"])
```

**Latest value per key:**
```python
from deephaven import new_table
from deephaven.column import double_col, string_col

t = new_table([
    string_col("Sym", ["AAPL", "AAPL", "GOOG", "GOOG"]),
    double_col("Price", [150.0, 152.0, 140.0, 142.0]),
])

latest = t.last_by("Sym")
```

**Top N per group:**
```python
from deephaven import new_table
from deephaven.column import double_col, string_col

t = new_table([
    string_col("Category", ["A", "A", "A", "A", "B", "B", "B", "B"]),
    double_col("Value", [10.0, 40.0, 20.0, 30.0, 50.0, 80.0, 60.0, 70.0]),
])

top3 = t.sort_descending("Value").head_by(3, "Category")
```

**Count with percentage:**
```python
from deephaven import agg, new_table
from deephaven.column import string_col

t = new_table([
    string_col("Category", ["A", "A", "A", "B", "B", "C"]),
])

counts = t.agg_by([agg.count_(col="Count")], by=["Category"])
total = counts.view(["Total = Count"]).sum_by()
result = counts.natural_join(total, on=[]).update(["Pct = Count / Total * 100"])
```

## Memory Warning

Aggregation keys persist in memory for the worker's lifetime, even after rows are removed from the table. Be cautious with high-cardinality grouping keys on long-running workers.

## Documentation URLs

- agg_by: https://deephaven.io/core/docs/reference/table-operations/group-and-aggregate/aggBy.md
- Dedicated aggs: https://deephaven.io/core/docs/how-to-guides/combined-aggregations.md
- group_by: https://deephaven.io/core/docs/reference/table-operations/group-and-aggregate/groupBy.md
- partition_by: https://deephaven.io/core/docs/reference/table-operations/group-and-aggregate/partitionBy.md
