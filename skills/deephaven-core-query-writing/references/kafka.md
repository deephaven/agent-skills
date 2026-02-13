# Deephaven Kafka Integration Reference

## Overview

Deephaven integrates with Apache Kafka to consume topics as real-time tables and produce table changes back to Kafka streams.

## Basic Consumption

```python
# incomplete
from deephaven.stream.kafka import consumer as kc
from deephaven import dtypes as dht

result = kc.consume(
    {"bootstrap.servers": "kafka:9092"},
    "topic.name",
    key_spec=kc.KeyValueSpec.IGNORE,
    value_spec=kc.simple_spec("Value", dht.string),
    table_type=kc.TableType.append(),
)
```

## Table Types

| Type | Behavior | Use Case |
|------|----------|----------|
| `TableType.append()` | Keeps all rows (unbounded memory) | Complete history |
| `TableType.blink()` | Keeps only current cycle rows (default) | Stateful aggregations |
| `TableType.ring(N)` | Keeps last N rows | Bounded memory, recent data |

```python
# incomplete
from deephaven.stream.kafka import consumer as kc
from deephaven import dtypes as dht

# Append-only (all history)
kc.consume({"bootstrap.servers": "kafka:9092"}, "topic", key_spec=kc.KeyValueSpec.IGNORE, value_spec=kc.simple_spec("Value", dht.string), table_type=kc.TableType.append())

# Blink (current cycle only, default)
kc.consume({"bootstrap.servers": "kafka:9092"}, "topic", key_spec=kc.KeyValueSpec.IGNORE, value_spec=kc.simple_spec("Value", dht.string), table_type=kc.TableType.blink())

# Ring (last 1000 rows)
kc.consume({"bootstrap.servers": "kafka:9092"}, "topic", key_spec=kc.KeyValueSpec.IGNORE, value_spec=kc.simple_spec("Value", dht.string), table_type=kc.TableType.ring(1000))
```

## Standard Kafka Columns

Every consumed table includes these columns (can be disabled):

| Column | Type | Description |
|--------|------|-------------|
| `KafkaPartition` | int | Message partition |
| `KafkaOffset` | long | Position in partition |
| `KafkaTimestamp` | Instant | Event timestamp |

Disable by setting property to empty string:
```python
# incomplete
properties = {
    "bootstrap.servers": "kafka:9092",
    "deephaven.partition.column.name": "",  # Disable KafkaPartition
    "deephaven.offset.column.name": "",     # Disable KafkaOffset
    "deephaven.timestamp.column.name": "",  # Disable KafkaTimestamp
}
```

## Key and Value Specs

### Ignore Key/Value
```python
from deephaven.stream.kafka import consumer as kc

key_spec = kc.KeyValueSpec.IGNORE
value_spec = kc.KeyValueSpec.IGNORE
```

### Simple Types
```python
from deephaven import dtypes as dht
from deephaven.stream.kafka import consumer as kc

# String value
value_spec = kc.simple_spec("ColumnName", dht.string)

# Other types
value_spec = kc.simple_spec("IntCol", dht.int32)
value_spec = kc.simple_spec("LongCol", dht.int64)
value_spec = kc.simple_spec("DoubleCol", dht.double)
value_spec = kc.simple_spec("BoolCol", dht.bool_)
```

### JSON Format
```python
from deephaven import dtypes as dht
from deephaven.stream.kafka import consumer as kc

value_spec = kc.json_spec(
    col_defs={
        "Symbol": dht.string,
        "Price": dht.double,
        "Qty": dht.int64,
        "Timestamp": dht.Instant,
    },
    # Optional: map JSON field names to column names
    mapping={
        "sym": "Symbol",
        "px": "Price",
        "qty": "Qty",
        "ts": "Timestamp",
    }
)
```

### Avro Format (Schema Registry)
```python
# incomplete
from deephaven.stream.kafka import consumer as kc

value_spec = kc.avro_spec(
    schema_name="record.name",
    schema_version="1",  # or "latest"
    # Optional: select specific fields
    # field_to_col_mapping={"field1": "Col1"}
)

# Requires schema registry URL in properties
properties = {
    "bootstrap.servers": "kafka:9092",
    "schema.registry.url": "http://schema-registry:8081",
}
```

