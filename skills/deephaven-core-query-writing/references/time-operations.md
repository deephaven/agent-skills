# Deephaven Time Operations Reference

## Types and Parsing

**Types:** `Instant` (timestamp with timezone), `LocalDate` (date only), `LocalTime` (time only), `Duration` (fixed time amount like `PT1h`), `Period` (calendar amount like `P1m`).

**Timezone IDs:** Full IANA format (`America/New_York`, `America/Chicago`, `America/Los_Angeles`, `Europe/London`, `UTC`) or built-in aliases: `ET`, `CT`, `MT`, `PT`, `UTC`, `GMT`. Three-letter Java IDs (`EST`, `CST`, `PST`) and `NY` do NOT work.

```python
from deephaven import empty_table

t = empty_table(5).update(
    [
        # Parse from strings (backtick-delimited in query strings)
        "Ts = parseInstant(`2024-01-01T09:30:00 America/New_York`) + i * 'PT1h'",
        "D = parseLocalDate(`2024-01-0` + (i + 1))",
        "T = parseLocalTime(`09:3` + i + `:00`)",
        # Combine date + time into Instant
        "Combined = toInstant(D, T, 'America/New_York')",
    ]
)

# Filtering with time literals
t.where("Ts > parseInstant(`2024-01-01T11:00:00 America/New_York`)")
t.where("D = '2024-01-01'")  # LocalDate comparison uses single quotes
t.where("T > '09:30:00'")  # LocalTime comparison uses single quotes

# Null-safe parsing (returns null instead of error on bad input)
t.update(["Safe = parseInstantQuiet(`not-a-date`)"])

# Epoch timestamps (common in raw data)
t.update(["FromEpoch = epochSecondsToInstant(1718454600)"])
# Also: epochMillisToInstant(), epochMicrosToInstant(), epochNanosToInstant()

# Extract date/time parts from Instant
t.update(
    [
        "DatePart = toLocalDate(Ts, timeZone(`America/New_York`))",
        "TimePart = toLocalTime(Ts, timeZone(`America/New_York`))",
    ]
)
```

**Non-standard date formats** (e.g., `MM/dd/yyyy`): use `simple_date_format` from `deephaven.time`:
```python
from deephaven import new_table
from deephaven.column import string_col
from deephaven.time import simple_date_format

t = new_table([string_col("Raw", ["06/15/2024 14:30:00", "12/25/2024 09:00:00"])])
fmt = simple_date_format("MM/dd/yyyy HH:mm:ss")
t.update(["Parsed = fmt.parse(Raw).toInstant()"])
```

## Creating Time Data

```python
from deephaven import empty_table, time_table

# Ticking time table (real-time)
ticking = time_table("PT1s")  # every second
ticking = time_table("PT1s", start_time="2024-01-01T09:30:00 America/New_York")

# Static timestamped table
t = empty_table(100).update(
    ["Timestamp = parseInstant(`2024-01-01T09:30:00 America/New_York`) + i * 'PT1m'"]
)

# Current time
t = empty_table(1).update(
    [
        "Now = now()",
        "TodayDate = today('America/New_York')",
        "EngineTZ = timeZone()",
    ]
)
```

**From Python datetime:**
```python
import datetime as dt

from deephaven.time import to_j_instant, to_j_local_date, to_j_local_time

j_instant = to_j_instant(dt.datetime(2024, 1, 15, 10, 30))
j_date = to_j_local_date(dt.date(2024, 1, 15))
j_time = to_j_local_time(dt.time(10, 30, 0))
```

## Extracting Components

All extraction functions take `(Instant, ZoneId)`. Use `timeZone()` to wrap timezone IDs.

```python
from deephaven import empty_table

t = empty_table(10).update(
    ["Ts = parseInstant(`2024-06-15T14:30:45 America/New_York`) + i * 'PT1h'"]
)

tz = "timeZone(`America/New_York`)"
t.update(
    [
        f"Year = year(Ts, {tz})",
        f"Month = monthOfYear(Ts, {tz})",
        f"Day = dayOfMonth(Ts, {tz})",
        f"DayOfWeek = dayOfWeekValue(Ts, {tz})",  # 1=Mon, 7=Sun
        f"DayOfYear = dayOfYear(Ts, {tz})",
        f"Hour = hourOfDay(Ts, {tz}, true)",  # 0-23
        f"Minute = minuteOfHour(Ts, {tz})",
        f"MinOfDay = minuteOfDay(Ts, {tz}, true)",  # 0-1439
        f"Second = secondOfMinute(Ts, {tz})",
        f"Millis = millisOfSecond(Ts, {tz})",
        f"Micros = microsOfSecond(Ts, {tz})",
        f"Nanos = nanosOfSecond(Ts, {tz})",
    ]
)
```

## Arithmetic and Differences

