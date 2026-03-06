# Deephaven Joins Reference

## Join Types Overview

| Join Method | Match Type | Unmatched Rows | Multiple Matches |
|-------------|------------|----------------|------------------|
| `natural_join` | Exact | NULL values | Configurable (error/first/last) |
| `exact_join` | Exact | Error | Error (must be exactly one) |
| `join` | Exact | Excluded | All combinations returned |
| `aj` | As-of (<=) | NULL values | Closest match |
| `raj` | Reverse as-of (>=) | NULL values | Closest match |
| `range_join` | Range | NULL values | Aggregated |

## natural_join

Adds columns from right table. Unmatched rows get NULL. Most common join type.

```python
from deephaven import new_table
from deephaven.column import double_col, int_col, string_col

left = new_table(
    [
        string_col("KeyCol", ["A", "B", "C"]),
        double_col("LeftVal", [1.0, 2.0, 3.0]),
    ]
)

right = new_table(
    [
        string_col("KeyCol", ["A", "B", "D"]),
        double_col("Col1", [10.0, 20.0, 40.0]),
        double_col("Col2", [100.0, 200.0, 400.0]),
    ]
)

result = left.natural_join(
    table=right,
    on="KeyCol",  # or ["Key1", "Key2"]
    joins="Col1, Col2",  # columns to add (default: all)
)

# Match different column names
left2 = new_table(
    [
        string_col("LeftKey", ["A", "B"]),
        double_col("Val", [1.0, 2.0]),
    ]
)
right2 = new_table(
    [
        string_col("RightKey", ["A", "B"]),
        double_col("Info", [10.0, 20.0]),
    ]
)
left2.natural_join(right2, on="LeftKey = RightKey")

# Multiple keys
left3 = new_table(
    [
        string_col("Sym", ["AAPL", "GOOG"]),
        string_col("Date", ["2024-01-01", "2024-01-01"]),
        double_col("Price", [150.0, 140.0]),
    ]
)
right3 = new_table(
    [
        string_col("Sym", ["AAPL", "GOOG"]),
        string_col("Date", ["2024-01-01", "2024-01-01"]),
        int_col("Volume", [1000, 2000]),
    ]
)
left3.natural_join(right3, on=["Sym", "Date"])

# Rename while joining
left.natural_join(right, on="KeyCol", joins=["NewName = Col1"])
```

**Handling duplicates in right table:**
```python
from deephaven import new_table
from deephaven.column import double_col, string_col
from deephaven.table import NaturalJoinType

left = new_table(
    [
        string_col("Key", ["A", "B"]),
        double_col("Val", [1.0, 2.0]),
    ]
)

right = new_table(
    [
        string_col("Key", ["A", "A", "B"]),
        double_col("Info", [10.0, 11.0, 20.0]),
    ]
)

# Use first match
left.natural_join(right, on="Key", type=NaturalJoinType.FIRST_MATCH)

# Use last match
left.natural_join(right, on="Key", type=NaturalJoinType.LAST_MATCH)
```

## exact_join

Like natural_join but errors if not exactly one match per left row.

```python
from deephaven import new_table
from deephaven.column import double_col, string_col

left = new_table(
    [
        string_col("Key", ["A", "B"]),
        double_col("Val", [1.0, 2.0]),
    ]
)

right_table = new_table(
    [
        string_col("Key", ["A", "B"]),
        double_col("Col1", [10.0, 20.0]),
        double_col("Col2", [100.0, 200.0]),
    ]
)

result = left.exact_join(table=right_table, on="Key", joins="Col1, Col2")
```

Use when you require one-to-one matching and want to catch data issues.

## join (Cross Join)

Returns all matching combinations. With no keys, produces Cartesian product.

