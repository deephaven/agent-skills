# Deephaven update_by Reference

Rolling, cumulative, and window operations that add columns based on row-by-row calculations.

## All Operations

All operations require numeric columns. Every `_tick` op has a `_time` counterpart (first arg is `ts_col`, uses `rev_time`/`fwd_time` ISO durations instead of `rev_ticks`/`fwd_ticks`).

- `cum_sum`, `cum_prod`, `cum_min`, `cum_max` — running cumulative values
- `cum_count_where` — cumulative count matching filter (`col=, filters=`)
- `forward_fill` — fill NULL/NaN with last valid value
- `delta` — difference from previous row (`delta_control=` for null behavior)
- `rolling_{sum,avg,min,max,prod,count,std}_tick/_time` — rolling window aggregations
- `rolling_wavg_tick/_time` — rolling weighted average (`wcol=` required)
- `rolling_group_tick/_time` — collect window values into array
- `rolling_count_where_tick/_time` — count matching filter in window (`col=, filters=`)
- `rolling_formula_tick/_time` — custom formula (see below)
- `ema_tick/_time`, `ems_tick/_time`, `emmin_tick/_time`, `emmax_tick/_time`, `emstd_tick/_time` — exponential moving average/sum/min/max/std (`decay_ticks=` / `decay_time=`)

## Cumulative, Forward Fill, and Delta

```python
from deephaven import new_table
from deephaven.column import double_col, string_col
from deephaven.updateby import (
    cum_count_where,
    cum_max,
    cum_min,
    cum_prod,
    cum_sum,
    delta,
    forward_fill,
)

t = new_table(
    [
        string_col("Sym", ["AAPL", "AAPL", "AAPL", "GOOG", "GOOG", "GOOG"]),
        double_col("Price", [150.0, float("nan"), 152.0, 140.0, 142.0, 141.0]),
        double_col("Value", [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]),
    ]
)

t.update_by(
    [
        cum_sum(cols=["RunningTotal = Value"]),
        cum_prod(cols=["RunningProduct = Value"]),
        cum_min(cols=["RunningMin = Value"]),
        cum_max(cols=["RunningMax = Value"]),
        cum_count_where(col="CountAbove25", filters="Value > 25"),
        forward_fill(cols=["FilledPrice = Price"]),  # fills NaN with last valid
        delta(cols=["PriceChange = Price"]),  # difference from previous row
    ],
    by=["Sym"],
)
```

## Rolling and EMA Operations (Tick-Based)

Window based on row count. `rev_ticks` = rows to look back (including current), `fwd_ticks` = rows forward (default 0).

```python
from deephaven import new_table
from deephaven.column import double_col, int_col, string_col
from deephaven.updateby import (
    ema_tick,
    emmax_tick,
    emmin_tick,
    ems_tick,
    emstd_tick,
    rolling_avg_tick,
    rolling_count_tick,
    rolling_count_where_tick,
    rolling_group_tick,
    rolling_max_tick,
    rolling_min_tick,
    rolling_prod_tick,
    rolling_std_tick,
    rolling_sum_tick,
    rolling_wavg_tick,
)

t = new_table(
    [
        string_col("Sym", ["AAPL"] * 20 + ["GOOG"] * 20),
        double_col(
            "Price",
            [150.0 + i * 0.5 for i in range(20)] + [140.0 + i * 0.3 for i in range(20)],
        ),
        double_col(
            "PrevPrice",
            [149.0 + i * 0.5 for i in range(20)] + [139.0 + i * 0.3 for i in range(20)],
        ),
        int_col("Qty", [100 + i * 10 for i in range(40)]),
        int_col("Volume", [1000 + i * 50 for i in range(40)]),
    ]
)

t.update_by(
    [
        rolling_avg_tick(cols=["MA10 = Price"], rev_ticks=10),
        rolling_sum_tick(cols=["Sum10 = Qty"], rev_ticks=10),
        rolling_min_tick(cols=["Min10 = Price"], rev_ticks=10),
        rolling_max_tick(cols=["Max10 = Price"], rev_ticks=10),
        rolling_std_tick(cols=["StdDev = Price"], rev_ticks=20),
        rolling_prod_tick(cols=["Prod5 = Price"], rev_ticks=5),
        rolling_count_tick(cols=["NonNull = Price"], rev_ticks=10),
        rolling_avg_tick(cols=["MA_Ctr = Price"], rev_ticks=5, fwd_ticks=5),
        rolling_wavg_tick(wcol="Volume", cols=["VWAP = Price"], rev_ticks=20),
        rolling_group_tick(cols=["Last5 = Price"], rev_ticks=5),
        rolling_count_where_tick(
            col="UpTicks", filters="Price > PrevPrice", rev_ticks=10
        ),
        ema_tick(decay_ticks=10, cols=["EMA = Price"]),
        ems_tick(decay_ticks=10, cols=["EMS = Qty"]),
        emmin_tick(decay_ticks=10, cols=["EMMin = Price"]),
        emmax_tick(decay_ticks=10, cols=["EMMax = Price"]),
        emstd_tick(decay_ticks=10, cols=["EMStd = Price"]),
    ],
    by=["Sym"],
)
```

