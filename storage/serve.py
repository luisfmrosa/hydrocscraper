"""
Serve step: Library -> Postgres serving database, for Metabase.

The DuckDB server attaches the Postgres database hydroc_serve as `serve`
(sql/ddl/10_attach.sql). Per Lake table, sql/serve/<source>/<table>.sql
replaces serve.latest.<code> and serve.latest.<code>_dev with copies of the
Library latest views. Metabase reads only these copies, through its built-in
Postgres driver: no BI tool can speak quack, and the DuckDB build behind
the Library is a 2.0 dev build no Metabase DuckDB driver embeds.

storage/lake.py runs it after every Lake load; `python main.py --mode serve`
runs it alone (e.g. to fill a new serving database from the current Library).
"""

from __future__ import annotations

import logging
from pathlib import Path

from storage import scripts

logger = logging.getLogger(__name__)


def serve_script(source: str, table: str) -> Path | None:
    """The table's serve script, or None if it isn't served."""
    path = scripts.SQL_DIR / "serve" / source / f"{table}.sql"
    return path if path.exists() else None


def refresh(source: str, table: str) -> bool:
    """Replace the table's serving copies; return False if it isn't served."""
    path = serve_script(source, table)
    if path is None:
        return False
    scripts.run(path)
    logger.info("serve.latest.%s_%s refreshed", source, table)
    return True
