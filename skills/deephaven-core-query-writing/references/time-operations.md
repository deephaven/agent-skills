# Deephaven Time Operations Reference

## Date-Time Literals

In query strings, use single quotes for date-time values (not backticks, which are for strings).

```python
from deephaven import empty_table

t = empty_table(5).update([
    "Timestamp = parseInstant(`2024-01-01T09:30:00 America/New_York`) + i * 'PT1h'",
    "Date = parseLocalDate(`2024-01-0` + (i + 1))",
    "Time = parseLocalTime(`09:3` + i + `:00`)",
])

# Instant (timestamp with timezone) - MUST use parseInstant with full IANA timezone
t.where("Timestamp > parseInstant(`2024-01-01T09:30:00 America/New_York`)")
t.where("Timestamp > parseInstant(`2024-01-01T14:30:00 UTC`)")
t.where("Timestamp > parseInstant(`2024-01-01T09:30:00.123456789 America/New_York`)")

# Local date (no timezone)
t.where("Date = '2024-01-01'")

# Local time (no timezone)
t.where("Time > '09:30:00'")

# Duration (ISO 8601)
t.update(["Later = Timestamp + 'PT1h'"])       # 1 hour
t.update(["Later = Timestamp + 'PT30m'"])      # 30 minutes
t.update(["Later = Timestamp + 'PT1h30m15s'"]) # 1h 30m 15s
t.update(["Later = Timestamp - 'PT0.5s'"])     # 500 milliseconds

# Period (calendar-based)
t.update(["NextYear = Date + 'P1y'"])          # 1 year
t.update(["NextMonth = Date + 'P1m'"])         # 1 month
t.update(["NextWeek = Date + 'P7d'"])          # 7 days
```

**Timezone IDs (IANA format required):**
- `America/New_York` - US Eastern
- `America/Chicago` - US Central
- `America/Los_Angeles` - US Pacific
- `UTC` - Coordinated Universal Time

**WARNING:** Short aliases like `NY`, `ET`, `PT`, `CT` do NOT work in query string time literals. Always use full IANA timezone IDs with `parseInstant`.

## Creating Timestamped Tables

```python
from deephaven import empty_table, time_table

# Time table - ticks at intervals
ticking = time_table("PT1s")  # Every second
ticking = time_table("PT0.1s")  # Every 100ms
ticking = time_table("PT1s", start_time="2024-01-01T09:30:00 America/New_York")

# Empty table with timestamp formulas
t = empty_table(100).update([
    "Timestamp = parseInstant(`2024-01-01T09:30:00 America/New_York`) + i * 'PT1m'"
])

# From Python datetime
import datetime as dt

from deephaven.time import to_j_instant

ts = dt.datetime(2024, 1, 15, 10, 30, 0)
j_instant = to_j_instant(ts)
```

## Parsing Time Data

```python
from deephaven import empty_table

t = empty_table(5).update([
    "DateTimeString = `2024-01-0` + (i + 1) + `T10:00:00 UTC`",
    "DateString = `2024-01-0` + (i + 1)",
    "TimeString = `10:0` + i + `:00`",
    "LocalDateCol = parseLocalDate(DateString)",
    "LocalTimeCol = parseLocalTime(TimeString)",
])

# Parse ISO 8601 format
t.update(["Parsed = parseInstant(DateTimeString)"])

# Parse local date
t.update(["ParsedDate = parseLocalDate(DateString)"])

# Parse local time
t.update(["ParsedTime = parseLocalTime(TimeString)"])

# Combine date and time columns
t.update([
    "Combined = toInstant(LocalDateCol, LocalTimeCol, 'America/New_York')"
])
```

## Extracting Components

```python
from deephaven import empty_table

t = empty_table(10).update([
    "Timestamp = parseInstant("
    "`2024-06-15T14:30:45.123456789 America/New_York`"
    ") + i * 'PT1h'",
])

t.update([
    # Date components (use timeZone() to wrap timezone IDs)
    "Year = year(Timestamp, timeZone(`America/New_York`))",
    "Month = monthOfYear(Timestamp, timeZone(`America/New_York`))",
    "Day = dayOfMonth(Timestamp, timeZone(`America/New_York`))",
    "DayOfWeek = dayOfWeek(Timestamp, timeZone(`America/New_York`))",  # 1=Monday
    "DayOfYear = dayOfYear(Timestamp, timeZone(`America/New_York`))",

    # Time components
    "Minute = minuteOfHour(Timestamp, timeZone(`America/New_York`))",
    "Second = secondOfMinute(Timestamp, timeZone(`America/New_York`))",
    "Millis = millisOfSecond(Timestamp, timeZone(`America/New_York`))",
    "Nanos = nanosOfSecond(Timestamp, timeZone(`America/New_York`))",

    # For hour/minuteOfDay, use Java methods via toLocalTime or toZonedDateTime
    "LocalTime = toLocalTime(Timestamp, timeZone(`America/New_York`))",
    "Hour = LocalTime.getHour()",
])
```