```python
from deephaven import new_table
from deephaven.column import double_col, string_col

left = new_table(
    [
        string_col("Key", ["A", "A", "B"]),
        double_col("LVal", [1.0, 2.0, 3.0]),
    ]
)

right = new_table(
    [
        string_col("Key", ["A", "B", "B"]),
        double_col("RVal", [10.0, 20.0, 30.0]),
    ]
)

# All matching rows from both tables
result = left.join(right, on="Key")

# Cross join (every combination) - use joins to avoid column name conflicts
result = left.join(right, on=[], joins=["RVal"])
```

**Warning:** Can produce very large result tables with multiple matches.

## aj (As-Of Join)

Time-series join finding the closest right-table timestamp that doesn't exceed the left timestamp.

```python
import datetime

from deephaven import new_table
from deephaven.column import datetime_col, double_col, string_col

trades = new_table(
    [
        string_col("Sym", ["AAPL", "AAPL", "GOOG"]),
        datetime_col(
            "Timestamp",
            [
                datetime.datetime(2024, 6, 1, 10, 0, 1, tzinfo=datetime.timezone.utc),
                datetime.datetime(2024, 6, 1, 10, 0, 3, tzinfo=datetime.timezone.utc),
                datetime.datetime(2024, 6, 1, 10, 0, 2, tzinfo=datetime.timezone.utc),
            ],
        ),
        double_col("TradePrice", [150.0, 152.0, 140.0]),
    ]
)

quotes = new_table(
    [
        string_col("Sym", ["AAPL", "AAPL", "GOOG"]),
        datetime_col(
            "Timestamp",
            [
                datetime.datetime(2024, 6, 1, 10, 0, 0, tzinfo=datetime.timezone.utc),
                datetime.datetime(2024, 6, 1, 10, 0, 2, tzinfo=datetime.timezone.utc),
                datetime.datetime(2024, 6, 1, 10, 0, 1, tzinfo=datetime.timezone.utc),
            ],
        ),
        double_col("Bid", [149.0, 151.0, 139.0]),
        double_col("Ask", [150.5, 152.5, 140.5]),
    ]
)

# Basic time-series join
trades.aj(quotes, on=["Sym", "Timestamp"])

# Select specific columns
trades.aj(quotes, on=["Sym", "Timestamp"], joins=["Bid", "Ask"])

# Rename columns
trades.aj(quotes, on=["Sym", "Timestamp"], joins=["QuoteBid = Bid"])
```

**Common patterns:**

```python
import datetime

from deephaven import new_table
from deephaven.column import datetime_col, double_col, string_col

trades = new_table(
    [
        string_col("Ticker", ["AAPL", "GOOG"]),
        datetime_col(
            "TradeTime",
            [
                datetime.datetime(2024, 6, 1, 10, 0, 1, tzinfo=datetime.timezone.utc),
                datetime.datetime(2024, 6, 1, 10, 0, 2, tzinfo=datetime.timezone.utc),
            ],
        ),
        double_col("Price", [150.0, 140.0]),
    ]
)

quotes = new_table(
    [
        string_col("Ticker", ["AAPL", "GOOG"]),
        datetime_col(
            "QuoteTime",
            [
                datetime.datetime(2024, 6, 1, 10, 0, 0, tzinfo=datetime.timezone.utc),
                datetime.datetime(2024, 6, 1, 10, 0, 1, tzinfo=datetime.timezone.utc),
            ],
        ),
        double_col("Bid", [149.0, 139.0]),
        double_col("Ask", [150.5, 140.5]),
    ]
)

# Get quote at trade time
trades.aj(quotes, on=["Ticker", "TradeTime >= QuoteTime"])

# Exclude exact timestamp matches (use > instead of >=)
trades.aj(quotes, on=["Ticker", "TradeTime > QuoteTime"])
```

## raj (Reverse As-Of Join)

Like aj but finds closest right timestamp >= left timestamp (looking forward).

