# Deephaven Iceberg Integration Reference

## Overview

Apache Iceberg is a high-performance table format for large analytic tables. Deephaven integrates with Iceberg catalogs to read and write data.

## Supported Catalog Types

- REST
- AWS Glue
- JDBC
- Hive
- Hadoop
- Nessie

Some catalog types require additional classpath dependencies.

## Catalog Adapters

### Generic REST Adapter
```python
# incomplete
from deephaven.experimental import iceberg

adapter = iceberg.adapter(
    name="my-catalog",
    properties={
        "type": "rest",
        "uri": "http://iceberg-rest:8181",
        "warehouse": "s3://my-bucket/warehouse",
        "s3.access-key-id": "my-access-key",
        "s3.secret-access-key": "my-secret-key",
        "s3.endpoint": "http://minio:9000",
        "s3.region": "us-east-1",
        "io-impl": "org.apache.iceberg.aws.s3.S3FileIO",
    }
)
```

### S3-Backed REST Catalog
```python
# incomplete
from deephaven.experimental import iceberg

adapter = iceberg.adapter_s3_rest(
    name="s3-catalog",
    catalog_uri="http://iceberg-rest:8181",
    warehouse_location="s3://bucket/warehouse",
    region_name="us-east-1",
    access_key_id="my-access-key",
    secret_access_key="my-secret-key",
    end_point_override="http://minio:9000",  # Optional, for MinIO/LocalStack
)
```

### AWS Glue Catalog
```python
# incomplete
from deephaven.experimental import iceberg

adapter = iceberg.adapter_aws_glue(
    name="glue-catalog",
    region_name="us-east-1",
    access_key_id="my-access-key",
    secret_access_key="my-secret-key",
)
```

## Exploring Catalogs

```python
# incomplete
from deephaven.experimental import iceberg

adapter = iceberg.adapter(name="my-catalog", properties={"type": "rest", "uri": "http://iceberg-rest:8181"})

# List namespaces
namespaces = adapter.namespaces()

# List tables in namespace
tables = adapter.tables(namespace="my_namespace")

# Get table info
table_adapter = adapter.load_table("namespace.table_name")
```

## Reading Tables

### Basic Read
```python
# incomplete
from deephaven.experimental import iceberg

adapter = iceberg.adapter(name="my-catalog", properties={"type": "rest", "uri": "http://iceberg-rest:8181"})

# Load table adapter
table_adapter = adapter.load_table("namespace.table_name")

# Read as static table
t = table_adapter.table(update_mode=iceberg.IcebergUpdateMode.static())
```

### Update Modes

```python
# incomplete
from deephaven.experimental import iceberg

adapter = iceberg.adapter(name="my-catalog", properties={"type": "rest", "uri": "http://iceberg-rest:8181"})
table_adapter = adapter.load_table("namespace.table_name")

# Static (no refresh, snapshot at read time)
t = table_adapter.table(update_mode=iceberg.IcebergUpdateMode.static())

# Manual refresh (call refresh() to update)
t = table_adapter.table(update_mode=iceberg.IcebergUpdateMode.manual_refresh())
table_adapter.refresh()  # Refresh when needed

# Auto refresh (default: 60 seconds)
t = table_adapter.table(update_mode=iceberg.IcebergUpdateMode.auto_refresh())

# Auto refresh with custom interval (30 seconds)
t = table_adapter.table(
    update_mode=iceberg.IcebergUpdateMode.auto_refresh(auto_refresh_ms=30000)
)
```

### Read Specific Snapshot
```python
from deephaven.experimental import iceberg

instructions = iceberg.IcebergReadInstructions(snapshot_id=6738371110677246500)
```

### Column Renames
```python
from deephaven.experimental import iceberg

instructions = iceberg.IcebergReadInstructions(
    column_renames={
        "source_column": "TargetColumn",
        "another_source": "AnotherTarget",
    }
)
```

### Custom Table Definition
```python
from deephaven import dtypes as dht
from deephaven.experimental import iceberg

instructions = iceberg.IcebergReadInstructions(
    table_definition={
        "ID": dht.int64,
        "Name": dht.string,
        "Value": dht.double,
        "Timestamp": dht.Instant,
    }
)
```

### Schema-Based Field Mapping (by Field ID)
```python
from deephaven import dtypes as dht
from deephaven.experimental import iceberg

table_def = {
    "Symbol": dht.string,
    "Price": dht.double,
    "Quantity": dht.int64,
}

# Map column names to Iceberg field IDs
field_mapping = {
    "Symbol": 1,  # Field ID 1
    "Price": 2,  # Field ID 2
    "Quantity": 3,  # Field ID 3
}

resolver = iceberg.UnboundResolver(
    table_definition=table_def, column_instructions=field_mapping
)
```

## Writing Tables

### Create New Iceberg Table
```python
# incomplete
from deephaven import empty_table
from deephaven.experimental import iceberg

# Create source data
source = empty_table(100).update([
    "ID = ii",
    "Value = randomDouble(0, 100)",
    "Category = (ii % 3 == 0) ? `A` : (ii % 3 == 1) ? `B` : `C`"
])

# Create Iceberg table from definition
adapter = iceberg.adapter(name="my-catalog", properties={"type": "rest", "uri": "http://iceberg-rest:8181"})
table_adapter = adapter.create_table(
    table_identifier="namespace.new_table",
    table_definition=source.definition
)

# Write data
writer_options = iceberg.TableParquetWriterOptions(
    table_definition=source.definition
)
writer = table_adapter.table_writer(writer_options=writer_options)
writer.append(iceberg.IcebergWriteInstructions([source]))
```

