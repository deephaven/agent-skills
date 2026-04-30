---
name: deephaven-core-query-writing
description: Work with Deephaven for real-time data processing. Use for table queries, joins, aggregations, time-series, UI dashboards, plotting (dx), Kafka streaming, Iceberg integration. Triggers on mentions of Deephaven, tables or queries, and related concepts.
license: Apache-2.0
metadata:
  author: Deephaven Data Labs
  version: "0.1.0"
---

## References

You must always read reference files before writing code.

| Topic | Reference File | Read before writing code that... |
| --- | --- | --- |
| Joins | `references/joins.md` | uses natural_join, aj, raj, exact_join, range_join; match syntax, performance tips |
| Aggregations | `references/aggregations.md` | uses agg_by, sum_by, avg_by, count_by, etc.; 20+ aggregators, common patterns |
| Update-by | `references/updateby.md` | uses rolling ops, cumulative ops, EMAs, forward fill |
| Time | `references/time-operations.md` | parses, bins, or manipulates timestamps; literals, calendars, timezone conversion |
| Kafka | `references/kafka.md` | consumes from or produces to Kafka; table types, key/value specs |
| Iceberg | `references/iceberg.md` | reads/writes Iceberg tables; catalog types, partitioned writes |
| UI | `references/ui.md` | creates dashboards, components, hooks, ui.table, styling |
| Plotting | `references/plotting.md` | creates charts with dx; all plot types, subplots, interactivity |
| CSV | `references/csv.md` | imports/exports any CSV files; column types, renaming, date parsing, messy files |

**Do NOT guess or rely on memory.** Deephaven APIs have specific patterns that differ from similar libraries.

## Core Principles

**YOU NEVER ADD PRINT STATEMENTS TO PRINT TABLES, DO NOT CONVERT TO PANDAS JUST TO PRINT**

**Filter early.** Place partition/grouping column filters first in `where()` to exclude data early.

**Do as much in-engine as possible.** Deephaven's Java engine is highly optimized. Prefer built-in operations over Python UDFs.

**Avoid Python UDFs in query strings.** Each Python call crosses the Python-Java boundary (slower). Use built-in functions from `java.lang.Math`, string, time functions, and auto-imported query language functions instead.

**Don't use pandas for intermediate steps.** Converting to pandas and back is slow and can cause memory issues. Use Deephaven's native operations. Avoid pandas unless specifically asked for.

**All imports at the top of the file.** Import only the modules you need. Never use `__import__()` or inline imports mid-script.

### Example Table Creation

```python
from deephaven import agg, empty_table, merge, new_table, read_csv, time_table, ui
from deephaven.column import double_col, string_col
from deephaven.plot import express as dx

# Empty table with formulas
t = empty_table(100).update(["X = i", "Y = X * 2"])

# New table from columns
t = new_table(
    [string_col("Sym", ["AAPL", "GOOG"]), double_col("Price", [150.0, 140.0])]
)

# Ticking time table (real-time)
t = time_table("PT1s")  # accepts durations

# Ring table (bounded size, keeps last N rows)
source = time_table("PT1s")
t = ring_table(source, capacity=1000)
```

### Extracting Scalar Values

`print(table)` only shows the object reference. To get actual values for a specific cell:

```python
from deephaven import empty_table

table = empty_table(1).update(["ColName = 42.5"])

# Get a scalar from a 1-row result table
value = table.j_table.getColumnSource("ColName").get(
    table.j_table.getRowSet().firstRowKey()
)
print(f"Result: {value:,.2f}")
```

### Column Operations

```python
from deephaven import empty_table

t = empty_table(100).update(["A = i", "B = i * 2", "OldName = i", "Unwanted = i"])

# select — returns ONLY named columns; stores results in RAM
# Best for: column subset with expensive formulas or frequently accessed results
t.select(["A", "B", "C = A + B"])

# view — returns ONLY named columns; recalculates on every access (no RAM cost)
# Best for: column subset with cheap formulas, sparse access, or memory pressure
t.view(["A", "B", "C = A + B"])

# update — keeps ALL columns + adds new; stores results in RAM
# Best for: results that feed downstream ops (joins, aggs, further updates)
t.update(["C = A + B", "D = sqrt(C)"])

# update_view — keeps ALL columns + adds new; recalculates on every access
# Best for: display-only columns, or when memory is a concern
t.update_view(["C = A + B"])

# lazy_update — keeps ALL columns + adds new; memoizes by input value
# Best for: few distinct inputs relative to row count (e.g. category lookups)
t.lazy_update(["C = A + B"])

# drop_columns — remove columns
t.drop_columns(["Unwanted"])

# select_distinct — unique rows for named columns
t.select_distinct(["A"])  # unique values of A
t.select_distinct(["A", "B"])  # unique (A, B) pairs

# rename_columns — rename columns
t.rename_columns(["NewName = OldName"])
```

### Filtering

