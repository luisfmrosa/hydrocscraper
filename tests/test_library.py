"""The Sodir Library frame and latest views (development) on a local DuckDB, over
the Lake built by the full load of tests/test_lake.py's snapshots:

  F1 (Jan): EKOFISK 1.0, TROLL 2.0, GULLFAKS 3.0
  F2 (Feb): EKOFISK 1.0, TROLL 20.0 (changed), OSEBERG 4.0 (new); GULLFAKS deleted
  F3 (Mar): as F2, GULLFAKS back
"""

from datetime import datetime, timezone

import pytest

from storage import lake
from test_lake import DDL, con, load, raw, run  # noqa: F401  (fixtures)

FRAME = "library.frame.no_sodir_field_production_monthly_dev"
LATEST = "library.latest.no_sodir_field_production_monthly_dev"
JAN, FEB, MAR = (datetime(2026, m, 1, 10, 0, tzinfo=timezone.utc) for m in (1, 2, 3))
OPEN = None  # versions() reports an open ___Effective_To ('infinity') as None


@pytest.fixture
def lib(con):  # noqa: F811
    con.execute("ATTACH ':memory:' AS library")
    run(con, DDL / "20_library.sql")
    load(con, "full")
    for path in lake.library_scripts("no_sodir", "field_production_monthly"):
        run(con, path)
    return con


def versions(con, field):
    return con.execute(
        "SELECT prfPrdOilNetMillSm3, ___Effective_From, "
        "CASE WHEN isfinite(___Effective_To) THEN ___Effective_To END, ___Is_Deleted "
        f"FROM {FRAME} "
        "WHERE prfInformationCarrier = ? ORDER BY ___Effective_From",
        [field],
    ).fetchall()


def test_library_scripts_resolve():
    assert [p.name for p in lake.library_scripts("no_sodir", "field_production_monthly")] == [
        "no_sodir_field_production_monthly.sql",
        "no_sodir_field_production_monthly_dev.sql",
    ]


def test_frame_has_one_version_per_lake_row(lib):
    assert lib.execute(f"SELECT count(*) FROM {FRAME}").fetchone()[0] == 7
    assert versions(lib, "EKOFISK") == [(1.0, JAN, OPEN, False)]
    assert versions(lib, "TROLL") == [(2.0, JAN, FEB, False), (20.0, FEB, OPEN, False)]
    assert versions(lib, "OSEBERG") == [(4.0, FEB, OPEN, False)]
    # deleted in Feb, back in Mar
    assert versions(lib, "GULLFAKS") == [(3.0, JAN, FEB, False), (3.0, FEB, MAR, True), (3.0, MAR, OPEN, False)]


def test_one_open_version_per_key(lib):
    assert lib.execute(
        f"SELECT count(*) FROM (SELECT prfNpdidInformationCarrier, prfYear, prfMonth FROM {FRAME} "
        f"WHERE ___Effective_To = 'infinity'::TIMESTAMPTZ GROUP BY ALL HAVING count(*) <> 1)"
    ).fetchone()[0] == 0


def test_hook_column(lib):
    hooks = lib.execute(f"SELECT DISTINCT prfInformationCarrier, HK_FIELD FROM {FRAME} ORDER BY 1").fetchall()
    assert hooks == [
        ("EKOFISK", "no_sodir.sup.field|EKOFISK"),
        ("GULLFAKS", "no_sodir.sup.field|GULLFAKS"),
        ("OSEBERG", "no_sodir.sup.field|OSEBERG"),
        ("TROLL", "no_sodir.sup.field|TROLL"),
    ]


def test_latest_has_current_versions_only(lib):
    rows = lib.execute(f"SELECT prfInformationCarrier, prfPrdOilNetMillSm3 FROM {LATEST} ORDER BY 1").fetchall()
    assert rows == [("EKOFISK", 1.0), ("GULLFAKS", 3.0), ("OSEBERG", 4.0), ("TROLL", 20.0)]
    columns = [r[0] for r in lib.execute(f"DESCRIBE {LATEST}").fetchall()]
    assert columns[0] == "HK_FIELD"
    assert not {"___Effective_From", "___Effective_To", "___Is_Deleted"} & set(columns)


