"""
Incremental-load state, stored in hook.metadata.watermark (see
sql/ddl/41_hook_watermark.sql). The table is append-only: each step of a
load inserts a row, and hook.metadata.watermark_latest exposes the most
recent one per (source, dataset).

`status` follows a Raw file through the pipeline: 'raw' (stored in Raw),
'std' (converted to Std), 'lake' (loaded into the Lake). Rows written before
the Std layer existed have 'ok', which counts as done.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from storage import duck

logger = logging.getLogger(__name__)

TABLE = "hook.metadata.watermark"
LATEST_VIEW = "hook.metadata.watermark_latest"

FIELDS = ("load_mode", "last_period_fetched", "status", "raw_file")
STATUSES = ("raw", "std", "lake")
DONE = ("lake", "ok")

Executor = Callable[[str], tuple[list[str], list[tuple]]]


def read_watermark(source: str, dataset: str, execute: Executor = duck.query) -> dict:
    """Return the latest watermark row for (source, dataset), or {}."""
    columns, rows = execute(
        f"SELECT * FROM {LATEST_VIEW} "
        f"WHERE source = {duck.literal(source)} AND dataset = {duck.literal(dataset)}"
    )
    return dict(zip(columns, rows[0])) if rows else {}


def write_watermark(
    source: str, dataset: str, execute: Executor = duck.query, **fields
) -> None:
    """Append a watermark row. Unknown field names raise ValueError."""
    unknown = set(fields) - set(FIELDS)
    if unknown:
        raise ValueError(f"Unknown watermark fields: {sorted(unknown)}")

    row = {
        "source": source,
        "dataset": dataset,
        **{f: fields.get(f) for f in FIELDS},
        "updated_at": datetime.now(timezone.utc),
    }
    cols = ", ".join(row)
    values = ", ".join(duck.literal(v) for v in row.values())
    execute(f"INSERT INTO {TABLE} ({cols}) VALUES ({values})")
    logger.debug("Watermark written for %s/%s: %s", source, dataset, row)