### Protobuf Format (Schema Registry)
```python
# incomplete
from deephaven.stream.kafka import consumer as kc

value_spec = kc.protobuf_spec(
    schema_name="message.name",
    schema_version=1,
    # Optional: specify message name within schema
    # schema_message_name="InnerMessage"
)
```

### Raw Bytes
```python
# incomplete
from deephaven.stream.kafka import consumer as kc
from deephaven import dtypes as dht

value_spec = kc.raw_spec("RawBytes", dht.byte_array)
```

## Complete JSON Example

```python
# incomplete
from deephaven.stream.kafka import consumer as kc
from deephaven import dtypes as dht

trades = kc.consume(
    {"bootstrap.servers": "kafka:9092"},
    "trades",
    key_spec=kc.simple_spec("Symbol", dht.string),
    value_spec=kc.json_spec({
        "Price": dht.double,
        "Quantity": dht.int64,
        "Timestamp": dht.Instant,
        "Side": dht.string,
    }),
    table_type=kc.TableType.append(),
)
```

## Complete Avro Example

```python
# incomplete
from deephaven.stream.kafka import consumer as kc

quotes = kc.consume(
    {
        "bootstrap.servers": "kafka:9092",
        "schema.registry.url": "http://schema-registry:8081",
    },
    "quotes",
    key_spec=kc.KeyValueSpec.IGNORE,
    value_spec=kc.avro_spec("quote.record", schema_version="latest"),
    table_type=kc.TableType.blink(),
)
```

## Partitioned Table Consumption

Consume into partitioned table (by Kafka partition):

```python
# incomplete
from deephaven.stream.kafka import consumer as kc
from deephaven import dtypes as dht

partitioned = kc.consume_to_partitioned_table(
    {"bootstrap.servers": "kafka:9092"},
    "topic.name",
    key_spec=kc.KeyValueSpec.IGNORE,
    value_spec=kc.simple_spec("Value", dht.string),
    table_type=kc.TableType.append(),
)

# Access merged table
merged = partitioned.merge()
```

## Offset Control

```python
# incomplete
from deephaven.stream.kafka import consumer as kc
from deephaven import dtypes as dht

# Start from beginning
kc.consume({"bootstrap.servers": "kafka:9092"}, "topic", key_spec=kc.KeyValueSpec.IGNORE, value_spec=kc.simple_spec("V", dht.string), offsets=kc.ALL_PARTITIONS_SEEK_TO_BEGINNING)

# Start from end (new messages only)
kc.consume({"bootstrap.servers": "kafka:9092"}, "topic", key_spec=kc.KeyValueSpec.IGNORE, value_spec=kc.simple_spec("V", dht.string), offsets=kc.ALL_PARTITIONS_SEEK_TO_END)

# Specific offsets per partition
kc.consume({"bootstrap.servers": "kafka:9092"}, "topic", key_spec=kc.KeyValueSpec.IGNORE, value_spec=kc.simple_spec("V", dht.string), offsets={0: 100, 1: 200})
```

## Producing to Kafka

```python
# incomplete
from deephaven.stream.kafka import producer as pk
from deephaven import time_table

# Create a source table
source = time_table("PT1s").update(["Value = ii"])

# Produce to Kafka
pk.produce(
    source,
    {"bootstrap.servers": "kafka:9092"},
    "output.topic",
    key_spec=pk.KeyValueSpec.IGNORE,
    value_spec=pk.simple_spec("Value"),
)
```

### JSON Producer
```python
# incomplete
from deephaven.stream.kafka import producer as pk
from deephaven import time_table

source = time_table("PT1s").update(["Col1 = ii", "Col2 = ii * 2", "Col3 = ii * 3"])

pk.produce(
    source,
    {"bootstrap.servers": "kafka:9092"},
    "output.topic",
    key_spec=pk.KeyValueSpec.IGNORE,
    value_spec=pk.json_spec(
        col_defs=["Col1", "Col2", "Col3"],  # Columns to include
        timestamp_field="Timestamp",  # Optional: embed timestamp
    ),
)
```