def test_latest_excludes_a_key_deleted_last(lib):
    # A fourth file without OSEBERG: the load appends a deletion row
    lib.execute(
        "INSERT INTO lake.no_sodir.field_production_monthly "
        "SELECT * REPLACE (TIMESTAMPTZ '2026-04-01 10:00:00+00' AS ___Lake_load_timestamp, true AS ___Lake_isdeleted) "
        "FROM (VALUES (43625::BIGINT, 2025, 1, 'OSEBERG', 4.0, 0.5, 0.0, 0.0, 1.5, 0.1, 'x', NULL::TIMESTAMPTZ, "
        "'no_sodir_field_production_monthly', 'f4', false)) "
        "t(prfNpdidInformationCarrier, prfYear, prfMonth, prfInformationCarrier, prfPrdOilNetMillSm3, "
        "prfPrdGasNetBillSm3, prfPrdNGLNetMillSm3, prfPrdCondensateNetMillSm3, prfPrdOeNetMillSm3, "
        "prfPrdProducedWaterInFieldMillSm3, ___Lake_md5, ___Lake_load_timestamp, ___Lake_datasource, "
        "___Lake_sourcefile, ___Lake_isdeleted)"
    )
    apr = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
    assert versions(lib, "OSEBERG") == [(4.0, FEB, apr, False), (4.0, apr, OPEN, True)]
    names = [r[0] for r in lib.execute(f"SELECT prfInformationCarrier FROM {LATEST}").fetchall()]
    assert "OSEBERG" not in names


@pytest.mark.parametrize("zone", ["Europe/Oslo", "America/Sao_Paulo"])
def test_open_end_does_not_depend_on_the_session_time_zone(lib, zone):
    def snapshot():
        open_versions = lib.execute(
            f"SELECT count(*) FROM {FRAME} WHERE ___Effective_To = 'infinity'::TIMESTAMPTZ"
        ).fetchone()[0]
        latest = lib.execute(f"SELECT * FROM {LATEST} ORDER BY ALL").fetchall()
        return open_versions, latest

    utc = snapshot()
    lib.execute(f"SET TimeZone = '{zone}'")
    assert snapshot() == utc
    assert utc[0] == 4     # one open version per key


# --- production views ---------------------------------------------------------

PROD_FRAME = "library.frame.no_sodir_field_production_monthly"
PROD_LATEST = "library.latest.no_sodir_field_production_monthly"


def test_production_frame_matches_development(lib):
    # same versions and data; only the hook column differs
    cols = "* EXCLUDE (HK_FIELD)"
    assert lib.execute(f"SELECT {cols} FROM {PROD_FRAME} ORDER BY ALL").fetchall() == \
        lib.execute(f"SELECT {cols} FROM {FRAME} ORDER BY ALL").fetchall()
    assert lib.execute(f"SELECT {cols} FROM {PROD_LATEST} ORDER BY ALL").fetchall() == \
        lib.execute(f"SELECT {cols} FROM {LATEST} ORDER BY ALL").fetchall()


def test_production_hook_is_the_npdid_as_4_bytes(lib):
    hooks = dict(lib.execute(f"SELECT DISTINCT prfInformationCarrier, HK_FIELD FROM {PROD_FRAME}").fetchall())
    # key_set_binary 0x080101, then the NPDID big-endian: 43506 = 0x0000A9F2
    assert hooks == {
        "EKOFISK": bytes.fromhex("0801010000A9F2"),
        "GULLFAKS": bytes.fromhex("0801010000AAA6"),
        "OSEBERG": bytes.fromhex("0801010000AA69"),
        "TROLL": bytes.fromhex("0801010000B565"),
    }