```python
import datetime

from deephaven import new_table
from deephaven.column import datetime_col, double_col, string_col

trades = new_table(
    [
        string_col("Sym", ["AAPL", "GOOG"]),
        datetime_col(
            "Timestamp",
            [
                datetime.datetime(2024, 6, 1, 10, 0, 0, tzinfo=datetime.timezone.utc),
                datetime.datetime(2024, 6, 1, 10, 0, 1, tzinfo=datetime.timezone.utc),
            ],
        ),
        double_col("Price", [150.0, 140.0]),
    ]
)

quotes = new_table(
    [
        string_col("Sym", ["AAPL", "GOOG"]),
        datetime_col(
            "Timestamp",
            [
                datetime.datetime(2024, 6, 1, 10, 0, 1, tzinfo=datetime.timezone.utc),
                datetime.datetime(2024, 6, 1, 10, 0, 2, tzinfo=datetime.timezone.utc),
            ],
        ),
        double_col("Bid", [149.0, 139.0]),
    ]
)

# Find next quote after trade
trades.raj(quotes, on=["Sym", "Timestamp"])
```

## range_join

Joins rows falling within a range, then aggregates the matches.

```python
from deephaven import agg, new_table
from deephaven.column import double_col, int_col

left = new_table(
    [
        int_col("start_col", [0, 10, 20]),
        int_col("end_col", [10, 20, 30]),
    ]
)

right = new_table(
    [
        int_col("range_col", [5, 15, 25]),
        double_col("Value", [100.0, 200.0, 300.0]),
    ]
)

result = left.range_join(
    table=right,
    on=["start_col <= range_col <= end_col"],
    aggs=[agg.group(cols=["MatchedValues = Value"])],
)
```

**Range match syntax:**
- `"left_start <= right_col <= left_end"` - inclusive
- `"left_start < right_col < left_end"` - exclusive
- `"<- left_start <= right_col <= left_end ->"` - allow preceding/following

**Constraints:**
- Currently only supports `agg.group()` aggregation
- Right table must be sorted by range column within each exact-match group
- Static tables only

## Join Syntax Reference

**The `on` and `joins` parameters:**
```python
from deephaven import new_table
from deephaven.column import double_col, string_col

left = new_table(
    [
        string_col("X", ["A", "B"]),
        string_col("A", ["x", "y"]),
        double_col("LVal", [1.0, 2.0]),
    ]
)

right = new_table(
    [
        string_col("X", ["A", "B"]),
        string_col("B", ["x", "y"]),
        double_col("Col1", [10.0, 20.0]),
        double_col("Col2", [100.0, 200.0]),
    ]
)

# on: Match column X in both tables
left.natural_join(right, on=["X"], joins=["Col1"])

# on: Match left.A with right.B (different column names)
left.natural_join(right, on=["A = B"], joins=["Col1"])

# on: Multiple conditions
left.natural_join(right, on=["X", "A = B"], joins=["Col1"])

# joins: Add specific columns from right
left.natural_join(right, on="X", joins=["Col1", "Col2"])

# joins: Rename while adding
left.natural_join(right, on="X", joins=["NewName = Col1"])

# joins: Add all non-key columns (default when omitted)
left.natural_join(right, on=["X", "A = B"])
```

## Performance Tips

1. **Index join columns** when joining large tables frequently
2. **Filter before joining** to reduce data volume
3. **Use `natural_join`** for one-to-one/many-to-one relationships
4. **Use `aj`/`raj`** for time-series data instead of range comparisons
5. **Avoid `join` with multiple matches** unless you need all combinations

## Documentation URLs

- natural_join: https://deephaven.io/core/docs/reference/table-operations/join/natural-join.md
- exact_join: https://deephaven.io/core/docs/reference/table-operations/join/exact-join.md
- join: https://deephaven.io/core/docs/reference/table-operations/join/join.md
- aj: https://deephaven.io/core/docs/reference/table-operations/join/aj.md
- raj: https://deephaven.io/core/docs/reference/table-operations/join/raj.md
- range_join: https://deephaven.io/core/docs/reference/table-operations/join/range-join.md
