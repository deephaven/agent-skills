# Deephaven update_by Reference

Rolling, cumulative, and window operations that add columns based on row-by-row calculations.

## Basic Usage

```python
from deephaven import new_table
from deephaven import updateby as uby
from deephaven.column import double_col, string_col

t = new_table(
    [
        string_col("GroupCol", ["A", "A", "A", "B", "B", "B"]),
        double_col("Value", [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]),
    ]
)

result = t.update_by(
    ops=[uby.cum_sum(cols=["CumTotal = Value"])],
    by=["GroupCol"],  # Optional grouping
)
```

## Cumulative Operations

Calculate running totals from the start of data.

```python
from deephaven import new_table
from deephaven.column import double_col, string_col
from deephaven.updateby import cum_count_where, cum_max, cum_min, cum_prod, cum_sum

t = new_table(
    [
        string_col("Sym", ["AAPL", "AAPL", "AAPL", "GOOG", "GOOG", "GOOG"]),
        double_col("Value", [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]),
    ]
)

t.update_by(
    [
        cum_sum(cols=["RunningTotal = Value"]),
        cum_prod(cols=["RunningProduct = Value"]),
        cum_min(cols=["RunningMin = Value"]),
        cum_max(cols=["RunningMax = Value"]),
        cum_count_where(col="CountAbove100", filters="Value > 100"),
    ],
    by=["Sym"],
)
```

## Forward Fill

Fill NULL values with the last non-NULL value.

```python
from deephaven import new_table
from deephaven.column import double_col, string_col
from deephaven.updateby import forward_fill

t = new_table(
    [
        string_col("Sym", ["AAPL", "AAPL", "AAPL"]),
        double_col("Price", [150.0, float("nan"), 152.0]),
    ]
)

t.update_by([forward_fill(cols=["FilledPrice = Price"])], by=["Sym"])
```

## Delta

Calculate difference from previous row.

```python
from deephaven import new_table
from deephaven.column import double_col, string_col
from deephaven.updateby import delta

t = new_table(
    [
        string_col("Sym", ["AAPL", "AAPL", "AAPL"]),
        double_col("Price", [150.0, 152.0, 148.0]),
    ]
)

t.update_by([delta(cols=["PriceChange = Price"])], by=["Sym"])
```

## Rolling Operations (Tick-Based)

Window based on row count.

```python
from deephaven import new_table
from deephaven.column import double_col, int_col, string_col
from deephaven.updateby import (
    rolling_avg_tick,
    rolling_count_where_tick,
    rolling_group_tick,
    rolling_std_tick,
    rolling_sum_tick,
    rolling_wavg_tick,
)

t = new_table(
    [
        string_col("Sym", ["AAPL"] * 20 + ["GOOG"] * 20),
        double_col(
            "Price",
            (
                [150.0 + i * 0.5 for i in range(20)]
                + [140.0 + i * 0.3 for i in range(20)]
            ),
        ),
        double_col(
            "PrevPrice",
            (
                [149.0 + i * 0.5 for i in range(20)]
                + [139.0 + i * 0.3 for i in range(20)]
            ),
        ),
        int_col("Qty", [100 + i * 10 for i in range(40)]),
        int_col("Volume", [1000 + i * 50 for i in range(40)]),
    ]
)

t.update_by(
    [
        # 10-row lookback
        rolling_avg_tick(cols=["MA10 = Price"], rev_ticks=10),
        # 5 back, 5 forward (centered window)
        rolling_avg_tick(cols=["MA_Centered = Price"], rev_ticks=5, fwd_ticks=5),
        # Sum of last 20 rows
        rolling_sum_tick(cols=["Sum20 = Qty"], rev_ticks=20),
        # Rolling standard deviation
        rolling_std_tick(cols=["StdDev = Price"], rev_ticks=20),
        # Rolling count where condition met
        rolling_count_where_tick(
            col="UpTicks", filters="Price > PrevPrice", rev_ticks=10
        ),
        # Collect values into array
        rolling_group_tick(cols=["Last5Prices = Price"], rev_ticks=5),
        # Weighted average (requires weight column)
        rolling_wavg_tick(wcol="Volume", cols=["VWAP = Price"], rev_ticks=20),
    ],
    by=["Sym"],
)
```

