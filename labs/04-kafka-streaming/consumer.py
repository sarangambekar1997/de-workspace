"""A plain consumer: print messages with their partition and offset, committing manually.

Usage:
    python consumer.py --group demo                      # read from the last committed offset
    python consumer.py --group demo --max 20             # stop after 20 messages
    python consumer.py --group demo --crash-after 50     # exit without committing, to see redelivery
"""
from __future__ import annotations

import argparse
import os

from confluent_kafka import Consumer, KafkaException

from common import BOOTSTRAP, TOPIC_EVENTS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--topic", default=TOPIC_EVENTS)
    parser.add_argument("--group", required=True)
    parser.add_argument("--max", type=int, default=0, help="stop after this many messages (0 = run until Ctrl+C)")
    parser.add_argument("--crash-after", type=int, default=0, help="exit abruptly after N messages")
    parser.add_argument("--quiet", action="store_true", help="print a summary only")
    args = parser.parse_args()

    consumer = Consumer({
        "bootstrap.servers": BOOTSTRAP,
        "group.id": args.group,
        "auto.offset.reset": "earliest",       # a new group starts at the beginning of the topic
        "enable.auto.commit": False,           # commit only after processing: at-least-once
        "session.timeout.ms": 10_000,          # how soon a crashed member is removed from the group
    })
    consumer.subscribe([args.topic], on_assign=lambda c, parts: print(
        "Assigned partitions:", sorted(p.partition for p in parts)))

    seen = 0
    try:
        while not args.max or seen < args.max:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                print("Error:", msg.error())
                continue
            seen += 1
            if not args.quiet:
                print(f"p{msg.partition()} offset {msg.offset():>6}  key={msg.key().decode():>5}  {msg.value()[:70].decode()}")
            if args.crash_after and seen == args.crash_after:
                print(f"Crashing after {seen} messages without committing", flush=True)
                os._exit(1)                       # no commit, no clean leave from the group
            if seen % 100 == 0:
                consumer.commit(asynchronous=False)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            consumer.commit(asynchronous=False)
        except KafkaException:                    # nothing new to commit
            pass
        consumer.close()                          # leave the group so partitions rebalance at once
        print(f"Consumed {seen:,} messages")


if __name__ == "__main__":
    main()
