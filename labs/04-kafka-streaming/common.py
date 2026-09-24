"""Shared settings for the lab scripts."""
from __future__ import annotations

import os
from pathlib import Path

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")
EVENTS_FILE = Path(__file__).resolve().parent.parent / "data" / "output" / "events.jsonl"

TOPIC_EVENTS = "page_views"             # input: one message per page view, keyed by customer_id
TOPIC_HOURLY = "page_views_hourly"      # output: page views per page per hour
TOPIC_DLQ = "page_views_dlq"            # messages that could not be processed, with the reason
