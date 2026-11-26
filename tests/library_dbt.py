"""Build Library views with the real dbt project (transform/) against a test's
local DuckDB, the way the app does in production: the test connection serves
quack on localhost and dbt connects to it through storage/dbt_quack.py, so the
models run on the same in-memory lake/library/hook databases as the test.

The models read hook.metadata.hooks and .datasets, so the connection also gets
the static Hook metadata from data/static/ (sql/ddl/45_hook_static.sql).
"""

from __future__ import annotations

import os
import secrets
import socket
from pathlib import Path

from storage import library

ROOT = Path(__file__).resolve().parents[1]
HOOK_STATIC = ROOT / "sql" / "ddl" / "45_hook_static.sql"
NAMES = ("sources", "datasets", "business_domains", "business_concepts", "hooks")
SERVED: list = []  # connections serving quack, stopped by tests/conftest.py


def hook_static(con) -> None:
    """Build hook.metadata.* from data/static/ (hook.metadata must exist);
    the copies the script writes to s3://hydroc-raw/metadata/ go to the test
    bucket."""
    for name in NAMES:
        (Path(con.bucket) / "metadata" / name).mkdir(parents=True, exist_ok=True)
    sql = (
        HOOK_STATIC.read_text(encoding="utf-8")
        .replace("/opt/duckdb/static/", (ROOT / "data" / "static").as_posix() + "/")
        .replace("s3://hydroc-raw/", con.bucket)
    )
    con.execute(sql)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(con) -> None:
    """Serve quack from the test connection (once) and point the dbt profile
    at it."""
    if getattr(con, "quack_url", None) is None:
        token = secrets.token_hex(8)
        url = f"quack:localhost:{_free_port()}"
        con.execute("INSTALL quack")
        con.execute("LOAD quack")
        con.execute(f"CALL quack_serve('{url}', token = '{token}')")
        con.quack_url, con.quack_token = url, token
        SERVED.append(con)
    os.environ["HYDROC_QUACK_URL"] = con.quack_url
    os.environ["HYDROC_QUACK_TOKEN"] = con.quack_token
    os.environ["HYDROC_QUACK_DISABLE_SSL"] = "false"


def build(con, source: str, table: str) -> None:
    """Run the table's Library models on the test connection."""
    serve(con)
    assert library.build(source, table), f"{source}_{table} has no Library models"


def library_models(table: str, source: str = "no_sodir") -> list[str]:
    """The four Library model names of a hooked Lake table."""
    code = f"{source}_{table}"
    return sorted([f"frame_{code}", f"frame_{code}_dev", f"latest_{code}", f"latest_{code}_dev"])


def stop_all() -> None:
    """Close dbt's client connection, then stop every quack server and close
    its database: a server left listening can hang the interpreter's exit."""
    if not SERVED:
        return
    library.close()
    while SERVED:
        con = SERVED.pop()
        con.execute(f"FROM quack_stop('{con.quack_url}')")
        con.db.close()