## Time Binning

```python
from deephaven import empty_table

t = empty_table(100).update([
    "Timestamp = parseInstant(`2024-01-01T09:30:00 America/New_York`) + i * 'PT1m'",
])

t.update([
    # Round down to interval
    "Bin5min = lowerBin(Timestamp, 'PT5m')",
    "BinHour = lowerBin(Timestamp, 'PT1h')",
    # Use Duration, NOT Period ('P1d' fails on Instants)
    "BinDay = lowerBin(Timestamp, 'PT24h')",

    # Round up to interval
    "BinUp = upperBin(Timestamp, 'PT5m')",
])
```

## Current Time

**In query strings:**
```python
from deephaven import empty_table

t = empty_table(1)
t.update(["CurrentTime = now()"])
t.update(["Today = today('America/New_York')"])
t.update(["TZ = timeZone()"])  # Engine timezone
```

**Outside query strings (Python side):**
```python
from deephaven.time import dh_now, dh_time_zone, dh_today

current = dh_now()
today = dh_today()
tz = dh_time_zone()
```

## Time Arithmetic

```python
from deephaven import empty_table

t = empty_table(10).update([
    "Timestamp = parseInstant(`2024-01-01T09:30:00 America/New_York`) + i * 'PT1h'",
    "Timestamp2 = Timestamp + 'PT30m'",
    "Timestamp1 = Timestamp",
])

t.update([
    # Add/subtract durations
    "Plus1Hour = Timestamp + 'PT1h'",
    "Minus30Min = Timestamp - 'PT30m'",

    # Difference between timestamps (returns nanoseconds)
    "DiffNanos = Timestamp2 - Timestamp1",

    # Convert to other units
    "DiffSeconds = (Timestamp2 - Timestamp1) / SECOND",
    "DiffMinutes = (Timestamp2 - Timestamp1) / MINUTE",
    "DiffHours = (Timestamp2 - Timestamp1) / HOUR",
])
```

**Built-in time constants (nanoseconds):**
- `SECOND` = 1,000,000,000
- `MINUTE` = 60 * SECOND
- `HOUR` = 60 * MINUTE
- `DAY` = 24 * HOUR
- `WEEK` = 7 * DAY
- `YEAR_365` = 365 * DAY
- `YEAR_AVG` = 365.2425 * DAY

## Time Zone Conversion

```python
from deephaven import empty_table

t = empty_table(5).update([
    "Timestamp = parseInstant(`2024-06-15T14:30:00 UTC`) + i * 'PT1h'",
])

t.update([
    # Convert to different timezone for display
    "NYTime = toZonedDateTime(Timestamp, timeZone(`America/New_York`))",
    "LondonTime = toZonedDateTime(Timestamp, timeZone(`Europe/London`))",
])
```

## Formatting for Display

```python
from deephaven import empty_table

t = empty_table(5).update([
    "Timestamp = parseInstant(`2024-06-15T14:30:00 UTC`) + i * 'PT1h'",
])

# Format instant as display string
formatted = t.update([
    "Display = formatDateTime(Timestamp, timeZone(`America/New_York`))"
])
```

## Business Calendar Operations

```python
from deephaven import empty_table

t = empty_table(10).update([
    "Timestamp = parseInstant(`2024-06-10T10:00:00 America/New_York`) + i * 'PT24h'",
    "Start = parseInstant(`2024-06-10T10:00:00 America/New_York`)",
    "End = parseInstant(`2024-06-20T10:00:00 America/New_York`)",
])

# Check if business day (uses default calendar)
t.where("isBusinessDay(Timestamp)")

# Get next/previous business day
t.update([
    "NextBizDay = plusBusinessDays(Timestamp, 1)",
    "PrevBizDay = minusBusinessDays(Timestamp, 1)",
])

# Business days between dates
t.update([
    "BizDaysBetween = diffBusinessDays(Start, End)"
])
```

## Time-Based Joins

