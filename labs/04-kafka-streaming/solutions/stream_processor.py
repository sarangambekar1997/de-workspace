"""Stream processor: hourly page views per page, by event time, with a watermark.

    page_views ──► validate ──► deduplicate ──► 1-hour tumbling windows ──► page_views_hourly
                      │                                │
                      └── invalid ──► page_views_dlq ◄──┘ too late (window already emitted)

A window is emitted once the watermark passes its end. Kafka orders messages only within a
partition, so the watermark is tracked per partition and the slowest partition decides:
    watermark = min(latest event time per partition) - allowed lateness
Events that arrive for an already-emitted window go to the dead-letter topic.
Offsets are committed only after results are produced: at-least-once delivery.

Usage:
    python stream_processor.py                    # allowed lateness 2 hours
    python stream_processor.py --lateness-hours 36 --group page-counts-36h
    python stream_processor.py --crash-after-batches 20      # simulate a failure mid-stream
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from confluent_kafka import Consumer, Producer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))     # run from the lab folder or solutions/
from common import BOOTSTRAP, TOPIC_DLQ, TOPIC_EVENTS, TOPIC_HOURLY  # noqa: E402

WINDOW = timedelta(hours=1)
EARLIEST = datetime.min.replace(tzinfo=timezone.utc)
REQUIRED = ("event_id", "customer_id", "page", "event_ts")


# ── Exercise functions ───────────────────────────────────────────────────────
def validate(raw: bytes) -> tuple[dict | None, str | None]:
    """Return (event, None) for a valid message, or (None, reason) for an invalid one."""
    try:
        event = json.loads(raw)
    except ValueError:
        return None, "invalid_json"
    missing = [f for f in REQUIRED if event.get(f) is None]
    if missing:
        return None, f"missing_fields:{','.join(missing)}"
    try:
        event["event_ts"] = datetime.fromisoformat(event["event_ts"].replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None, "invalid_event_ts"
    return event, None


def window_start(ts: datetime) -> datetime:
    """The start of the 1-hour tumbling window containing ts."""
    return ts.replace(minute=0, second=0, microsecond=0)


def compute_watermark(latest_by_partition: dict[int, datetime], assigned: set[int],
                      lateness: timedelta) -> datetime:
    """Event time up to which all windows are complete.

    Each partition is in order on its own, but partitions are read at different speeds, so the
    slowest partition limits progress. Until every assigned partition has delivered an event,
    nothing is known about the missing ones and no window may close.
    """
    if not assigned or not assigned <= latest_by_partition.keys():
        return EARLIEST
    return min(latest_by_partition[p] for p in assigned) - lateness


# ── Processor ────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--group", default="page-counts")
    parser.add_argument("--lateness-hours", type=float, default=2)
    parser.add_argument("--idle-seconds", type=float, default=10, help="stop after this long without messages")
    parser.add_argument("--crash-after-batches", type=int, default=0,
                        help="exit after writing results but before committing offsets")
    args = parser.parse_args()
    lateness = timedelta(hours=args.lateness_hours)

    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": args.group,
                         "auto.offset.reset": "earliest", "enable.auto.commit": False,
                         "session.timeout.ms": 10_000})   # how soon a crashed member is removed
    producer = Producer({"bootstrap.servers": BOOTSTRAP, "enable.idempotence": True, "acks": "all"})
    assigned: set[int] = set()
    consumer.subscribe([TOPIC_EVENTS],
                       on_assign=lambda c, parts: assigned.update(p.partition for p in parts),
                       on_revoke=lambda c, parts: assigned.difference_update(p.partition for p in parts))

    open_windows: dict[datetime, Counter[str]] = defaultdict(Counter)   # window start -> page -> count
    emitted: set[datetime] = set()
    seen_ids: set[int] = set()        # in memory: lost on restart (a state store would persist it)
    latest_by_partition: dict[int, datetime] = {}
    watermark = EARLIEST
    stats: Counter[str] = Counter()

    def to_dlq(raw: bytes, reason: str) -> None:
        producer.produce(TOPIC_DLQ, raw, headers={"reason": reason})
        stats[reason.split(":")[0]] += 1

    def emit(start: datetime) -> None:
        for page, n in sorted(open_windows.pop(start).items()):
            key = f"{start.isoformat()}|{page}"
            value = {"window_start": start.isoformat(), "window_end": (start + WINDOW).isoformat(),
                     "page": page, "views": n}
            producer.produce(TOPIC_HOURLY, json.dumps(value).encode(), key=key.encode())
        emitted.add(start)
        stats["windows_emitted"] += 1

    idle = 0.0
    while idle < args.idle_seconds:
        batch = consumer.consume(num_messages=500, timeout=1.0)
        if not batch:
            idle += 1.0 if assigned else 0.0       # waiting to join the group is not idleness
            continue
        idle = 0.0
        for msg in batch:
            if msg.error():
                continue
            stats["messages"] += 1
            event, error = validate(msg.value())
            if error:
                to_dlq(msg.value(), error)
                continue
            if event["event_id"] in seen_ids:
                stats["duplicates"] += 1
                continue
            seen_ids.add(event["event_id"])
            start = window_start(event["event_ts"])
            if start in emitted or start + WINDOW <= watermark:
                to_dlq(msg.value(), "too_late")
                continue
            open_windows[start][event["page"]] += 1
            p = msg.partition()
            latest_by_partition[p] = max(latest_by_partition.get(p, EARLIEST), event["event_ts"])
        watermark = compute_watermark(latest_by_partition, assigned, lateness)
        for start in sorted(s for s in open_windows if s + WINDOW <= watermark):
            emit(start)
        producer.flush(10)
        stats["batches"] += 1
        if stats["batches"] == args.crash_after_batches:
            print(f"Crashing after batch {stats['batches']}: results written, offsets not committed", flush=True)
            os._exit(1)
        consumer.commit(asynchronous=False)       # after results are safely written

    for start in sorted(open_windows):             # end of input: emit whatever is still open
        emit(start)
    producer.flush(10)
    consumer.close()

    print(f"Allowed lateness: {args.lateness_hours:g} hours   Watermark: {watermark:%Y-%m-%d %H:%M}")
    for name in ["messages", "duplicates", "invalid_json", "missing_fields", "invalid_event_ts",
                 "too_late", "windows_emitted"]:
        print(f"  {name:<17} {stats[name]:>7,}")


if __name__ == "__main__":
    main()