```python
from deephaven import empty_table

t = empty_table(5).update(
    [
        "Ts = parseInstant(`2024-01-01T09:30:00 America/New_York`) + i * 'PT1h'",
        "Ts2 = Ts + 'PT30m'",
        "D = parseLocalDate(`2024-01-0` + (i + 1))",
    ]
)

t.update(
    [
        # Duration arithmetic on Instants (ISO 8601: PT1h, PT30m, PT1h30m15s, PT0.5s)
        "Plus1Hour = Ts + 'PT1h'",
        "Minus30Min = Ts - 'PT30m'",
        # Period arithmetic on LocalDate (P1y, P1m, P7d)
        "NextMonth = D + 'P1m'",
        "NextYear = D + 'P1y'",
        # Dedicated diff functions (cleaner than manual nanos division)
        "DiffSec = diffSeconds(Ts, Ts2)",
        "DiffMin = diffMinutes(Ts, Ts2)",
        "DiffDays = diffDays(Ts, Ts2)",
        "DiffNanos = diffNanos(Ts, Ts2)",
    ]
)
```

**Time constants (nanoseconds):** `SECOND`, `MINUTE`, `HOUR`, `DAY`, `WEEK`, `YEAR_365`, `YEAR_AVG`, `MILLI`, `MICRO`. Use for manual conversion: `(Ts2 - Ts1) / HOUR`.

## Binning

```python
from deephaven import empty_table

t = empty_table(100).update(
    ["Ts = parseInstant(`2024-01-01T09:30:00 America/New_York`) + i * 'PT1m'"]
)

t.update(
    [
        "Bin5min = lowerBin(Ts, 'PT5m')",
        "BinHour = lowerBin(Ts, 'PT1h')",
        "BinDay = lowerBin(Ts, 'PT24h')",  # NOT 'P1d' — Period fails on Instants
        "BinUp = upperBin(Ts, 'PT5m')",  # rounds up
        "Midnight = atMidnight(Ts, timeZone(`America/New_York`))",
    ]
)
```

## Formatting and Timezone Conversion

```python
from deephaven import empty_table

t = empty_table(5).update(["Ts = parseInstant(`2024-06-15T14:30:00 UTC`) + i * 'PT1h'"])

t.update(
    [
        "DateStr = formatDate(Ts, timeZone(`America/New_York`))",  # "2024-06-15"
        "FullStr = formatDateTime(Ts, timeZone(`America/New_York`))",
        "NYTime = toZonedDateTime(Ts, timeZone(`America/New_York`))",
        "Epoch = epochMillis(Ts)",  # also: epochNanos, epochSeconds, epochMicros
    ]
)

# Reverse: epochMillisToInstant(long), epochNanosToInstant(long), etc.
```

## Business Calendar

Uses the default calendar. No setup required.

```python
from deephaven import empty_table

t = empty_table(10).update(
    [
        "Ts = parseInstant(`2024-06-10T10:00:00 America/New_York`) + i * 'PT24h'",
        "Start = parseInstant(`2024-06-10T10:00:00 America/New_York`)",
        "End = parseInstant(`2024-06-20T10:00:00 America/New_York`)",
    ]
)

t.where("isBusinessDay(Ts)")
t.update(
    [
        "NextBiz = plusBusinessDays(Ts, 1)",
        "PrevBiz = minusBusinessDays(Ts, 1)",
        "BizBetween = diffBusinessDays(Start, End)",
        "IsBizTime = isBusinessTime(Ts)",
    ]
)
```

## Common Patterns

**Time-bucketed OHLCV:**
```python
from deephaven import agg, empty_table

t = empty_table(100).update(
    [
        "Sym = i % 2 == 0 ? `AAPL` : `GOOG`",
        "Ts = parseInstant(`2024-01-01T09:30:00 America/New_York`) + i * 'PT10s'",
        "Price = 150.0 + Math.sin(i * 0.1) * 10",
        "Qty = (int)(100 + i * 10)",
    ]
)

t.update(["Bucket = lowerBin(Ts, 'PT1m')"]).agg_by(
    [
        agg.first(cols=["Open = Price"]),
        agg.max_(cols=["High = Price"]),
        agg.min_(cols=["Low = Price"]),
        agg.last(cols=["Close = Price"]),
        agg.sum_(cols=["Volume = Qty"]),
    ],
    by=["Sym", "Bucket"],
)
```

**Filter to market hours:**
```python
from deephaven import empty_table

t = empty_table(100).update(
    ["Ts = parseInstant(`2024-06-15T06:00:00 America/New_York`) + i * 'PT15m'"]
)

tz = "timeZone(`America/New_York`)"
t.where(
    [
        f"hourOfDay(Ts, {tz}, true) >= 9",
        f"hourOfDay(Ts, {tz}, true) < 16",
    ]
)
```
