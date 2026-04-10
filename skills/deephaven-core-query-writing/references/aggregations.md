# Deephaven Aggregations Reference

## Dedicated Aggregations

Single-operation aggregations optimized for common use cases.

```python
from deephaven import new_table
from deephaven.column import double_col, int_col, string_col

t = new_table(
    [
        string_col("Sym", ["AAPL", "AAPL", "GOOG", "GOOG", "MSFT", "MSFT"]),
        double_col("Price", [150.0, 152.0, 140.0, 142.0, 200.0, 198.0]),
        int_col("Qty", [100, 200, 150, 250, 300, 100]),
        double_col("Weight", [0.5, 0.3, 0.7, 0.2, 0.4, 0.6]),
        double_col("Value", [1500.0, 3040.0, 2100.0, 3550.0, 6000.0, 1980.0]),
    ]
)

# (by): sum_by, avg_by, min_by, max_by, median_by,
# std_by, var_by, abs_sum_by, first_by, last_by
t.view(["Price", "Qty", "Value"]).sum_by()  # no arg — entire table (numeric only)
t.sum_by("Sym")  # single grouping column (key excluded from agg)
t.sum_by(["Sym", "Weight"])  # multiple grouping columns
t.avg_by("Sym")
t.min_by("Sym")
t.max_by("Sym")
t.median_by("Sym")
t.std_by("Sym")
t.var_by("Sym")
t.abs_sum_by("Sym")
t.first_by("Sym")
t.last_by("Sym")

# (col, by): count_by — first arg is the OUTPUT column name
t.count_by("Count")  # no grouping — entire table
t.count_by("Count", "Sym")
t.count_by("Count", ["Sym", "Weight"])

# (n, by) or (wcol, by): first arg is NOT a grouping key
t.head_by(5, "Sym")
t.tail_by(5, "Sym")
t.weighted_avg_by("Weight", "Sym")  # wcol first, then by
t.weighted_sum_by("Weight", "Sym")
```

**Warning — `UnsupportedOperationException: Unsupported type class java.lang.String`:**
Dedicated aggs like `avg_by`, `std_by`, `var_by`, `median_by` operate on ALL non-key columns. If any non-key column is a String (or other non-numeric type), they throw. Also throws `aggAllBy has no columns to aggregate` if all non-key columns have been dropped (must have something to aggregate). **Fix: narrow to key + numeric columns before the agg (`.view()` or `.select()`), use `select_distinct` for unique keys, or use `count_by` when you only need counts.**

```python
from deephaven import agg, new_table
from deephaven.column import double_col, string_col

t = new_table(
    [
        string_col("Sym", ["AAPL", "AAPL", "GOOG"]),
        string_col("Exchange", ["NYSE", "NYSE", "NASDAQ"]),
        double_col("Price", [150.0, 152.0, 140.0]),
    ]
)

# WRONG — Exchange is a String, avg_by will throw
# t.avg_by("Sym")

# Fix: narrow to key + numeric columns first
t.view(["Sym", "Price"]).avg_by("Sym")

# Or use agg_by with explicit cols (never touches non-numeric columns)
t.agg_by([agg.avg(cols=["AvgPrice = Price"])], by=["Sym"])
```

## Combined Aggregations (agg_by)

Multiple aggregations in a single pass — more efficient than separate calls with `from deephaven import agg`.

```python
import datetime

from deephaven import agg, new_table
from deephaven.column import datetime_col, double_col, int_col, string_col

t = new_table(
    [
        string_col("Sym", ["AAPL", "AAPL", "GOOG", "GOOG"]),
        double_col("Price", [150.0, 152.0, 140.0, 142.0]),
        int_col("Qty", [100, 200, 150, 250]),
        double_col("Weight", [0.5, 0.5, 0.3, 0.7]),
        datetime_col(
            "Timestamp",
            [
                datetime.datetime(2024, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
                datetime.datetime(2024, 6, 1, 11, 0, tzinfo=datetime.timezone.utc),
                datetime.datetime(2024, 6, 1, 10, 0, tzinfo=datetime.timezone.utc),
                datetime.datetime(2024, 6, 1, 11, 0, tzinfo=datetime.timezone.utc),
            ],
        ),
    ]
)

result = t.agg_by(
    [
        # Statistical
        agg.avg(cols=["AvgPrice = Price"]),
        agg.sum_(cols=["TotalQty = Qty"]),  # note underscore
        agg.min_(cols=["MinPrice = Price"]),
        agg.max_(cols=["MaxPrice = Price"]),
        agg.median(cols=["MedPrice = Price"]),
        agg.std(cols=["StdPrice = Price"]),
        agg.var(cols=["VarPrice = Price"]),
        agg.abs_sum(cols=["AbsQty = Qty"]),
        # Weighted
        agg.weighted_avg(wcol="Weight", cols=["WAvgPrice = Price"]),
        agg.weighted_sum(wcol="Weight", cols=["WSumPrice = Price"]),
        # Counting
        agg.count_(col="RowCount"),  # note underscore
        agg.count_distinct(cols=["NumPrices = Price"]),
        agg.count_where(col="HighCount", filters="Price > 141"),
        # Value selection
        agg.first(cols=["FirstTime = Timestamp"]),
        agg.last(cols=["LastTime = Timestamp"]),
        agg.group(cols=["AllPrices = Price"]),  # collect into array
        agg.distinct(cols=["UniquePrices = Price"]),  # distinct values as array
        # Percentiles
        agg.pct(percentile=0.5, cols=["P50Price = Price"]),
        agg.pct(percentile=0.95, cols=["P95Price = Price"]),
    ],
    by=["Sym"],
)
```

