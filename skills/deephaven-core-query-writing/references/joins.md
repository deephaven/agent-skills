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

**Common gotchas:**
- **Type mismatch errors** — join key columns must have the same type on both sides. `string` vs `int` throws `Mismatched join types`. Cast first with `.update(["Key = `` + Key"])` or use `header` to match types at import.
- **Column name conflicts** — if left and right share non-key column names, joins error with `Conflicting column names`. Fix: use `joins=["NewName = Col"]` to rename, or `.drop_columns()` before joining.
- **String date keys** — work as exact string matches, but mismatched formats (e.g. `2024-01-01` vs `01/01/2024`) silently produce NULLs instead of erroring.

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
    on="KeyCol",  # or ["Key1", "Key2"] for multiple keys
    joins="Col1, Col2",  # columns to add (default: all non-key)
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

**Handling duplicates in right table** — `natural_join` errors by default if the right table has duplicate keys. Use `type=` to pick first/last, or pre-deduplicate with `right.last_by("KeyCol")` before joining:
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

Like `natural_join` but errors if any left row has zero or multiple matches. Use when you require strict one-to-one matching: `left.exact_join(right, on="Key", joins="Col1, Col2")`.

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

Time-series join finding the closest right-table timestamp <= the left timestamp. Use `raj` for the reverse direction (>=).

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
            "QuoteTime",
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

# Get quote at or before trade time (default: <=)
trades.aj(quotes, on=["Sym", "Timestamp >= QuoteTime"], joins=["Bid", "Ask"])

# Exclude exact matches (strict <)
trades.aj(quotes, on=["Sym", "Timestamp > QuoteTime"], joins=["Bid", "Ask"])

# raj — same syntax, finds closest right timestamp >= left (looking forward)
trades.raj(quotes, on=["Sym", "Timestamp <= QuoteTime"], joins=["Bid", "Ask"])
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

**Constraints:** Currently only supports `agg.group()` aggregation. Right table must be sorted by range column. Static tables only.

## Performance Tips

1. **Filter before joining** to reduce data volume
2. **Use `natural_join`** for one-to-one/many-to-one relationships
3. **Use `aj`/`raj`** for time-series data instead of range comparisons
4. **Avoid `join` with multiple matches** unless you need all combinations