**Parameters:**
- `rev_ticks`: Rows to look back (including current)
- `fwd_ticks`: Rows to look forward (default: 0)

## Rolling Operations (Time-Based)

Window based on time duration.

```python
from deephaven import empty_table
from deephaven.updateby import (
    rolling_avg_time,
    rolling_count_where_time,
    rolling_sum_time,
)

t = empty_table(100).update(
    [
        "Sym = i % 2 == 0 ? `AAPL` : `GOOG`",
        "Timestamp = parseInstant(`2024-01-01T09:30:00 America/New_York`) + i * 'PT1m'",
        "Price = 150.0 + Math.sin(i * 0.1) * 10",
        "PrevPrice = 150.0 + Math.sin((i - 1) * 0.1) * 10",
        "Qty = (int)(100 + i * 10)",
    ]
)

t.update_by(
    [
        # 5-minute lookback
        rolling_avg_time("Timestamp", cols=["MA_5min = Price"], rev_time="PT5m"),
        # 1-hour lookback
        rolling_sum_time("Timestamp", cols=["Volume1h = Qty"], rev_time="PT1h"),
        # 30-second centered window
        rolling_avg_time(
            "Timestamp",
            cols=["MA_Centered = Price"],
            rev_time="PT15s",
            fwd_time="PT15s",
        ),
        # Count conditions in window
        rolling_count_where_time(
            "Timestamp", col="UpMoves", filters="Price > PrevPrice", rev_time="PT10m"
        ),
    ],
    by=["Sym"],
)
```

**Time duration format (ISO 8601):**
- `PT1s` - 1 second
- `PT5m` - 5 minutes
- `PT1h` - 1 hour
- `PT1h30m` - 1 hour 30 minutes

## Exponential Moving Averages (Tick-Based)

```python
from deephaven import new_table
from deephaven.column import double_col, int_col, string_col
from deephaven.updateby import ema_tick, emmax_tick, emmin_tick, ems_tick, emstd_tick

t = new_table(
    [
        string_col("Sym", ["AAPL"] * 20 + ["GOOG"] * 20),
        double_col(
            "Price",
            (
                [150.0 + i * 0.5 for i in range(20)]
                + [140.0 + i * 0.3 for i in range(20)]
            ),
        ),
        int_col("Qty", [100 + i * 10 for i in range(40)]),
    ]
)

t.update_by(
    [
        # EMA with decay over 10 ticks
        ema_tick(decay_ticks=10, cols=["EMA = Price"]),
        # Exponential moving sum
        ems_tick(decay_ticks=10, cols=["EMS = Qty"]),
        # Exponential moving min/max
        emmin_tick(decay_ticks=10, cols=["EMMin = Price"]),
        emmax_tick(decay_ticks=10, cols=["EMMax = Price"]),
        # Exponential moving standard deviation
        emstd_tick(decay_ticks=10, cols=["EMStd = Price"]),
    ],
    by=["Sym"],
)
```

## Exponential Moving Averages (Time-Based)

```python
from deephaven import empty_table
from deephaven.updateby import ema_time, emstd_time

t = empty_table(100).update(
    [
        "Sym = i % 2 == 0 ? `AAPL` : `GOOG`",
        "Timestamp = parseInstant(`2024-01-01T09:30:00 America/New_York`) + i * 'PT1m'",
        "Price = 150.0 + Math.sin(i * 0.1) * 10",
    ]
)

t.update_by(
    [
        # EMA with 5-minute decay
        ema_time("Timestamp", decay_time="PT5m", cols=["EMA = Price"]),
        # Exponential moving std with 1-hour decay
        emstd_time("Timestamp", decay_time="PT1h", cols=["EMStd = Price"]),
    ],
    by=["Sym"],
)
```

## Rolling Formula (Custom Calculations)

Apply custom formulas to rolling windows.