Additional aggregators not shown above:

```python
from deephaven import agg, new_table
from deephaven.column import double_col, int_col, string_col

t = new_table(
    [
        string_col("Group", ["A", "A", "B", "B"]),
        int_col("SortCol", [2, 1, 4, 3]),
        double_col("Val", [100.0, 200.0, 300.0, 400.0]),
    ]
)

t.agg_by(
    [
        agg.sorted_first(order_by="SortCol", cols=["FirstVal = Val"]),
        agg.sorted_last(order_by="SortCol", cols=["LastVal = Val"]),
        # formula_param names the variable, cols maps Result = Source
        agg.formula(
            formula="max(each) - min(each)", formula_param="each", cols=["Range = Val"]
        ),
        agg.partition(col="SubTable", include_by_columns=False),
    ],
    by=["Group"],
)
```

**agg_by options** — `preserve_empty` keeps result rows for groups that become empty after updates; `initial_groups` pre-defines all possible group keys:

```python
from deephaven import agg, new_table
from deephaven.column import double_col, string_col

t = new_table(
    [
        string_col("Sym", ["AAPL", "AAPL"]),
        double_col("Price", [150.0, 152.0]),
    ]
)

all_syms = new_table([string_col("Sym", ["AAPL", "GOOG", "MSFT"])])

t.agg_by(
    aggs=[agg.sum_(cols=["Total = Price"])],
    by=["Sym"],
    preserve_empty=True,
    initial_groups=all_syms,
)
```

## Grouping, Ungrouping, and Partitioning

```python
from deephaven import agg, new_table
from deephaven.column import double_col, int_col, string_col
from deephaven.execution_context import get_exec_ctx

t = new_table(
    [
        string_col("Sym", ["AAPL", "AAPL", "GOOG", "GOOG"]),
        string_col("Exchange", ["NYSE", "NYSE", "NASDAQ", "NASDAQ"]),
        double_col("Price", [150.0, 152.0, 140.0, 142.0]),
        int_col("Qty", [100, 200, 150, 250]),
    ]
)

# group_by — collapse rows into arrays per key
grouped = t.group_by("Sym")  # each column becomes an array
ungrouped = grouped.ungroup(["Price", "Qty"])  # explode specific columns
ungrouped = grouped.ungroup()  # explode all array columns

# partition_by — split into sub-tables per key
partitioned = t.partition_by("Sym")
constituents = partitioned.constituent_tables
single = partitioned.get_constituent(["AAPL"])
keys = partitioned.keys()
merged = partitioned.merge()

# transform — apply a function to every constituent (needs execution context)
ctx = get_exec_ctx()


def add_rank(t):
    with ctx:
        return t.update(["Rank = ii + 1"])


transformed = partitioned.transform(add_rank)
merged = transformed.merge()

# partitioned_agg_by — aggregate and return a PartitionedTable
result = t.partitioned_agg_by(
    aggs=[agg.avg(cols=["AvgPrice = Price"])],
    by=["Sym"],
)
```

## Common Patterns

```python
from deephaven import agg, new_table
from deephaven.column import double_col, int_col, string_col

# OHLCV (Candlestick) aggregation
trades = new_table(
    [
        string_col("Sym", ["AAPL", "AAPL", "AAPL", "GOOG", "GOOG", "GOOG"]),
        string_col(
            "TimeBucket", ["10:00", "10:00", "10:00", "10:00", "10:00", "10:00"]
        ),
        double_col("Price", [150.0, 152.0, 148.0, 140.0, 142.0, 138.0]),
        int_col("Qty", [100, 200, 150, 250, 300, 100]),
    ]
)
ohlcv = trades.agg_by(
    [
        agg.first(cols=["Open = Price"]),
        agg.max_(cols=["High = Price"]),
        agg.min_(cols=["Low = Price"]),
        agg.last(cols=["Close = Price"]),
        agg.sum_(cols=["Volume = Qty"]),
    ],
    by=["Sym", "TimeBucket"],
)

# Top N per group
scores = new_table(
    [
        string_col("Category", ["A", "A", "A", "A", "B", "B", "B", "B"]),
        double_col("Value", [10.0, 40.0, 20.0, 30.0, 50.0, 80.0, 60.0, 70.0]),
    ]
)
top3 = scores.sort_descending("Value").head_by(3, "Category")

# Count with percentage
items = new_table([string_col("Category", ["A", "A", "A", "B", "B", "C"])])
counts = items.agg_by([agg.count_(col="Count")], by=["Category"])
total = counts.view(["Total = Count"]).sum_by()
result = counts.natural_join(total, on=[]).update(["Pct = Count / Total * 100"])
```

## Memory Warning

Aggregation keys persist in memory for the worker's lifetime, even after rows are removed from the table. Be cautious with high-cardinality grouping keys on long-running workers.

## Documentation URLs

https://deephaven.io/core/docs/reference/table-operations/group-and-aggregate/aggBy.md
https://deephaven.io/core/docs/how-to-guides/combined-aggregations.md
https://deephaven.io/core/docs/reference/table-operations/group-and-aggregate/groupBy.md
https://deephaven.io/core/docs/reference/table-operations/group-and-aggregate/partitionBy.md
