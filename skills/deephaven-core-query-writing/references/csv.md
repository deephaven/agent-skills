# Deephaven CSV Reference

## Importing CSV Files

### read_csv Signature

```python
# pseudo
from deephaven import read_csv
import deephaven.dtypes as dht

result = read_csv(
    path: str,                        # file path or URL (supports compressed: .gz, .zip, .bz2, .7z, .zst, .tar variants)
    header: dict[str, dht.DType],     # column names -> types (overrides file header)
    headless: bool = False,           # True if file has no header row
    header_row: int = 0,              # which row contains headers (rows before it are skipped)
    skip_rows: int = 0,               # rows to skip after header before data
    num_rows: int = MAX_LONG,         # max data rows to read
    ignore_empty_lines: bool = False, # skip blank lines instead of erroring
    allow_missing_columns: bool = False,  # fill missing columns with null instead of erroring
    ignore_excess_columns: bool = False,  # ignore extra columns instead of erroring
    delimiter: str = ",",             # field separator
    quote: str = '"',                 # quoting character
    ignore_surrounding_spaces: bool = True,  # trim unquoted value whitespace
    trim: bool = False,               # trim quoted value whitespace
) -> Table
```

### Basic Import

```python
from deephaven import read_csv

# From a local file
t = read_csv("data/stocks.csv")

# From a URL
t_url = read_csv(
    "https://media.githubusercontent.com/media/deephaven/examples/main/Iris/csv/iris.csv"
)
```

### Alternative Delimiters

```python
from pathlib import Path

from deephaven import read_csv

# Create a tab-separated test file
Path("/tmp/test.tsv").write_text("Name\tValue\nAlpha\t10\nBeta\t20\n")

# Tab-separated
t_tsv = read_csv("/tmp/test.tsv", delimiter="\t")

# Create a pipe-separated test file
Path("/tmp/test.psv").write_text("Name|Value\nAlpha|10\nBeta|20\n")

# Pipe-separated
t_psv = read_csv("/tmp/test.psv", delimiter="|")
```

Any character can be used as a delimiter.

### Headerless Files

When the CSV has no header row, use `headless=True`. Columns are auto-named `Column1`, `Column2`, etc.

```python
from pathlib import Path

from deephaven import read_csv

# Create a headerless test file
Path("/tmp/headerless.csv").write_text(
    "2024-06-01,AAPL,153.0,1000000\n2024-06-02,GOOG,142.0,800000\n"
)

t = read_csv("/tmp/headerless.csv", headless=True)
```

### Specifying Column Names and Types on Import

Use the `header` parameter to define column names and types. This is the primary way to rename columns during import and fix type inference.

```python
from pathlib import Path

import deephaven.dtypes as dht
from deephaven import read_csv

# Create a headerless test file
Path("/tmp/headerless.csv").write_text(
    "2024-06-01,AAPL,153.0,1000000\n2024-06-02,GOOG,142.0,800000\n"
)

# Define exact column names and types for a headerless file
header = {
    "Date": dht.string,
    "Symbol": dht.string,
    "Price": dht.double,
    "Volume": dht.int64,
}

t = read_csv("/tmp/headerless.csv", header=header, headless=True)
```

When `header` is used with a file that has a header row, the `header` dict **overrides** the file's header — the column names and types from the dict are used instead.

```python
import deephaven.dtypes as dht
from deephaven import read_csv

# Override types on a file that has headers
header = {
    "Date": dht.string,
    "Symbol": dht.string,
    "Open": dht.double,
    "High": dht.double,
    "Low": dht.double,
    "Close": dht.double,
    "Volume": dht.int64,
    "Status": dht.string,
    "TimestampStr": dht.string,
}

t = read_csv("data/stocks.csv", header=header)
```

### Available Data Types

| Type | Python `dht` constant | Use for |
|------|----------------------|---------|
| `string` | `dht.string` | Text values |
| `bool_` | `dht.bool_` | True/false |
| `int16` | `dht.int16` | Small integers |
| `int32` | `dht.int32` | Standard integers |
| `int64` | `dht.int64` | Large integers |
| `float32` | `dht.float32` | Single-precision decimals |
| `float64` / `double` | `dht.double` | Double-precision decimals |
| `Instant` | `dht.Instant` | Timestamps (ISO-8601) |
| `LocalDate` | `dht.LocalDate` | Date without time |
| `LocalTime` | `dht.LocalTime` | Time without date |