```python
from deephaven import empty_table
from deephaven.updateby import rolling_formula_tick, rolling_formula_time

t = empty_table(100).update(
    [
        "Sym = i % 2 == 0 ? `AAPL` : `GOOG`",
        "Timestamp = parseInstant(`2024-01-01T09:30:00 America/New_York`) + i * 'PT1m'",
        "Price = 150.0 + Math.sin(i * 0.1) * 10",
        "Qty = (int)(100 + i * 10)",
    ]
)

t.update_by(
    [
        # Custom formula over 10-tick window
        rolling_formula_tick(
            formula="max(Price) - min(Price)",  # Range
            formula_param="Price",
            cols=["Range = Price"],
            rev_ticks=10,
        ),
        # Time-based custom formula
        rolling_formula_time(
            "Timestamp",
            formula="max(x) - min(x)",  # Range over time window
            formula_param="x",
            cols=["TimeRange = Price"],
            rev_time="PT5m",
        ),
    ],
    by=["Sym"],
)
```

## Combining Multiple Operations

```python
from deephaven import empty_table
from deephaven import updateby as uby

t = empty_table(100).update(
    [
        "Sym = i % 2 == 0 ? `AAPL` : `GOOG`",
        "Price = 150.0 + Math.sin(i * 0.1) * 10",
        "Qty = (int)(100 + i * 10)",
        "Bid = Price - 0.5",
        "Ask = Price + 0.5",
    ]
)

result = t.update_by(
    [
        # Cumulative
        uby.cum_sum(cols=["CumQty = Qty"]),
        # Rolling averages at different windows
        uby.rolling_avg_tick(cols=["MA5 = Price"], rev_ticks=5),
        uby.rolling_avg_tick(cols=["MA20 = Price"], rev_ticks=20),
        # EMAs
        uby.ema_tick(decay_ticks=12, cols=["EMA12 = Price"]),
        uby.ema_tick(decay_ticks=26, cols=["EMA26 = Price"]),
        # Forward fill missing data
        uby.forward_fill(cols=["FilledBid = Bid", "FilledAsk = Ask"]),
    ],
    by=["Sym"],
)
```

## Common Patterns

**MACD Indicator:**
```python
from deephaven import new_table
from deephaven.column import double_col, string_col
from deephaven.updateby import ema_tick

t = new_table(
    [
        string_col("Sym", ["AAPL"] * 30),
        double_col("Price", [150.0 + i * 0.5 for i in range(30)]),
    ]
)

macd = (
    t.update_by(
        [
            ema_tick(decay_ticks=12, cols=["EMA12 = Price"]),
            ema_tick(decay_ticks=26, cols=["EMA26 = Price"]),
        ],
        by=["Sym"],
    )
    .update(["MACD = EMA12 - EMA26"])
    .update_by([ema_tick(decay_ticks=9, cols=["Signal = MACD"])], by=["Sym"])
    .update(["Histogram = MACD - Signal"])
)
```

**Bollinger Bands:**
```python
from deephaven import new_table
from deephaven.column import double_col, string_col
from deephaven.updateby import rolling_avg_tick, rolling_std_tick

t = new_table(
    [
        string_col("Sym", ["AAPL"] * 30),
        double_col("Price", [150.0 + i * 0.5 for i in range(30)]),
    ]
)

bands = t.update_by(
    [
        rolling_avg_tick(cols=["MA = Price"], rev_ticks=20),
        rolling_std_tick(cols=["StdDev = Price"], rev_ticks=20),
    ],
    by=["Sym"],
).update(["UpperBand = MA + 2 * StdDev", "LowerBand = MA - 2 * StdDev"])
```

**Time-Weighted Average Price (TWAP):**
```python
from deephaven import empty_table
from deephaven.updateby import rolling_avg_time

t = empty_table(100).update(
    [
        "Sym = i % 2 == 0 ? `AAPL` : `GOOG`",
        "Timestamp = parseInstant(`2024-01-01T09:30:00 America/New_York`) + i * 'PT1m'",
        "Price = 150.0 + Math.sin(i * 0.1) * 10",
    ]
)

twap = t.update_by(
    [rolling_avg_time("Timestamp", cols=["TWAP = Price"], rev_time="PT1h")], by=["Sym"]
)
```

## Documentation URLs

- update_by overview: https://deephaven.io/core/docs/reference/table-operations/update-by-operations/updateBy.md
- Rolling operations: https://deephaven.io/core/docs/reference/table-operations/update-by-operations/rolling-avg-tick.md
- EMA operations: https://deephaven.io/core/docs/reference/table-operations/update-by-operations/ema-tick.md
- Cumulative operations: https://deephaven.io/core/docs/reference/table-operations/update-by-operations/cum-sum.md
