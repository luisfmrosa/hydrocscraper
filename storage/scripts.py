"""
Finding and running the static SQL scripts on the quack server.

Layout (sql/):
  ddl/raw_views/<nnn>_<dataset code>.sql   raw view over the Raw files
  ddl/std_views/<nnn>_<table code>.sql     std view over the Std Parquet files
  ddl/lake/<table code>.sql                Lake table
  std/<source>/<dataset>.sql               Raw -> Std (one Raw file)
  lake/<source>/<table>_<mode>.sql         Std -> Lake (full | incremental)
"""

from __future__ import annotations

import logging
from pathlib import Path

from config import PROJECT_ROOT
from storage import duck

logger = logging.getLogger(__name__)

SQL_DIR = PROJECT_ROOT / "sql"


def view_script(kind: str, code: str) -> Path:
    """The one script sql/ddl/<kind>/*_<code>.sql (kind: raw_views | std_views)."""
    found = sorted((SQL_DIR / "ddl" / kind).glob(f"*_{code}.sql"))
    if len(found) != 1:
        raise FileNotFoundError(f"Expected one script sql/ddl/{kind}/*_{code}.sql, found {len(found)}")
    return found[0]


def require(paths: list[Path]) -> list[Path]:
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing SQL scripts: {', '.join(str(p) for p in missing)}")
    return paths


def run(path: Path, variables: dict[str, object] | None = None) -> list[tuple]:
    """Run every statement of *path* on the server; return the last result.

    *variables* are set first (SET VARIABLE), in the same request, so the
    script reads them with getvariable().
    """
    logger.info("Running %s", path.relative_to(PROJECT_ROOT))
    prelude = "".join(
        f"SET VARIABLE {name} = {duck.literal(value)};\n" for name, value in (variables or {}).items()
    )
    _, rows = duck.query(prelude + path.read_text(encoding="utf-8"))
    return rows
