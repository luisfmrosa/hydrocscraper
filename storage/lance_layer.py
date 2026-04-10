"""
Layer 1 — Lance columnar storage via LanceDB.

Stores parsed ProductionRecord objects into a unified LanceDB table at:
    ./lake/production.lance/

LanceDB treats ./lake/ as the database directory. Each table is a
subdirectory in Lance format (e.g. lake/production.lance/).

Write modes
-----------
"overwrite"  — drop and recreate the entire table.
"append"     — add rows, then deduplicate on the composite primary key.
               Safe to run multiple times; keeps the latest scraped_at per key.

Primary key (uniqueness constraint enforced at write time):
    (source, country_iso3, field_name, well_id, period, commodity)
"""

from __future__ import annotations

import logging

import lancedb
import pyarrow as pa

from config import LAKE_ROOT
from models.production import ProductionRecord

logger = logging.getLogger(__name__)

TABLE_NAME = "production"

# Primary-key columns for deduplication
_PK_COLS = ["source", "country_iso3", "field_name", "well_id", "period", "commodity"]

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

PRODUCTION_SCHEMA = pa.schema(
    [
        pa.field("source",        pa.utf8()),
        pa.field("country_iso3",  pa.utf8()),
        pa.field("region",        pa.utf8()),
        pa.field("field_name",    pa.utf8()),
        pa.field("well_id",       pa.utf8()),
        pa.field("period",        pa.date32()),
        pa.field("commodity",     pa.utf8()),
        pa.field("value",         pa.float64()),
        pa.field("unit",          pa.utf8()),
        pa.field("scraped_at",    pa.timestamp("us", tz="UTC")),
        pa.field("source_file",   pa.utf8()),
    ]
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write(records: list[ProductionRecord], mode: str = "append") -> lancedb.table.Table:
    """Write *records* to the Lance table.

    mode="overwrite"  — recreate the table from scratch.
    mode="append"     — add rows then deduplicate on the primary key.
    """
    if not records:
        logger.warning("write() called with 0 records — nothing to do.")
        return _connect().open_table(TABLE_NAME)

    LAKE_ROOT.mkdir(parents=True, exist_ok=True)
    db = _connect()
    table = _to_arrow(records)

    table_exists = TABLE_NAME in db.list_tables()

    if mode == "overwrite" or not table_exists:
        logger.info(
            "Writing %d records to Lance table '%s' (overwrite).",
            len(records), TABLE_NAME,
        )
        tbl = db.create_table(TABLE_NAME, data=table, mode="overwrite")
    else:
        logger.info(
            "Appending %d records to Lance table '%s'.",
            len(records), TABLE_NAME,
        )
        tbl = db.open_table(TABLE_NAME)
        tbl.add(table)
        tbl = _deduplicate(tbl)

    row_count = tbl.count_rows()
    logger.info("Lance table '%s' now has %d rows.", TABLE_NAME, row_count)
    return tbl


def open_table() -> lancedb.table.Table:
    """Open the Lance table for reading."""
    db = _connect()
    if TABLE_NAME not in db.list_tables():
        raise FileNotFoundError(
            f"Lance table '{TABLE_NAME}' not found in {LAKE_ROOT}. "
            "Run --mode convert first."
        )
    return db.open_table(TABLE_NAME)


def dataset_info() -> dict:
    """Return a summary dict for CLI reporting."""
    tbl = open_table()
    schema = tbl.schema
    versions = tbl.list_versions()
    return {
        "path": str(LAKE_ROOT / f"{TABLE_NAME}.lance"),
        "rows": tbl.count_rows(),
        "versions": len(versions),
        "latest_version": versions[-1]["version"] if versions else None,
        "columns": [f.name for f in schema],
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _connect() -> lancedb.DBConnection:
    return lancedb.connect(str(LAKE_ROOT))


def _to_arrow(records: list[ProductionRecord]) -> pa.Table:
    """Convert ProductionRecord list to a PyArrow Table matching PRODUCTION_SCHEMA."""
    scraped_ts = [
        int(
            (r.scraped_at.replace(tzinfo=None) if r.scraped_at.tzinfo is None
             else r.scraped_at).timestamp() * 1_000_000
        )
        for r in records
    ]

    return pa.table(
        {
            "source":       [r.source       for r in records],
            "country_iso3": [r.country_iso3 for r in records],
            "region":       [r.region       for r in records],
            "field_name":   [r.field_name   for r in records],
            "well_id":      [r.well_id      for r in records],
            "period":       pa.array([r.period for r in records], type=pa.date32()),
            "commodity":    [r.commodity    for r in records],
            "value":        pa.array([r.value for r in records], type=pa.float64()),
            "unit":         [r.unit         for r in records],
            "scraped_at":   pa.array(scraped_ts, type=pa.timestamp("us", tz="UTC")),
            "source_file":  [r.source_file  for r in records],
        },
        schema=PRODUCTION_SCHEMA,
    )


def _deduplicate(tbl: lancedb.table.Table) -> lancedb.table.Table:
    """Remove duplicate rows, keeping the one with the latest scraped_at per PK."""
    import pyarrow.compute as pc

    logger.info("Deduplicating on primary key %s ...", _PK_COLS)
    full = tbl.to_arrow()
    original_rows = len(full)

    # Sort ascending so latest scraped_at ends up last
    full = full.sort_by([("scraped_at", "ascending")])

    # Build composite key column
    pk_arrays = [full.column(c).cast(pa.utf8()) for c in _PK_COLS]
    composite = pc.binary_join_element_wise(*pk_arrays, "||")
    full = full.append_column("_pk", composite)

    # Deduplicate via pandas (keep last = latest scraped_at)
    import pandas as pd
    df = full.to_pandas()
    df = df.drop_duplicates(subset=["_pk"], keep="last").drop(columns=["_pk"])
    deduped = pa.Table.from_pandas(df, schema=PRODUCTION_SCHEMA, preserve_index=False)

    removed = original_rows - len(deduped)
    if removed:
        logger.info("Removed %d duplicate rows.", removed)

    db = _connect()
    return db.create_table(TABLE_NAME, data=deduped, mode="overwrite")
