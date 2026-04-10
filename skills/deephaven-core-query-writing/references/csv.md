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

**Warning — column name sanitization:** `read_csv` legalizes column headers automatically. Spaces and dashes become underscores; all other illegal characters (`.`, `/`, `#`, `@`, `%`, `(`, `)`, etc.) are removed; `$` and `_` are kept; a leading digit gets a `column_` prefix; duplicates get a numeric suffix (`_2`). Examples: `Annual Income (k$)` → `Annual_Income_k$`, `fixed acidity` → `fixed_acidity`, `State/UnionTerritory` → `StateUnionTerritory`, `1st Place` → `column_1st_Place`.

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

**Non-numeric sentinels (e.g. `-`, `N/A`, blanks):** If a column uses placeholder values like `-` or empty strings for missing data, type inference as `double`/`int` will fail at the first non-numeric row. **Fix: import the column as `dht.string`, then clean and cast.**

```python
from pathlib import Path

import deephaven.dtypes as dht
from deephaven import read_csv

Path("/tmp/sentinel.csv").write_text("Name,Value\nA,10\nB,-\nC,30\n")

# Import Value as string to avoid parse failure on "-"
t = read_csv("/tmp/sentinel.csv", header={"Name": dht.string, "Value": dht.string})

# Clean sentinel values, then cast
t = t.update(
    [
        "Value = Value.equals(`-`) || Value.trim().isEmpty()"
        + " ? NULL_DOUBLE : Double.parseDouble(Value)"
    ]
)
```

Rare trailing comma / phantom column: A header row ending with `,` creates an unnamed extra column that causes `ArrayIndexOutOfBoundsException`. Neither `allow_missing_columns` nor `ignore_excess_columns` fixes this. **Fix: preprocess the file to strip trailing commas.**

### Reading Compressed Files

`read_csv` natively supports compressed files. No decompression step needed.

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

Null values are written as empty fields in the CSV output.

---

## After Import

Use standard table operations to clean imported data. Rename columns with `rename_columns` or `view` aliases. Filter with `.where()`. Handle nulls with `isNull()` and ternary expressions. Cast strings with `Double.parseDouble()` / `Integer.parseInt()` in `.update()` — guard nullable columns: `isNull(Col) ? null : Integer.parseInt(Col)`. Parse date strings with `parseInstant()` — see `references/time-operations.md`. Prefer specifying types via `header` at import time over post-import casting.

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Using `pd.read_csv` / pandas for import | Use `deephaven.read_csv` — keeps data in-engine |
| Not specifying types, then getting wrong inference | Use the `header` parameter with `dht` types |
| Parsing dates in Python instead of query strings | Use `parseInstant()`, `parseLong()`, etc. in `.update()` |
| Using `trim=True` when you need `ignore_surrounding_spaces=True` | `trim` is for quoted values; `ignore_surrounding_spaces` (default True) is for unquoted |
| Using original CSV header names after import | `read_csv` sanitizes names (spaces/special chars → `_`). Check `t.meta_table` for actual names |
| Specifying `dht.double` for columns with `-` or blank sentinels | Import as `dht.string`, clean sentinels, then cast to numeric |
| CSV header has trailing comma → phantom column | Preprocess file to strip trailing commas before `read_csv` |
