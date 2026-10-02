"""
Storage of the known-sources catalog in the Raw layer.

Each discovery run writes a timestamped snapshot:
  s3://hydroc-raw/metadata/known_sources/known_sources_<YYYYMMDD_HHmm>.json

Every record carries an md5_digest over its catalog fields (utils/hashing.py),
used downstream to detect changes between snapshots.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from storage import s3
from storage.raw import timestamp
from utils.hashing import row_md5

logger = logging.getLogger(__name__)

PREFIX = "metadata/known_sources/"

# Catalog fields, in digest order
FIELDS = (
    "id",
    "name",
    "url",
    "format",
    "granularity",
    "periodicity",
    "scope",
    "countries",
)


def snapshot_key(ts: datetime | None = None) -> str:
    return f"{PREFIX}known_sources_{timestamp(ts)}.json"


def with_digest(records: list[dict]) -> list[dict]:
    """Return copies of *records* with a fresh md5_digest."""
    out = []
    for rec in records:
        rec = {k: v for k, v in rec.items() if k != "md5_digest"}
        rec["md5_digest"] = row_md5(rec, FIELDS)
        out.append(rec)
    return out


def latest_known_sources() -> list[dict]:
    """Return the records of the most recent snapshot, or [] if none exists."""
    keys = [k for k in s3.list_keys(PREFIX) if k.endswith(".json")]
    if not keys:
        return []
    logger.info("Loading %s", keys[-1])
    return json.loads(s3.get_bytes(keys[-1]))


def save_known_sources(records: list[dict]) -> str:
    """Write a new timestamped snapshot and return its key."""
    key = snapshot_key()
    body = json.dumps(with_digest(records), indent=2, ensure_ascii=False)
    s3.put_bytes(body.encode("utf-8"), key)
    return key