### Handling Messy Files

```python
import deephaven.dtypes as dht
from deephaven import read_csv

header = {
    "Date": dht.string,
    "Symbol": dht.string,
    "Open": dht.double,
    "High": dht.double,
    "Low": dht.double,
    "Close": dht.double,
    "Volume": dht.int64,
    "Status": dht.string,
    "TimestampStr": dht.string,
}

t = read_csv(
    "data/stocks.csv",
    header=header,
    num_rows=3,  # only read 3 rows
    ignore_empty_lines=True,  # skip blank lines
    allow_missing_columns=True,  # null-fill missing columns
    ignore_excess_columns=True,  # ignore extra columns
    trim=True,  # strip whitespace from quoted values
)
```

### Reading Compressed Files

`read_csv` natively supports compressed files. No decompression step needed.

```python
# incomplete
from deephaven import read_csv

t = read_csv("/data/large_file.csv.gz")
t = read_csv("/data/archive.csv.zip")
```

Supported extensions: `.gz`, `.bz2`, `.zip`, `.7z`, `.zst`, `.tar`, `.tar.gz`, `.tar.bz2`, `.tar.zip`, `.tar.7z`, `.tar.zst`

---

## Exporting CSV Files

### write_csv Signature

```python
# pseudo
from deephaven import write_csv

write_csv(
    table: Table,          # source table
    path: str,             # output file path
    cols: list[str] = None # columns to include (default: all)
)
```

### Basic Export

```python
from deephaven import empty_table, write_csv

t = empty_table(100).update(["X = 0.1 * i", "Y = sin(X)", "Z = cos(X)"])

# Export all columns
write_csv(t, "/tmp/output.csv")

# Export specific columns
write_csv(t, "/tmp/partial.csv", cols=["X", "Y"])
```

### Null Handling in Export

Null values are written as empty fields in the CSV output.

```python
from deephaven import empty_table, write_csv

t = empty_table(10).update(
    [
        "X = i",
        "Y = i % 3 == 0 ? NULL_DOUBLE : i * 1.5",
    ]
)

write_csv(t, "/tmp/with_nulls.csv")
```

---

## Common Post-Import Operations

### Renaming Columns

After import, use `rename_columns` to rename columns or `view`/`select` to alias them.

```python
from deephaven import read_csv

t = read_csv("data/stocks.csv")

# Rename specific columns (NewName = OldName)
t_renamed = t.rename_columns(
    [
        "Ticker = Symbol",
        "ClosePrice = Close",
        "Vol = Volume",
    ]
)

# Or use view to rename and select specific columns
t_view = t.view(
    [
        "Ticker = Symbol",
        "ClosePrice = Close",
        "Vol = Volume",
    ]
)
```

### Fixing Column Types After Import

When `read_csv` infers the wrong type, cast columns with update formulas. This happens when a column contains mixed data or when you import with all-string types.

```python
import deephaven.dtypes as dht
from deephaven import read_csv

# Force all columns to string to demonstrate type fixing
header = {
    "Date": dht.string,
    "Symbol": dht.string,
    "Open": dht.string,
    "High": dht.string,
    "Low": dht.string,
    "Close": dht.string,
    "Volume": dht.string,
    "Status": dht.string,
    "TimestampStr": dht.string,
}

t = read_csv("data/stocks.csv", header=header)

# Cast string to double
t = t.update(["Close = Double.parseDouble(Close)"])

# Cast string to int
t = t.update(["Volume = Integer.parseInt(Volume)"])

# Multiple type fixes at once
t2 = read_csv("data/stocks.csv", header=header)
t2 = t2.update(
    [
        "Open = Double.parseDouble(Open)",
        "High = Double.parseDouble(High)",
        "Low = Double.parseDouble(Low)",
        "Close = Double.parseDouble(Close)",
        "Volume = Integer.parseInt(Volume)",
    ]
)
```