### Append to Existing Table
```python
# incomplete
from deephaven import empty_table
from deephaven.experimental import iceberg

source1 = empty_table(50).update(["ID = ii", "Value = randomDouble(0, 100)"])
source2 = empty_table(50).update(["ID = ii + 50", "Value = randomDouble(0, 100)"])

adapter = iceberg.adapter(name="my-catalog", properties={"type": "rest", "uri": "http://iceberg-rest:8181"})

# Load existing table
table_adapter = adapter.load_table("namespace.existing_table")

# Create writer
writer_options = iceberg.TableParquetWriterOptions(
    table_definition=source1.definition
)
writer = table_adapter.table_writer(writer_options=writer_options)

# Append data (multiple tables must have same schema)
writer.append(iceberg.IcebergWriteInstructions([source1, source2]))
```

**Note:** Deephaven currently only supports appending data to Iceberg tables (no updates or deletes).

### Writing Partitioned Tables
```python
from deephaven import dtypes as dht
from deephaven import empty_table
from deephaven.column import ColumnType, col_def

# Define schema with partitioning column
partitioned_def = [
    col_def("Year", dht.int32, column_type=ColumnType.PARTITIONING),
    col_def("ID", dht.int64),
    col_def("Value", dht.double),
]

# Note: Partitioning columns CANNOT be in the data, only in partition path
source_2024 = empty_table(50).update(["ID = ii", "Value = randomDouble(0, 100)"])
source_2025 = empty_table(50).update(["ID = ii + 50", "Value = randomDouble(0, 100)"])
```

## S3 Configuration

For S3-compatible storage:
```python
from deephaven.experimental import s3

# Configure S3 instructions
s3_instructions = s3.S3Instructions(
    region_name="us-east-1",
    access_key_id="my-access-key",
    secret_access_key="my-secret-key",
    endpoint_override="http://minio:9000",  # For MinIO/LocalStack
)
```

## Common Patterns

**Read from Iceberg, process, write back:**
```python
# incomplete
from deephaven.experimental import iceberg
from deephaven import agg

# Read source data
adapter = iceberg.adapter_s3_rest(
    name="s3-catalog",
    catalog_uri="http://iceberg-rest:8181",
    warehouse_location="s3://bucket/warehouse",
    region_name="us-east-1",
    access_key_id="my-access-key",
    secret_access_key="my-secret-key",
)
source_adapter = adapter.load_table("namespace.raw_data")
raw = source_adapter.table(update_mode=iceberg.IcebergUpdateMode.static())

# Process
aggregated = raw.agg_by([
    agg.sum_(cols=["TotalValue = Value"]),
    agg.count_(col="Count"),
], by=["Category"])

# Write results
result_adapter = adapter.create_table(
    table_identifier="namespace.aggregated_data",
    table_definition=aggregated.definition
)
writer_options = iceberg.TableParquetWriterOptions(
    table_definition=aggregated.definition
)
writer = result_adapter.table_writer(writer_options=writer_options)
writer.append(iceberg.IcebergWriteInstructions([aggregated]))
```

**Auto-refreshing dashboard from Iceberg:**
```python
# incomplete
from deephaven.experimental import iceberg

adapter = iceberg.adapter_s3_rest(
    name="s3-catalog",
    catalog_uri="http://iceberg-rest:8181",
    warehouse_location="s3://bucket/warehouse",
    region_name="us-east-1",
    access_key_id="my-access-key",
    secret_access_key="my-secret-key",
)
table_adapter = adapter.load_table("namespace.events")

# Table auto-updates every 30 seconds
live_data = table_adapter.table(
    update_mode=iceberg.IcebergUpdateMode.auto_refresh(auto_refresh_ms=30000)
)

# Build dashboard on auto-refreshing table
latest = live_data.last_by("EventType")
```

## Key Constraints

1. **Append-only writes** - No updates or deletes supported yet
2. **Same schema required** - Multiple tables written together must have identical definitions
3. **Partition columns not in data** - When writing partitioned tables, partition column values come from partition path, not data
4. **Experimental module** - API may change (`deephaven.experimental.iceberg`)

## Documentation URLs

- Iceberg overview: https://deephaven.io/core/docs/how-to-guides/data-import-export/iceberg.md
- adapter: https://deephaven.io/core/docs/reference/iceberg/adapter.md
- adapter_s3_rest: https://deephaven.io/core/docs/reference/iceberg/adapter-s3-rest.md
- adapter_aws_glue: https://deephaven.io/core/docs/reference/iceberg/adapter-aws-glue.md
- IcebergReadInstructions: https://deephaven.io/core/docs/reference/iceberg/iceberg-read-instructions.md
- IcebergWriteInstructions: https://deephaven.io/core/docs/reference/iceberg/iceberg-write-instructions.md
- IcebergUpdateMode: https://deephaven.io/core/docs/reference/iceberg/iceberg-update-mode.md
