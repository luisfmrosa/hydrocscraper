"""
Std step: Raw -> Std. All logic lives in static SQL; this only sends a
dataset's scripts to the quack server, in order:

  1. sql/ddl/raw_views/<nnn>_<source>_<dataset>.sql   raw view (CREATE OR REPLACE)
  2. sql/std/<source>/<dataset>.sql                   one Raw file -> Std Parquet

The std script reads one Raw file, given as the variable `raw_file` (its full
s3:// path), and writes one Parquet file per Std table with the Raw file's
year_month and timestamp:

  s3://hydroc-std/<source>/<table>/year_month=<ym>/<source>_<table>_<ts>.parquet
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from config import RAW_BUCKET, STD_BUCKET
from storage import duck, scripts

logger = logging.getLogger(__name__)

_RAW_PATH = re.compile(r"/year_month=(?P<ym>[^/]+)/[^/]*_(?P<ts>\d{8}_\d{4})\.[^./]+$")


def std_scripts(source: str, dataset: str) -> list[Path]:
    """The scripts of a dataset's Std step, in order."""
    return scripts.require([
        scripts.view_script("raw_views", f"{source}_{dataset}"),
        scripts.SQL_DIR / "std" / source / f"{dataset}.sql",
    ])


def raw_path(key: str) -> str:
    return f"s3://{RAW_BUCKET}/{key}"


def std_path(source: str, table: str, raw_file: str) -> str:
    """Std file written from *raw_file* (s3:// path) for *table*."""
    m = _RAW_PATH.search(raw_file)
    if not m:
        raise ValueError(f"Not a Raw file path: {raw_file}")
    return (
        f"s3://{STD_BUCKET}/{source}/{table}/year_month={m['ym']}/"
        f"{source}_{table}_{m['ts']}.parquet"
    )


def standardize(source: str, dataset: str, raw_key: str) -> None:
    """Convert one Raw file (its key in the Raw bucket) to Std."""
    raw_view, std_script = std_scripts(source, dataset)
    scripts.run(raw_view)
    scripts.run(std_script, {"raw_file": raw_path(raw_key)})
    logger.info("std: %s_%s <- %s", source, dataset, raw_key)


def raw_files(source: str, dataset: str) -> list[str]:
    """Every file the raw view reads (s3:// paths), oldest first."""
    _, rows = duck.query(
        f"SELECT ___Raw_filename FROM hook.raw_views.{source}_{dataset} "
        "GROUP BY ___Raw_filename ORDER BY min(___Raw_file_timestamp), ___Raw_filename"
    )
    return [r[0] for r in rows]


def std_files(source: str, tables: list[str]) -> set[str]:
    """Std files that exist for *tables* (s3:// paths)."""
    found: set[str] = set()
    for table in tables:
        _, rows = duck.query(
            f"SELECT file FROM glob('s3://{STD_BUCKET}/{source}/{table}/*/*.parquet')"
        )
        found.update(r[0] for r in rows)
    return found


def standardize_all(source: str, dataset: str, tables: list[str], rebuild: bool = False) -> int:
    """Convert every Raw file that lacks a Std file for any of *tables*;
    with *rebuild*, convert every Raw file again. Oldest first; return the
    number of files converted.

    A file whose conversion failed (e.g. a schema change) has no Std file, so
    it is retried here once the Std script is fixed. Use *rebuild* after a
    change that alters the Std files themselves (types, columns, flattening).
    """
    raw_view, std_script = std_scripts(source, dataset)
    scripts.run(raw_view)
    files = raw_files(source, dataset)
    existing = set() if rebuild else std_files(source, tables)
    todo = [f for f in files if not all(std_path(source, t, f) in existing for t in tables)]
    for path in todo:
        scripts.run(std_script, {"raw_file": path})
    logger.info(
        "std: %s_%s: %d of %d Raw files converted%s",
        source, dataset, len(todo), len(files), " (rebuild)" if rebuild else "",
    )
    return len(todo)
