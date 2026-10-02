"""
Client for the central DuckDB quack server.

The server (container hydroc-duckdb) attaches the Lake, Library, DWH and Hook
DuckLakes; this app holds no catalog credentials. The connection runs
`CONNECT 'quack:<host>:<port>'` (DuckDB 2.0), after which every statement
executes on the server and can use fully qualified names (hook.metadata.x).

Caveats (DuckDB 2.0.0-dev):
- Use execute(); the relational API (con.sql) binds names on the client.
- Bound parameters (?) are not forwarded to the server: render values with
  literal().
- Client and server must run the exact same DuckDB build.
- Dev builds need an AVX2 CPU.
- CONNECT uses HTTPS for any non-localhost host; the server only speaks plain
  HTTP, so set HYDROC_QUACK_DISABLE_SSL=true -> CONNECT '...' (DISABLE_SSL true).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from functools import lru_cache

import duckdb

from config import QUACK_DISABLE_SSL, QUACK_TOKEN, QUACK_URL

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _remote() -> duckdb.DuckDBPyConnection:
    if not QUACK_URL:
        raise RuntimeError("HYDROC_QUACK_URL is not set (see .env.example).")
    con = duckdb.connect()
    con.execute("INSTALL quack")
    con.execute("LOAD quack")
    con.execute(f"CREATE SECRET quack_server (TYPE quack, TOKEN {literal(QUACK_TOKEN)})")
    options = " (DISABLE_SSL true)" if QUACK_DISABLE_SSL else ""
    con.execute(f"CONNECT {literal(QUACK_URL)}{options}")
    return con


def query(sql: str) -> tuple[list[str], list[tuple]]:
    """Run *sql* on the quack server; return (column names, rows)."""
    logger.debug("quack: %s", sql)
    cur = _remote().execute(sql)
    if cur.description is None:
        return [], []
    return [d[0] for d in cur.description], cur.fetchall()


def literal(value) -> str:
    """Render a Python value as a SQL literal (parameters are not forwarded)."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, datetime):
        return f"TIMESTAMPTZ '{value.isoformat()}'"
    if isinstance(value, date):
        return f"DATE '{value.isoformat()}'"
    return "'" + str(value).replace("'", "''") + "'"