```python
import datetime

from deephaven import new_table
from deephaven.column import datetime_col, double_col, string_col

t = new_table(
    [
        string_col("Sym", ["AAPL", "GOOG", "MSFT", "AMZN"]),
        double_col("Price", [150.0, 140.0, 200.0, 50.0]),
        string_col("Description", ["no error", "has error", "fine", "ok"]),
        datetime_col(
            "Timestamp",
            [
                datetime.datetime(2024, 6, 1, tzinfo=datetime.timezone.utc),
                datetime.datetime(2024, 6, 2, tzinfo=datetime.timezone.utc),
                datetime.datetime(2024, 6, 3, tzinfo=datetime.timezone.utc),
                datetime.datetime(2024, 6, 4, tzinfo=datetime.timezone.utc),
            ],
        ),
    ]
)

filter_table = new_table([string_col("Sym", ["AAPL", "GOOG"])])

# Basic where
t.where("Price > 100")
t.where(["Sym = `AAPL`", "Price > 100"])  # AND logic

# String matching (Java String methods)
t.where("Sym.startsWith(`A`)")
t.where("Description.contains(`error`)")

# Set membership (fast)
t.where("Sym in `AAPL`, `GOOG`, `MSFT`")
t.where_in(filter_table, "Sym")
t.where_not_in(filter_table, "Sym")

# Time filtering
t.where("Timestamp > parseInstant(`2024-01-01T00:00:00 America/New_York`)")

# Dynamic filter — backtick-quote the interpolated string value
sym = "AAPL"
t.where(f"Sym = `{sym}`")
```

### Joins Overview

**Read `references/joins.md` before using joins.**

| Join           | Use Case                                    | Match Type  |
| -------------- | ------------------------------------------- | ----------- |
| `natural_join` | Add columns from right, NULL if no match    | Exact       |
| `exact_join`   | Add columns, error if not exactly one match | Exact       |
| `join`         | All matching combinations                   | Exact       |
| `aj`           | As-of join: find closest <= timestamp       | Time-series |
| `raj`          | Reverse as-of: find closest >= timestamp    | Time-series |
| `range_join`   | Match within ranges, aggregate results      | Range       |

Vertical stacking: `from deephaven import merge` / `merge([t1, t2])` — tables must have matching column names and types.

### Aggregations Overview

**Read `references/aggregations.md` before using aggregations.**

| Approach | Use Case | Example |
| --- | --- | --- |
| `sum_by`, `avg_by`, `min_by`, `max_by`, `median_by`, `std_by`, `var_by`, `abs_sum_by` | Single stat, all numeric columns | `t.sum_by("Sym")` |
| `count_by` | Row count per group (first arg is output col name) | `t.count_by("Count", "Sym")` |
| `first_by` / `last_by` | First/last row per group | `t.last_by("Sym")` |
| `head_by` / `tail_by` | First/last N rows per group | `t.head_by(5, "Sym")` |
| `weighted_avg_by` / `weighted_sum_by` | Weighted stats (first arg is weight col) | `t.weighted_avg_by("Weight", "Sym")` |
| `agg_by` | Multiple aggs in one pass | `t.agg_by([agg.avg(...), agg.sum_(...)], by=["Sym"])` |
| `group_by` / `ungroup` | Collect into arrays / explode back | `t.group_by("Sym")` |
| `partition_by` | Split into sub-tables by key | `t.partition_by("Sym")` |

Dedicated aggs operate on ALL non-key columns. If any are non-numeric (String, Timestamp), they throw `UnsupportedOperationException`. **Fix:** add `.view()` before the agg to keep only key + numeric columns, or use `agg_by` with explicit `cols`.

### Query String Syntax

**Literals:**

- Boolean: `true`, `false` (lowercase)
- Int: `42`, Long: `42L`, Double: `3.14` (underscores like `1_000L` are NOT supported). **Bare integers in division produce double:** `(year / 10) * 10` → `1987.0`. Fix: `year - year % 10` or `(int)(year / 10) * 10`
- String: backticks `` `hello` ``
- DateTime: `parseInstant(\`2024-01-01T12:00:00 America/New_York\`)`(short aliases like`NY` do NOT work)
- Duration: `'PT1h30m'`, Period: `'P1y2m3d'`

**Built-in variables:**

- `i` - row index (0-based)
- `ii` / `k` - row key (stable identifier)

**Ternary operator:**

```python
from deephaven import empty_table

t = empty_table(10).update(["Price = i * 25.0"])
t.update(["Category = Price > 100 ? `High` : `Low`"])
```

**Null handling:**

```python
from deephaven import empty_table

t = empty_table(10).update(["Value = i % 2 == 0 ? NULL_INT : i"])
t.update(["Safe = isNull(Value) ? 0 : Value"])
```

### Data Import/Export

```python
from deephaven import empty_table, read_csv, write_csv
from deephaven.parquet import read, write

t = empty_table(10).update(["X = i", "Y = X * 2"])

# CSV
write_csv(t, "/tmp/output.csv")
t_csv = read_csv("/tmp/output.csv")

# Parquet
write(t, "/tmp/output.parquet")
t_parquet = read("/tmp/output.parquet")
```

