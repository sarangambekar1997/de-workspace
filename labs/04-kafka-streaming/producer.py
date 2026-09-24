"""Replay the generated page-view events into Kafka, in the order they were received.

Late events (received hours after they happened) are sent late, duplicates are sent twice,
and --bad-rate adds malformed messages, so consumers see what a real stream looks like.

Usage:
    python producer.py                         # all events, as fast as possible
    python producer.py --rate 50 --limit 500   # 50 messages per second, stop after 500
    python producer.py --bad-rate 0.01         # also send ~1% malformed messages
"""
from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter

from confluent_kafka import KafkaError, Message, Producer

from common import BOOTSTRAP, EVENTS_FILE, TOPIC_EVENTS

BAD_MESSAGES = [
    b"{not valid json",
    b'{"event_id": null, "page": "/cart"}',
    b'{"event_id": 1, "customer_id": 5, "event_type": "page_view", "page": "/", "event_ts": "yesterday"}',
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topic", default=TOPIC_EVENTS)
    parser.add_argument("--rate", type=float, default=0, help="messages per second (0 = no limit)")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many messages (0 = all)")
    parser.add_argument("--bad-rate", type=float, default=0, help="share of extra malformed messages")
    args = parser.parse_args()

    producer = Producer({
        "bootstrap.servers": BOOTSTRAP,
        "enable.idempotence": True,     # retries never create duplicates or reorder a partition
        "acks": "all",
        "linger.ms": 20,                # wait briefly to send fuller batches
        "compression.type": "lz4",
    })
    per_partition: Counter[int] = Counter()
    failed = 0

    def on_delivery(err: KafkaError | None, msg: Message) -> None:
        nonlocal failed
        if err:
            failed += 1
        else:
            per_partition[msg.partition()] += 1

    events = [json.loads(line) for line in EVENTS_FILE.read_text(encoding="utf-8").splitlines()]
    events.sort(key=lambda e: e["received_ts"])             # arrival order, not event order
    if args.limit:
        events = events[: args.limit]

    rng = random.Random(7)
    sent = 0
    for event in events:
        if args.bad_rate and rng.random() < args.bad_rate:
            producer.produce(args.topic, rng.choice(BAD_MESSAGES), key=b"bad", on_delivery=on_delivery)
            sent += 1
        producer.produce(args.topic, json.dumps(event).encode(), key=str(event["customer_id"]).encode(),
                         on_delivery=on_delivery)
        sent += 1
        producer.poll(0)                                    # serve delivery callbacks
        if args.rate:
            time.sleep(1 / args.rate)

    producer.flush(30)
    print(f"Sent {sent:,} messages to '{args.topic}' ({failed} failed)")
    for partition, n in sorted(per_partition.items()):
        print(f"  partition {partition}: {n:,}")


if __name__ == "__main__":
    main()