## Time-Based Variants

Every `_tick` operation above has a `_time` counterpart. The difference: first arg is `ts_col` (timestamp column), uses `rev_time`/`fwd_time` ISO 8601 durations instead of `rev_ticks`/`fwd_ticks`. Use `_tick` for fixed row counts; use `_time` for real-time duration windows with irregular data.

**Time durations:** `PT1s` (1 sec), `PT5m` (5 min), `PT1h` (1 hour), `PT1h30m` (1.5 hours)

```python
from deephaven import empty_table
from deephaven.updateby import (
    ema_time,
    rolling_avg_time,
    rolling_count_where_time,
    rolling_wavg_time,
)

t = empty_table(100).update(
    [
        "Sym = i % 2 == 0 ? `AAPL` : `GOOG`",
        "Timestamp = parseInstant(`2024-01-01T09:30:00 America/New_York`) + i * 'PT1m'",
        "Price = 150.0 + Math.sin(i * 0.1) * 10",
        "PrevPrice = 150.0 + Math.sin((i - 1) * 0.1) * 10",
        "Volume = (int)(1000 + i * 50)",
    ]
)

t.update_by(
    [
        rolling_avg_time("Timestamp", cols=["MA_5min = Price"], rev_time="PT5m"),
        rolling_avg_time(
            "Timestamp", cols=["MA_Ctr = Price"], rev_time="PT2m", fwd_time="PT2m"
        ),
        rolling_wavg_time(
            "Timestamp", wcol="Volume", cols=["VWAP = Price"], rev_time="PT10m"
        ),
        rolling_count_where_time(
            "Timestamp", col="UpMoves", filters="Price > PrevPrice", rev_time="PT10m"
        ),
        ema_time("Timestamp", decay_time="PT5m", cols=["EMA = Price"]),
    ],
    by=["Sym"],
)
```

## Rolling Formula (Custom Calculations)

Apply custom formulas to rolling windows. `formula_param` names the variable representing the window data inside the formula — the formula cannot reference column names directly, only this alias. Operates on one input column at a time (multi-column formulas are not supported).

Available functions in formula: `max`, `min`, `sum`, `count`, `avg`, `var`, `std`, `first`, `last`, `countDistinct`, plus array indexing (`x[0]`) and `x.size()`.

```python
from deephaven import empty_table
from deephaven.updateby import rolling_formula_tick, rolling_formula_time

t = empty_table(100).update(
    [
        "Sym = i % 2 == 0 ? `AAPL` : `GOOG`",
        "Timestamp = parseInstant(`2024-01-01T09:30:00 America/New_York`) + i * 'PT1m'",
        "Price = 150.0 + Math.sin(i * 0.1) * 10",
    ]
)

t.update_by(
    [
        # Tick-based: x is the window data for Price
        rolling_formula_tick(
            formula="max(x) - min(x)",
            formula_param="x",
            cols=["Range = Price"],
            rev_ticks=10,
        ),
        # Time-based: same pattern
        rolling_formula_time(
            "Timestamp",
            formula="max(x) - min(x)",
            formula_param="x",
            cols=["TimeRange = Price"],
            rev_time="PT5m",
        ),
    ],
    by=["Sym"],
)
```

## Common Patterns

**MACD and Bollinger Bands:**
```python
from deephaven import new_table
from deephaven.column import double_col, string_col
from deephaven.updateby import ema_tick, rolling_avg_tick, rolling_std_tick

t = new_table(
    [
        string_col("Sym", ["AAPL"] * 30),
        double_col("Price", [150.0 + i * 0.5 for i in range(30)]),
    ]
)

# MACD: fast EMA - slow EMA, then signal line
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

# Bollinger Bands: MA +/- 2 standard deviations
bands = t.update_by(
    [
        rolling_avg_tick(cols=["MA = Price"], rev_ticks=20),
        rolling_std_tick(cols=["StdDev = Price"], rev_ticks=20),
    ],
    by=["Sym"],
).update(["UpperBand = MA + 2 * StdDev", "LowerBand = MA - 2 * StdDev"])
```

## NaN / Null Handling

EMA operations accept `op_control=` to configure behavior when encountering NaN or null values:

```python
from deephaven import new_table
from deephaven.column import double_col
from deephaven.updateby import BadDataBehavior, OperationControl, ema_tick

t = new_table([double_col("V", [10.0, float("nan"), 30.0, 40.0])])

# SKIP (default for EMA): ignore NaN, continue calculation
# POISON: NaN propagates to all subsequent values
# RESET: restart calculation from next valid value
oc = OperationControl(on_nan=BadDataBehavior.RESET)
t.update_by([ema_tick(decay_ticks=3, cols=["E = V"], op_control=oc)])
```

`delta` uses `delta_control=` instead: `DeltaControl.NULL_DOMINATES` (default), `VALUE_DOMINATES`, or `ZERO_DOMINATES`.
