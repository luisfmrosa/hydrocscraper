"""Run the server DDL against in-memory stand-ins for the four DuckLakes."""

from pathlib import Path

import duckdb
import pytest

from storage.watermark import read_watermark, write_watermark

DDL = Path(__file__).resolve().parents[1] / "sql" / "ddl"
SCRIPTS = ["20_library.sql", "30_dwh.sql", "40_hook.sql", "41_hook_watermark.sql"]


def _apply_ddl(con):
    for name in SCRIPTS:
        con.execute((DDL / name).read_text(encoding="utf-8"))


@pytest.fixture
def con():
    con = duckdb.connect()
    for layer in ("lake", "library", "dwh", "hook"):
        con.execute(f"ATTACH ':memory:' AS {layer}")
    _apply_ddl(con)
    return con


def _executor(con):
    """Stand-in for storage.duck.query on a local connection."""
    def execute(sql):
        cur = con.execute(sql)
        if cur.description is None:
            return [], []
        return [d[0] for d in cur.description], cur.fetchall()
    return execute


def test_ddl_is_idempotent(con):
    _apply_ddl(con)
    schemas = con.sql(
        "SELECT database_name || '.' || schema_name FROM duckdb_schemas() "
        "WHERE schema_name <> 'main' AND database_name IN ('library','dwh','hook') ORDER BY 1"
    ).fetchall()
    assert [s[0] for s in schemas] == [
        "dwh.supply", "hook.metadata", "hook.raw_views", "hook.std_views", "library.frame", "library.latest",
    ]


def test_watermark_roundtrip(con):
    ex = _executor(con)
    assert read_watermark("npd", "ds", execute=ex) == {}

    write_watermark("npd", "ds", execute=ex, load_mode="full",
                    last_period_fetched="2026-07", status="ok", raw_file="k1")
    write_watermark("npd", "ds", execute=ex, load_mode="incremental",
                    last_period_fetched="2026-08", status="ok", raw_file="k'2")

    assert con.sql("SELECT count(*) FROM hook.metadata.watermark").fetchone()[0] == 2
    wm = read_watermark("npd", "ds", execute=ex)
    assert wm["last_period_fetched"] == "2026-08"
    assert wm["raw_file"] == "k'2"


def test_watermark_rejects_unknown_fields(con):
    with pytest.raises(ValueError):
        write_watermark("npd", "ds", execute=_executor(con), bogus=1)
