"""
Lake step: Std -> Lake. All logic lives in static SQL; this only sends a
table's scripts to the quack server, in order:

  1. sql/ddl/std_views/<nnn>_<code>.sql      std view (CREATE OR REPLACE)
  2. sql/ddl/lake/<code>.sql                 Lake table (IF NOT EXISTS)
  3. sql/lake/<source>/<table>_<mode>.sql    load: full | incremental
  4. sql/ddl/library/<code>[_dev].sql        Library frame and latest views,
                                             if any (CREATE OR REPLACE)

where <code> is <source>_<table> and <table> is the dataset or one of its
flattened sub-tables (data/static/datasets.csv). Steps 1-2 and 4 also run at
server start; repeating them here means a new table needs no server restart
(the Library views can only be created once the Lake table exists).
"""

from __future__ import annotations

import logging
from pathlib import Path

from storage import scripts

logger = logging.getLogger(__name__)

MODES = ("full", "incremental")


def lake_scripts(source: str, table: str, mode: str) -> list[Path]:
    """The scripts to run for a table's Lake load, in order."""
    if mode not in MODES:
        raise ValueError(f"Unknown Lake load mode '{mode}' (expected one of {MODES})")
    code = f"{source}_{table}"
    return scripts.require([
        scripts.view_script("std_views", code),
        scripts.SQL_DIR / "ddl" / "lake" / f"{code}.sql",
        scripts.SQL_DIR / "lake" / source / f"{table}_{mode}.sql",
    ])


def library_scripts(source: str, table: str) -> list[Path]:
    """The table's Library view scripts that exist (production, development)."""
    code = f"{source}_{table}"
    folder = scripts.SQL_DIR / "ddl" / "library"
    return [p for p in (folder / f"{code}.sql", folder / f"{code}_dev.sql") if p.exists()]


def load(source: str, table: str, mode: str) -> int:
    """Run a table's Lake load, then (re)create its Library views; return
    the number of rows inserted."""
    rows: list[tuple] = []
    for path in lake_scripts(source, table, mode):
        rows = scripts.run(path)
    inserted = rows[0][0] if rows else 0
    logger.info("lake.%s.%s: %s load inserted %d rows", source, table, mode, inserted)
    for path in library_scripts(source, table):
        scripts.run(path)
    return inserted
