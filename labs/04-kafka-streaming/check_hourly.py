"""Compare the processor's hourly counts with the true counts computed from the source file.

Usage:
    python check_hourly.py
"""
from __future__ import annotations

import json
import uuid
from collections import Counter

from confluent_kafka import Consumer

from common import BOOTSTRAP, EVENTS_FILE, TOPIC_HOURLY


def expected_counts() -> Counter[tuple[str, str]]:
    """Views per (hour, page) from the file, each event counted once."""
    counts: Counter[tuple[str, str]] = Counter()
    seen = set()
    for line in EVENTS_FILE.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if e["event_id"] in seen:
            continue
        seen.add(e["event_id"])
        hour = e["event_ts"][:13] + ":00:00+00:00"
        counts[(hour, e["page"])] += 1
    return counts


def actual_counts() -> Counter[tuple[str, str]]:
    """Sum of everything published to the output topic (a fresh group reads it all)."""
    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": f"check-{uuid.uuid4()}",
                         "auto.offset.reset": "earliest", "enable.auto.commit": False})
    consumer.subscribe([TOPIC_HOURLY])
    counts: Counter[tuple[str, str]] = Counter()
    empty = 0
    while empty < 5:
        batch = consumer.consume(num_messages=1000, timeout=1.0)
        empty = 0 if batch else empty + 1
        for msg in batch:
            if not msg.error():
                v = json.loads(msg.value())
                counts[(v["window_start"], v["page"])] += v["views"]
    consumer.close()
    return counts


def main() -> None:
    expected, actual = expected_counts(), actual_counts()
    keys = expected.keys() | actual.keys()
    exact = sum(expected[k] == actual[k] for k in keys)
    under = sum(expected[k] - actual[k] for k in keys if actual[k] < expected[k])
    over = sum(actual[k] - expected[k] for k in keys if actual[k] > expected[k])
    print(f"Windows (hour x page): {len(keys):,}   exact: {exact:,}   wrong: {len(keys) - exact:,}")
    print(f"Events expected: {sum(expected.values()):,}   counted: {sum(actual.values()):,}")
    print(f"  missing (dropped as too late): {under:,}")
    print(f"  extra (double-counted):        {over:,}")


if __name__ == "__main__":
    main()
