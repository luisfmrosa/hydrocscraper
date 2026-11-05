"""The serve scripts (sql/serve/): copies of the Library latest views for
Metabase. On the server `serve` is the Postgres database hydroc_serve; here a
local DuckDB catalog stands in for it, over the Lake and Library of
tests/test_library.py.
"""

import csv
import re

import pytest

from storage import lake, serve
from test_lake import DDL, con, load, raw, run  # noqa: F401  (fixtures)
from test_library import lib  # noqa: F401  (fixture)

ROOT = DDL.parents[1]


def library_tables():
    """(source, table) of every Lake table with Library scripts."""
    with open(ROOT / "data" / "static" / "sources.csv", encoding="utf-8", newline="") as f:
        sources = [row["code"] for row in csv.DictReader(f)]
    codes = sorted({p.stem.removesuffix("_dev") for p in (ROOT / "sql" / "ddl" / "library").glob("*.sql")})
    return [(s, code.removeprefix(s + "_")) for code in codes for s in sources if code.startswith(s + "_")]


@pytest.mark.parametrize(("source", "table"), library_tables())
def test_every_library_table_is_served(source, table):
    """Each serve script replaces the copies of exactly its latest views."""
    path = serve.serve_script(source, table)
    assert path is not None, f"missing sql/serve/{source}/{table}.sql"
    sql = path.read_text(encoding="utf-8")
    code = f"{source}_{table}"
    views = [p.stem for p in lake.library_scripts(source, table)]
    assert re.findall(r"CREATE TABLE serve\.latest\.(\w+) AS SELECT \* FROM library\.latest\.(\w+);", sql) == [
        (v, v) for v in views
    ]
    assert re.findall(r"DROP TABLE IF EXISTS serve\.latest\.(\w+);", sql) == views
    assert views[0] == code
    assert sql.count("BEGIN;") == 1 and sql.rstrip().endswith("COMMIT;")


def test_unserved_table():
    assert serve.serve_script("no_sodir", "no_such_table") is None


@pytest.fixture
def served(lib):  # noqa: F811
    lib.execute("ATTACH ':memory:' AS serve")
    lib.execute("CREATE SCHEMA serve.latest")
    return lib


def test_serve_copies_the_latest_views(served):
    path = serve.serve_script("no_sodir", "field_production_monthly")
    for _ in range(2):  # a re-run replaces the copies
        run(served, path)
        for view in ("no_sodir_field_production_monthly", "no_sodir_field_production_monthly_dev"):
            assert sorted(served.execute(f"SELECT * FROM serve.latest.{view}").fetchall()) == sorted(
                served.execute(f"SELECT * FROM library.latest.{view}").fetchall()
            )
    # EKOFISK, TROLL, GULLFAKS, OSEBERG: current versions only
    assert served.execute("SELECT count(*) FROM serve.latest.no_sodir_field_production_monthly_dev").fetchone()[0] == 4