```python
import datetime

from deephaven import new_table
from deephaven.column import datetime_col, double_col, string_col

trades = new_table([
    string_col("Sym", ["AAPL", "GOOG"]),
    datetime_col("TradeTime", [
        datetime.datetime(2024, 6, 1, 10, 0, 1, tzinfo=datetime.timezone.utc),
        datetime.datetime(2024, 6, 1, 10, 0, 2, tzinfo=datetime.timezone.utc),
    ]),
    double_col("Price", [150.0, 140.0]),
])

quotes = new_table([
    string_col("Sym", ["AAPL", "GOOG"]),
    datetime_col("QuoteTime", [
        datetime.datetime(2024, 6, 1, 10, 0, 0, tzinfo=datetime.timezone.utc),
        datetime.datetime(2024, 6, 1, 10, 0, 1, tzinfo=datetime.timezone.utc),
    ]),
    double_col("Bid", [149.0, 139.0]),
])

# As-of join (get quote at trade time)
trades.aj(quotes, on=["Sym", "TradeTime >= QuoteTime"])

# Reverse as-of join (get next quote after trade)
trades.raj(quotes, on=["Sym", "TradeTime <= QuoteTime"])
```

## Time-Based Rolling Operations

```python
from deephaven import empty_table
from deephaven.updateby import ema_time, rolling_avg_time

t = empty_table(100).update([
    "Sym = i % 2 == 0 ? `AAPL` : `GOOG`",
    "Timestamp = parseInstant(`2024-01-01T09:30:00 America/New_York`) + i * 'PT1m'",
    "Price = 150.0 + Math.sin(i * 0.1) * 10",
])

t.update_by([
    # 5-minute moving average
    rolling_avg_time("Timestamp", cols=["MA5m = Price"], rev_time="PT5m"),

    # 1-hour exponential moving average
    ema_time("Timestamp", decay_time="PT1h", cols=["EMA1h = Price"]),
], by=["Sym"])
```

## Python <-> Java Time Conversion

```python
# Python → Java
import datetime as dt

from deephaven.time import (
    to_date,
    to_datetime,
    to_j_duration,
    to_j_instant,
    to_j_local_date,
    to_j_local_time,
    to_time,
    to_timedelta,
)

j_instant = to_j_instant(dt.datetime(2024, 1, 15, 10, 30))
j_date = to_j_local_date(dt.date(2024, 1, 15))
j_time = to_j_local_time(dt.time(10, 30, 0))
j_duration = to_j_duration(dt.timedelta(hours=1, minutes=30))

# Java → Python
py_datetime = to_datetime(j_instant)
py_date = to_date(j_date)
py_time = to_time(j_time)
py_timedelta = to_timedelta(j_duration)
```

**Performance note:** Call conversion functions outside query strings. Converting inside query strings causes repeated Python-Java boundary crossings.

## Common Patterns

**Filter to market hours:**
```python
from deephaven import empty_table

t = empty_table(100).update([
    "Timestamp = parseInstant(`2024-06-15T06:00:00 America/New_York`) + i * 'PT15m'",
])

# Use Timestamp comparison for market hours filtering
tz = "timeZone(`America/New_York`)"
t.where([
    f"Timestamp >= parseInstant("
    f"formatDate(Timestamp, {tz})"
    " + `T09:30:00 America/New_York`)",
    f"Timestamp < parseInstant("
    f"formatDate(Timestamp, {tz})"
    " + `T16:00:00 America/New_York`)",
])
```

**Time-bucketed OHLCV:**
```python
from deephaven import agg, empty_table

t = empty_table(100).update([
    "Sym = i % 2 == 0 ? `AAPL` : `GOOG`",
    "Timestamp = parseInstant(`2024-01-01T09:30:00 America/New_York`) + i * 'PT10s'",
    "Price = 150.0 + Math.sin(i * 0.1) * 10",
    "Qty = (int)(100 + i * 10)",
])

t.update([
    "TimeBucket = lowerBin(Timestamp, 'PT1m')"
]).agg_by([
    agg.first(cols=["Open = Price"]),
    agg.max_(cols=["High = Price"]),
    agg.min_(cols=["Low = Price"]),
    agg.last(cols=["Close = Price"]),
    agg.sum_(cols=["Volume = Qty"]),
], by=["Sym", "TimeBucket"])
```

## Documentation URLs

- Time cheat sheet: https://deephaven.io/core/docs/reference/cheat-sheets/time-cheat-sheet.md
- Date-time types: https://deephaven.io/core/docs/reference/query-language/types/date-time.md
- Duration types: https://deephaven.io/core/docs/reference/query-language/types/durations.md
- Period types: https://deephaven.io/core/docs/reference/query-language/types/periods.md
