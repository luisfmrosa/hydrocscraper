"""The dbt project (transform/) on a DuckLake, served over quack like the real
server: DuckLake rejects DROP ... CASCADE, which dbt-duckdb uses to replace a
view unless storage/dbt_quack.py marks the server's catalogs as DuckLakes. So
every model is built twice, and the second run must replace the views."""

import duckdb
import pytest

import library_dbt
from storage import library
from test_lake import DDL, Env, run


@pytest.fixture
def lakes(tmp_path):
    con = Env(duckdb.connect(), tmp_path.as_posix() + "/", tmp_path.as_posix() + "/std/")
    con.execute("INSTALL ducklake")
    con.execute("LOAD ducklake")
    for layer in ("lake", "library", "hook"):
        con.execute(
            f"ATTACH 'ducklake:{(tmp_path / layer).as_posix()}.ducklake' AS {layer} "
            f"(DATA_PATH '{(tmp_path / (layer + '_data')).as_posix()}/')"
        )
    for path in (DDL / "20_library.sql", DDL / "40_hook.sql"):
        run(con, path)
    library_dbt.hook_static(con)
    for path in sorted((DDL / "lake").glob("*.sql")):
        run(con, path)
    return con


def test_every_model_builds_twice_on_ducklake(lakes):
    library_dbt.serve(lakes)
    library.dbt(["run"])
    library.dbt(["run"])
    views = lakes.execute(
        "SELECT schema_name || '.' || view_name FROM duckdb_views() "
        "WHERE database_name = 'library' ORDER BY 1"
    ).fetchall()
    assert len(views) == 24  # 6 Lake tables x frame/latest x dev/prod
    assert not [v for (v,) in views if "__dbt_" in v]  # no leftover backup or tmp views
