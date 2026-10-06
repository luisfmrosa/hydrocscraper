"""
Std step: Raw -> Std. All logic lives in static SQL; this only sends a
dataset's scripts to the quack server, in order:

  1. sql/ddl/raw_views/<nnn>_<source>_<dataset>.sql   raw view (CREATE OR REPLACE)
  2. sql/std/<source>/<dataset>.sql                   one Raw file -> Std Parquet

The std script reads one Raw file, given as the variable `raw_file` (its full
s3:// path), and writes one Parquet file per Std table with the Raw file's
year_month and timestamp.
"""

from __future__ import annotations

import logging
from pathlib import Path

from config import RAW_BUCKET
from storage import duck, scripts

logger = logging.getLogger(__name__)


def std_scripts(source: str, dataset: str) -> list[Path]:
    """The scripts of a dataset's Std step, in order."""
    return scripts.require([
        scripts.view_script("raw_views", f"{source}_{dataset}"),
        scripts.SQL_DIR / "std" / source / f"{dataset}.sql",
    ])


def raw_path(key: str) -> str:
    return f"s3://{RAW_BUCKET}/{key}"


def standardize(source: str, dataset: str, raw_key: str) -> None:
    """Convert one Raw file (its key in the Raw bucket) to Std."""
    raw_view, std_script = std_scripts(source, dataset)
    scripts.run(raw_view)
    scripts.run(std_script, {"raw_file": raw_path(raw_key)})
    logger.info("std: %s_%s <- %s", source, dataset, raw_key)


def raw_files(source: str, dataset: str) -> list[str]:
    """Every file the raw view reads (s3:// paths), oldest first."""
    _, rows = duck.query(
        "SELECT ___Raw_filename FROM hook.raw_views." + f"{source}_{dataset} "
        "GROUP BY ___Raw_filename ORDER BY min(___Raw_file_timestamp), ___Raw_filename"
    )
    return [r[0] for r in rows]


def standardize_all(source: str, dataset: str) -> int:
    """Rebuild Std from every Raw file, oldest first; return the file count."""
    raw_view, std_script = std_scripts(source, dataset)
    scripts.run(raw_view)
    files = raw_files(source, dataset)
    for path in files:
        scripts.run(std_script, {"raw_file": path})
    logger.info("std: %s_%s rebuilt from %d Raw files", source, dataset, len(files))
    return len(files)