**Better approach — specify types at import time with the `header` parameter** to avoid post-import casting (see "Specifying Column Names and Types on Import" above).

### Parsing Date/Time Columns

CSV files often load date/time columns as strings. Parse them into proper Deephaven time types. Note: `read_csv` may auto-detect ISO-8601 timestamps as `Instant` — use the `header` parameter to force string type if you need manual parsing.

```python
import deephaven.dtypes as dht
from deephaven import read_csv

# Force TimestampStr and Date to string so we can demonstrate parsing
header = {
    "Date": dht.string,
    "Symbol": dht.string,
    "Open": dht.double,
    "High": dht.double,
    "Low": dht.double,
    "Close": dht.double,
    "Volume": dht.int64,
    "Status": dht.string,
    "TimestampStr": dht.string,
}

t = read_csv("data/stocks.csv", header=header)

# ISO-8601 timestamp string -> Instant
# TimestampStr contains values like "2024-06-01T10:30:00Z"
t = t.update(["Timestamp = parseInstant(TimestampStr)"])

# Date string -> Instant by appending time and timezone
# Date contains values like "2024-06-01"
t = t.update(
    [
        "DateAsInstant = parseInstant(Date + `T00:00:00 America/New_York`)",
    ]
)
```

For more on time parsing, see `references/time-operations.md`.

### Handling Null Values

CSV files may have empty fields that import as null, or you may need to replace values with null.

```python
from deephaven import read_csv

t = read_csv("data/stocks.csv")

# Check for nulls
t = t.update(["HasClose = !isNull(Close)"])

# Replace nulls with defaults
t = t.update(["SafeClose = isNull(Close) ? 0.0 : Close"])

# Create nulls conditionally (e.g., mark low-volume as null)
t = t.update(["AdjClose = Volume < 600000 ? NULL_DOUBLE : Close"])
```

### Filtering Rows After Import

```python
from deephaven import read_csv

t = read_csv("data/stocks.csv")

# Drop rows with null in a column
t_no_null = t.where("!isNull(Close)")

# Filter by string value
t_active = t.where("Status = `active`")

# Combine filters (AND logic)
t_filtered = t.where(["!isNull(Close)", "Close > 145", "Status = `active`"])
```

### Formatting Numeric Columns

```python
from deephaven import read_csv

t = read_csv("data/stocks.csv")

# Round a double column
t = t.update_view(["RoundedClose = Math.round(Close * 100) / 100.0"])

# Format as string with specific decimal places
t = t.update_view(["CloseStr = String.format(`%.2f`, Close)"])
```

---

## Complete Example: Import, Clean, and Export

```python
import deephaven.dtypes as dht
from deephaven import read_csv, write_csv

# Import with explicit types
header = {
    "Date": dht.string,
    "Symbol": dht.string,
    "Open": dht.double,
    "High": dht.double,
    "Low": dht.double,
    "Close": dht.double,
    "Volume": dht.int64,
    "Status": dht.string,
    "TimestampStr": dht.string,
}

raw = read_csv(
    "data/stocks.csv",
    header=header,
    ignore_empty_lines=True,
    trim=True,
)

# Clean and transform
cleaned = (
    raw.rename_columns(["Sym = Symbol"])
    .update(["Timestamp = parseInstant(TimestampStr)"])
    .where(["!isNull(Close)", "Volume > 0"])
    .drop_columns(["Date", "TimestampStr"])
    .update_view(["Range = High - Low", "MidPrice = (High + Low) / 2.0"])
)

# Export result
write_csv(cleaned, "/tmp/cleaned_prices.csv")
```

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Using `pd.read_csv` / pandas for import | Use `deephaven.read_csv` — keeps data in-engine |
| Not specifying types, then getting wrong inference | Use the `header` parameter with `dht` types |
| Parsing dates in Python instead of query strings | Use `parseInstant()`, `parseLong()`, etc. in `.update()` |
| Using `trim=True` when you need `ignore_surrounding_spaces=True` | `trim` is for quoted values; `ignore_surrounding_spaces` (default True) is for unquoted |
| Converting to pandas just to export | Use `write_csv` directly |
