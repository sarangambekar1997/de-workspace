# Apache Kafka Reference
> From first message to production-grade event streaming pipelines.

---

## Table of Contents

**Basics**
- [What is Kafka?](#what-is-kafka)
- [Core Concepts](#core-concepts)
- [Topics & Partitions](#topics--partitions)
- [Producers](#producers)
- [Consumers & Consumer Groups](#consumers--consumer-groups)

**Intermediate**
- [Offsets & Delivery Guarantees](#offsets--delivery-guarantees)
- [Consumer Group Rebalancing](#consumer-group-rebalancing)
- [Kafka CLI](#kafka-cli)
- [Schema Registry & Avro](#schema-registry--avro)
- [Kafka with Python](#kafka-with-python)

**Advanced**
- [Kafka Connect](#kafka-connect)
- [Kafka Streams](#kafka-streams)
- [Retention & Compaction](#retention--compaction)
- [Performance Tuning](#performance-tuning)
- [Kafka in DE Pipelines](#kafka-in-de-pipelines)

---

## What is Kafka?

Kafka is a distributed, fault-tolerant, high-throughput **event log**. It stores a durable, ordered sequence of events that any number of consumers can read at their own pace — independently and repeatedly.

Think of it as a **commit log for events**: producers append events to the end; consumers read from wherever they left off. Nothing is deleted by a consumer reading — events persist until a retention policy removes them.

```
Producers                Topics                     Consumers
─────────                ──────                     ─────────
App Server  ──write──→  [user-events topic]  ──read──→  Analytics Pipeline
Payment API ──write──→  [orders topic]       ──read──→  Fraud Detection
IoT Device  ──write──→  [sensors topic]      ──read──→  Alerting Service
                                             ──read──→  Data Lake Sink
```

**Kafka vs a message queue (RabbitMQ/SQS):**

| | Kafka | Message Queue |
|--|-------|--------------|
| Message deleted after consume? | No — retained by time/size | Yes |
| Multiple consumers same message? | Yes | No (one consumer per message) |
| Replay old messages? | Yes | No |
| Ordering guarantee | Per-partition | Varies |
| Throughput | Very high (millions/sec) | Moderate |

---

## Core Concepts

| Concept | Definition |
|---------|-----------|
| **Event / Message / Record** | An immutable unit of data: key, value, timestamp, headers |
| **Topic** | A named, ordered, durable log. Like a table, but for events |
| **Partition** | A topic split into parallel ordered sublogs; unit of parallelism |
| **Offset** | Sequential integer identifying a message's position in a partition |
| **Producer** | Application that writes events to a topic |
| **Consumer** | Application that reads events from a topic |
| **Consumer Group** | Set of consumers sharing the work of reading a topic |
| **Broker** | A single Kafka server that stores partitions |
| **Cluster** | Multiple brokers working together |
| **Zookeeper / KRaft** | Metadata coordination (Zookeeper being replaced by KRaft in Kafka 3.x) |
| **Replication Factor** | How many brokers hold a copy of each partition |
| **Leader / Follower** | One broker leads each partition; followers replicate it |
| **ISR** | In-Sync Replicas — followers caught up to the leader |

---

## Topics & Partitions

```
Topic: order-events  (3 partitions, replication factor 2)

Partition 0: [0: order_placed] [1: order_shipped] [2: order_delivered]
Partition 1: [0: order_placed] [1: order_cancelled]
Partition 2: [0: order_placed] [1: order_shipped]
              ↑ offset 0        ↑ offset 1

Each partition is an independent, ordered log.
Ordering is guaranteed WITHIN a partition, not across partitions.
```

### Partition key

The producer assigns each message a **key**. Kafka hashes the key to determine which partition the message lands in. Messages with the same key always go to the same partition — guaranteeing ordering for that key.

```python
# Messages for the same order_id → same partition → guaranteed order
producer.send("order-events", key=b"order_123", value=b"...")
producer.send("order-events", key=b"order_123", value=b"...")  # same partition

# No key → round-robin across partitions
producer.send("order-events", value=b"...")
```

### How many partitions?

```
More partitions → more parallelism → higher throughput
But: more partitions → more overhead, longer leader election on failure

Rule of thumb:
  - Start with partitions = max expected consumers in one group
  - Or: target throughput / throughput per partition
  - Common range: 6–100 for most use cases
  - You can add partitions later but cannot reduce them
```

---

## Producers

```python
from kafka import KafkaProducer
import json

producer = KafkaProducer(
    bootstrap_servers=["kafka:9092"],
    key_serializer=str.encode,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    acks="all",             # wait for all ISR replicas to confirm write
    retries=5,
    linger_ms=10,           # batch messages for up to 10ms before sending
    batch_size=16384,        # max batch size in bytes
)

# Send a message
producer.send(
    topic="order-events",
    key="order_123",
    value={"order_id": "order_123", "status": "placed", "amount": 99.50},
)

# Flush — wait for all pending messages to be sent
producer.flush()
producer.close()

# With callback — handle success/failure
def on_send_success(metadata):
    print(f"Sent to {metadata.topic}:{metadata.partition}@{metadata.offset}")

def on_send_error(exc):
    print(f"Send failed: {exc}")

producer.send("order-events", key="order_456", value={...}) \
    .add_callback(on_send_success) \
    .add_errback(on_send_error)
```

### Producer acknowledgment modes (`acks`)

| acks | Durability | Throughput | Risk |
|------|-----------|-----------|------|
| `0` | Fire-and-forget | Highest | Data loss on broker failure |
| `1` | Leader acknowledged | High | Loss if leader fails before replication |
| `all` / `-1` | All ISR replicas acknowledged | Lower | Safest — no loss if ISR count ≥ 2 |

---

## Consumers & Consumer Groups

```python
from kafka import KafkaConsumer
import json

consumer = KafkaConsumer(
    "order-events",
    bootstrap_servers=["kafka:9092"],
    group_id="analytics-pipeline",        # consumer group
    auto_offset_reset="earliest",         # start from beginning if no committed offset
    enable_auto_commit=True,              # auto-commit offsets every interval
    auto_commit_interval_ms=5000,
    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    key_deserializer=lambda k: k.decode("utf-8") if k else None,
)

# Continuous poll loop
for message in consumer:
    print(f"Topic: {message.topic}, Partition: {message.partition}, "
          f"Offset: {message.offset}, Key: {message.key}")
    process(message.value)

consumer.close()

# Manual offset commit — more control over exactly-once semantics
consumer = KafkaConsumer(
    "order-events",
    group_id="analytics-pipeline",
    enable_auto_commit=False,     # disable auto-commit
    ...
)

for message in consumer:
    try:
        process(message.value)
        consumer.commit()         # commit only after successful processing
    except Exception as e:
        logger.error("Processing failed: %s", e)
        # don't commit — message will be redelivered on restart
```

### How consumer groups work

```
Topic: order-events (4 partitions)

Consumer Group A (analytics):          Consumer Group B (alerts):
  Consumer A1 → Partition 0             Consumer B1 → Partition 0, 1, 2, 3
  Consumer A2 → Partition 1             (only 1 consumer — gets all partitions)
  Consumer A3 → Partition 2, 3
  (3 consumers share 4 partitions)

Each group reads ALL messages independently.
Within a group, each partition is assigned to exactly ONE consumer.
Adding more consumers than partitions → some consumers are idle.
```

---

## Offsets & Delivery Guarantees

### Offset management

```python
# Where to start consuming when no committed offset exists:
auto_offset_reset="earliest"   # from the oldest available message
auto_offset_reset="latest"     # from new messages only (skip historical)

# Seek to a specific offset manually
from kafka import TopicPartition

tp = TopicPartition("order-events", 0)
consumer.assign([tp])
consumer.seek(tp, 1000)        # start from offset 1000

# Seek to beginning / end
consumer.seek_to_beginning(tp)
consumer.seek_to_end(tp)

# Get current committed offset for a group
consumer.committed(tp)
```

### Delivery guarantees

| Guarantee | How | Risk |
|-----------|-----|------|
| **At-most-once** | Commit offset before processing | Message lost if consumer crashes after commit but before processing |
| **At-least-once** | Commit offset after processing | Duplicate if consumer crashes after processing but before commit |
| **Exactly-once** | Transactional producer + consumer, or idempotent consumer | Complex; requires Kafka transactions or deduplication logic |

> **At-least-once + idempotent consumer** is the standard production pattern. Design your consumer to safely reprocess the same message (deduplicate by event ID).

---

## Consumer Group Rebalancing

When consumers join or leave a group, Kafka **rebalances** — reassigns partitions to the current set of consumers. During rebalancing, all consumers in the group pause.

```python
from kafka import ConsumerRebalanceListener

class RebalanceHandler(ConsumerRebalanceListener):
    def on_partitions_revoked(self, revoked):
        print(f"Partitions revoked: {revoked}")
        consumer.commit()    # commit current offsets before losing partitions

    def on_partitions_assigned(self, assigned):
        print(f"Partitions assigned: {assigned}")

consumer.subscribe(["order-events"], listener=RebalanceHandler())
```

### Reduce rebalance frequency

```python
KafkaConsumer(
    ...
    session_timeout_ms=30000,          # consumer declared dead after 30s of silence
    heartbeat_interval_ms=10000,       # send heartbeat every 10s
    max_poll_interval_ms=300000,       # max time between poll() calls (5 min)
    max_poll_records=500,              # limit records per poll to stay within interval
)
```

---

## Kafka CLI

```bash
# Topics
kafka-topics.sh --bootstrap-server kafka:9092 \
    --create --topic order-events \
    --partitions 6 \
    --replication-factor 2

kafka-topics.sh --bootstrap-server kafka:9092 --list
kafka-topics.sh --bootstrap-server kafka:9092 --describe --topic order-events
kafka-topics.sh --bootstrap-server kafka:9092 --delete --topic order-events

# Change partition count (can only increase)
kafka-topics.sh --bootstrap-server kafka:9092 \
    --alter --topic order-events --partitions 12

# Produce messages (interactive)
kafka-console-producer.sh --bootstrap-server kafka:9092 --topic order-events
# type JSON and press Enter for each message

# Consume messages
kafka-console-consumer.sh --bootstrap-server kafka:9092 \
    --topic order-events \
    --from-beginning \
    --group my-test-group

# Consumer group info
kafka-consumer-groups.sh --bootstrap-server kafka:9092 --list
kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
    --describe --group analytics-pipeline
# Shows: partition, current-offset, log-end-offset, LAG

# Reset offsets (useful for reprocessing)
kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
    --group analytics-pipeline \
    --topic order-events \
    --reset-offsets --to-earliest \
    --execute
```

---

## Schema Registry & Avro

Schema Registry is a separate service (from Confluent) that stores and enforces message schemas. Every message is serialized with its schema ID — consumers always know the schema.

```python
from confluent_kafka import Producer, Consumer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer, AvroDeserializer
from confluent_kafka.serialization import SerializationContext, MessageField

# Define Avro schema
order_schema_str = """
{
  "type": "record",
  "name": "Order",
  "namespace": "com.mycompany.events",
  "fields": [
    {"name": "order_id",    "type": "string"},
    {"name": "customer_id", "type": "int"},
    {"name": "amount",      "type": "double"},
    {"name": "status",      "type": "string"},
    {"name": "created_at",  "type": "long", "logicalType": "timestamp-millis"}
  ]
}
"""

schema_registry = SchemaRegistryClient({"url": "http://schema-registry:8081"})
serializer   = AvroSerializer(schema_registry, order_schema_str)
deserializer = AvroDeserializer(schema_registry)

# Produce with Avro
producer = Producer({"bootstrap.servers": "kafka:9092"})

order = {"order_id": "abc123", "customer_id": 42, "amount": 99.50,
         "status": "placed", "created_at": 1710000000000}

producer.produce(
    topic="order-events",
    value=serializer(order, SerializationContext("order-events", MessageField.VALUE)),
)
producer.flush()
```

### Schema evolution rules

| Change | Backward compatible? | Forward compatible? |
|--------|---------------------|---------------------|
| Add field with default | ✅ | ✅ |
| Remove field with default | ✅ | ✅ |
| Add field without default | ❌ | ✅ |
| Remove required field | ✅ | ❌ |
| Change field type | ❌ | ❌ |

---

## Kafka with Python

### confluent-kafka (recommended — wraps librdkafka, high performance)

```python
from confluent_kafka import Producer, Consumer, KafkaError
import json

# Producer
producer = Producer({
    "bootstrap.servers": "kafka:9092",
    "acks": "all",
    "enable.idempotence": True,    # exactly-once producer semantics
})

def delivery_report(err, msg):
    if err:
        print(f"Delivery failed: {err}")
    else:
        print(f"Delivered to {msg.topic()}[{msg.partition()}]@{msg.offset()}")

producer.produce(
    "order-events",
    key="order_123",
    value=json.dumps({"order_id": "order_123", "amount": 50.0}),
    callback=delivery_report,
)
producer.poll(0)   # trigger delivery callbacks
producer.flush()

# Consumer
consumer = Consumer({
    "bootstrap.servers": "kafka:9092",
    "group.id":           "analytics-pipeline",
    "auto.offset.reset":  "earliest",
    "enable.auto.commit": False,
})

consumer.subscribe(["order-events"])

try:
    while True:
        msg = consumer.poll(timeout=1.0)
        if msg is None:
            continue
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                continue    # end of partition — not an error
            raise KafkaError(msg.error())

        data = json.loads(msg.value().decode("utf-8"))
        process(data)
        consumer.commit(asynchronous=False)   # synchronous commit after processing

finally:
    consumer.close()
```

---

## Kafka Connect

Kafka Connect moves data between Kafka and external systems without writing producers/consumers. Configured via JSON, not code.

```json
// Source connector — pull from Postgres into Kafka (via Debezium)
{
    "name": "postgres-source-orders",
    "config": {
        "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
        "database.hostname": "postgres",
        "database.port": "5432",
        "database.user": "debezium",
        "database.password": "secret",
        "database.dbname": "myapp",
        "table.include.list": "public.orders,public.customers",
        "topic.prefix": "cdc",
        "plugin.name": "pgoutput",
        "publication.name": "debezium_pub",
        "slot.name": "debezium_slot"
    }
}
// Creates topics: cdc.public.orders, cdc.public.customers
// Each INSERT/UPDATE/DELETE on those tables → event in Kafka
```

```json
// Sink connector — write from Kafka to S3
{
    "name": "s3-sink-orders",
    "config": {
        "connector.class": "io.confluent.connect.s3.S3SinkConnector",
        "tasks.max": "4",
        "topics": "cdc.public.orders",
        "s3.region": "us-east-1",
        "s3.bucket.name": "my-data-lake",
        "s3.part.size": "67108864",
        "flush.size": "1000",
        "storage.class": "io.confluent.connect.s3.storage.S3Storage",
        "format.class": "io.confluent.connect.s3.format.parquet.ParquetFormat",
        "partitioner.class": "io.confluent.connect.storage.partitioner.TimeBasedPartitioner",
        "path.format": "'year'=YYYY/'month'=MM/'day'=dd/'hour'=HH",
        "locale": "en_US",
        "timezone": "UTC"
    }
}
```

---

## Retention & Compaction

### Time-based retention (default)

```bash
# Keep messages for 7 days (default: 168 hours)
kafka-configs.sh --bootstrap-server kafka:9092 \
    --entity-type topics --entity-name order-events \
    --alter --add-config retention.ms=604800000

# Keep up to 50 GB per partition
kafka-configs.sh --bootstrap-server kafka:9092 \
    --entity-type topics --entity-name order-events \
    --alter --add-config retention.bytes=53687091200
```

### Log compaction

Instead of time-based deletion, keep only the **latest message per key**. Perfect for CDC — the topic acts like a changelog, always reflecting current state.

```bash
kafka-configs.sh --bootstrap-server kafka:9092 \
    --entity-type topics --entity-name customer-state \
    --alter --add-config cleanup.policy=compact

# Tombstone — delete a key by sending null value
producer.send("customer-state", key=b"customer_42", value=None)
```

---

## Performance Tuning

### Producer

```python
Producer({
    "linger.ms":       20,       # wait up to 20ms to batch messages
    "batch.size":      65536,    # 64KB batch size
    "compression.type": "snappy", # compress batches
    "buffer.memory":   67108864, # 64MB producer buffer
})
```

### Consumer

```python
Consumer({
    "fetch.min.bytes":          1024,    # wait for at least 1KB before returning
    "fetch.max.wait.ms":        500,     # wait up to 500ms for fetch.min.bytes
    "max.partition.fetch.bytes": 1048576, # 1MB max per partition per fetch
    "max.poll.records":         500,     # max records per poll()
})
```

### Broker

```
num.network.threads=8         # threads for handling network I/O
num.io.threads=8              # threads for disk I/O
socket.send.buffer.bytes=102400
socket.receive.buffer.bytes=102400
log.segment.bytes=1073741824  # 1GB per log segment
log.retention.check.interval.ms=300000
```

---

## Kafka in DE Pipelines

### Common patterns

```
Pattern 1: CDC → Data Lake
  OLTP DB → Debezium (Kafka Connect) → Kafka → S3 Sink (Kafka Connect) → Parquet files → dbt

Pattern 2: Event Stream → Real-time Aggregation
  App Events → Kafka → Flink/Spark Structured Streaming → Aggregated tables → BI

Pattern 3: Fan-out
  Single event topic → multiple consumer groups:
    → Group 1: Analytics pipeline (Snowflake load)
    → Group 2: Alerting service
    → Group 3: ML feature store

Pattern 4: Kafka as Buffer
  High-volume API events → Kafka (absorbs spikes) → Consumer (steady write rate to DB)
```

### Consumer lag monitoring

Consumer lag = log-end-offset − current-offset = how far behind a consumer is.

```bash
# Check lag for all groups
kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
    --describe --all-groups

# Output:
# GROUP               TOPIC          PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
# analytics-pipeline  order-events   0          1500            1502            2
# analytics-pipeline  order-events   1          980             985             5
```

High lag = consumer is falling behind producers. Investigate:
1. Consumer processing too slow → optimize or scale out consumers
2. Producer spike → temporary; will catch up
3. Consumer crashed → restart it

### Dead Letter Queue (DLQ)

```python
dlq_producer = Producer({"bootstrap.servers": "kafka:9092"})

for msg in consumer:
    try:
        process(msg.value)
        consumer.commit()
    except Exception as e:
        # Send failed message to DLQ for later inspection/reprocessing
        dlq_producer.produce(
            "order-events-dlq",
            key=msg.key(),
            value=msg.value(),
            headers={"error": str(e), "original_topic": msg.topic()}
        )
        dlq_producer.flush()
        consumer.commit()   # commit past the bad message
```