### Avro Producer
```python
# incomplete
from deephaven.stream.kafka import producer as pk
from deephaven import time_table

source = time_table("PT1s").update(["Symbol = `AAPL`", "Price = 150.0 + ii * 0.1", "Qty = ii"])

pk.produce(
    source,
    {
        "bootstrap.servers": "kafka:9092",
        "schema.registry.url": "http://schema-registry:8081",
    },
    "output.topic",
    key_spec=pk.KeyValueSpec.IGNORE,
    value_spec=pk.avro_spec(
        schema_name="output.record",
        col_defs=["Symbol", "Price", "Qty"],
    ),
)
```

## Common Patterns

**Kafka trades to OHLCV:**
```python
# incomplete
from deephaven.stream.kafka import consumer as kc
from deephaven import dtypes as dht, agg

trades = kc.consume(
    {"bootstrap.servers": "kafka:9092"},
    "trades",
    key_spec=kc.simple_spec("Symbol", dht.string),
    value_spec=kc.json_spec({
        "Price": dht.double,
        "Qty": dht.int64,
        "Timestamp": dht.Instant,
    }),
    table_type=kc.TableType.blink(),
)

ohlcv = trades.update([
    "TimeBucket = lowerBin(Timestamp, 'PT1m')"
]).agg_by([
    agg.first(cols=["Open = Price"]),
    agg.max_(cols=["High = Price"]),
    agg.min_(cols=["Low = Price"]),
    agg.last(cols=["Close = Price"]),
    agg.sum_(cols=["Volume = Qty"]),
], by=["Symbol", "TimeBucket"])
```

**Join Kafka streams:**
```python
# incomplete
from deephaven.stream.kafka import consumer as kc
from deephaven import dtypes as dht
from deephaven.stream import blink_to_append_only

# Trades and quotes from separate topics
trades = kc.consume(
    {"bootstrap.servers": "kafka:9092"},
    "trades",
    key_spec=kc.simple_spec("Symbol", dht.string),
    value_spec=kc.json_spec({"Price": dht.double, "Timestamp": dht.Instant}),
    table_type=kc.TableType.blink(),
)
quotes = kc.consume(
    {"bootstrap.servers": "kafka:9092"},
    "quotes",
    key_spec=kc.simple_spec("Symbol", dht.string),
    value_spec=kc.json_spec({"Bid": dht.double, "Ask": dht.double, "Timestamp": dht.Instant}),
    table_type=kc.TableType.blink(),
)

# Convert blink to append-only for joins
trades_append = blink_to_append_only(trades)
quotes_append = blink_to_append_only(quotes)

# As-of join trades with quotes
enriched = trades_append.aj(quotes_append, on=["Symbol", "Timestamp"])
```

## Consumer Properties Reference

```python
# incomplete
properties = {
    "bootstrap.servers": "kafka:9092",
    "schema.registry.url": "http://registry:8081",  # For Avro/Protobuf
    "group.id": "my-consumer-group",
    "auto.offset.reset": "earliest",  # or "latest"
    # Security
    "security.protocol": "SASL_SSL",
    "sasl.mechanism": "PLAIN",
    "sasl.jaas.config": "...",
    # Deephaven-specific
    "deephaven.partition.column.name": "KafkaPartition",
    "deephaven.offset.column.name": "KafkaOffset",
    "deephaven.timestamp.column.name": "KafkaTimestamp",
}
```

## Documentation URLs

- Kafka streaming: https://deephaven.io/core/docs/how-to-guides/data-import-export/kafka-stream.md
- Consumer API: https://deephaven.io/core/docs/reference/data-import-export/Kafka/consume.md
- Producer API: https://deephaven.io/core/docs/reference/data-import-export/Kafka/produce.md
