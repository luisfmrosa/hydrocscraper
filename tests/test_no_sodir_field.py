"""The Sodir fields dataset end to end on a local DuckDB, with the real SQL files:
raw view, Std script, std view, Lake DDL and loads, Library views (development
and production). Plus the scraper's content comparison. CSV snapshots are
written like Sodir's export (BOM, CRLF, trailing blank line, dd.mm.yyyy):

  G1 (Jan): EKOFISK, TROLL, GULLFAKS
  G2 (Feb): every export date moved; EKOFISK otherwise unchanged, TROLL shut
            down, GULLFAKS removed, OSEBERG new
  G3 (Mar): as G2 with new export dates, GULLFAKS back
"""

from datetime import date, datetime, timezone
from pathlib import Path

import duckdb
import pytest

from scrapers import base
from scrapers.no_sodir.field import NoSodirField, _period
from storage import lake, std
from test_lake import DDL, Env, run

HEADER = (
    "fldName,cmpLongName,fldCurrentActivitySatus,wlbName,wlbCompletionDate,fldMainArea,fldOwnerKind,"
    "fldOwnerName,fldMainSupplyBase,fldHcType,fldNpdidOwner,fldNpdidField,wlbNpdidWellbore,cmpNpdidCompany,"
    "fldFactPageUrl,fldFactMapUrl,fldDateUpdated,fldDateUpdatedMax,DatesyncNPD"
)
PREFIX = "no_sodir/field/"
G1 = PREFIX + "year_month=2026-01/field_20260101_1000.csv"
G2 = PREFIX + "year_month=2026-02/field_20260201_1000.csv"
G3 = PREFIX + "year_month=2026-03/field_20260301_1000.csv"
NPDID = {"EKOFISK": 43506, "TROLL": 46437, "GULLFAKS": 43686, "OSEBERG": 43625}

# (field, status) per file, and the file's export date (DatesyncNPD and fldDateUpdatedMax)
SNAPSHOTS = {
    G1: ([("EKOFISK", "Producing"), ("TROLL", "Producing"), ("GULLFAKS", "Producing")], "01.01.2026"),
    G2: ([("EKOFISK", "Producing"), ("TROLL", "Shut down"), ("OSEBERG", "Producing")], "01.02.2026"),
    G3: ([("EKOFISK", "Producing"), ("TROLL", "Shut down"), ("GULLFAKS", "Producing"),
          ("OSEBERG", "Producing")], "01.03.2026"),
}
FRAME, LATEST = "library.frame.no_sodir_field", "library.latest.no_sodir_field"
JAN, FEB, MAR = (datetime(2026, m, 1, 10, 0, tzinfo=timezone.utc) for m in (1, 2, 3))


def csv_text(rows, synced):
    lines = [HEADER] + [
        # fldMainSupplyBase empty, as for many fields
        f"{name},Equinor Energy AS,{status},1/1-1,26.11.1972,North sea,PRODUCTION LICENCE,018,,OIL,"
        f"1,{NPDID[name]},2,3,https://f/{NPDID[name]},https://m/{NPDID[name]},07.05.2025,{synced},{synced}"
        for name, status in rows
    ]
    return "﻿" + "\r\n".join(lines) + "\r\n\r\n"


def std_key(raw_key):
    folder, name = raw_key.rsplit("/", 1)
    return folder + "/no_sodir_field_" + name[len("field_"):-len(".csv")] + ".parquet"


@pytest.fixture
def con(tmp_path_factory):
    raw = tmp_path_factory.mktemp("raw")
    for key, (rows, synced) in SNAPSHOTS.items():
        path = raw / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(csv_text(rows, synced).encode("utf-8"))
    std_dir = tmp_path_factory.mktemp("std")
    con = Env(duckdb.connect(), raw.as_posix() + "/", std_dir.as_posix() + "/")
    for layer in ("lake", "hook", "library"):
        con.execute(f"ATTACH ':memory:' AS {layer}")
    for path in (DDL / "20_library.sql", DDL / "40_hook.sql", DDL / "41_hook_watermark.sql",
                 std.std_scripts("no_sodir", "field")[0]):
        run(con, path)
    for key in SNAPSHOTS:
        (std_dir / std_key(key)).parent.mkdir(parents=True, exist_ok=True)
        run(con, std.std_scripts("no_sodir", "field")[1], {"raw_file": con.bucket + key})
    for path in lake.lake_scripts("no_sodir", "field", "full")[:2]:
        run(con, path)
    return con


def load(con, mode):
    return run(con, lake.lake_scripts("no_sodir", "field", mode)[2])[0][0]


def library(con):
    for path in lake.library_scripts("no_sodir", "field"):
        run(con, path)


def changes(con, key):
    return sorted(con.execute(
        "SELECT fldName, fldCurrentActivitySatus, ___Lake_isdeleted FROM lake.no_sodir.field "
        "WHERE ___Lake_sourcefile = ?", [con.std_bucket + std_key(key)],
    ).fetchall())


def lake_rows(con):
    return sorted(con.execute("SELECT * EXCLUDE (___Lake_sourcefile) FROM lake.no_sodir.field").fetchall())


def test_scripts_resolve():
    root = DDL.parents[1]
    assert [p.relative_to(root).as_posix() for p in std.std_scripts("no_sodir", "field")] == [
        "sql/ddl/raw_views/021_no_sodir_field.sql",
        "sql/std/no_sodir/field.sql",
    ]
    assert [p.relative_to(root).as_posix() for p in lake.lake_scripts("no_sodir", "field", "full")] == [
        "sql/ddl/std_views/021_no_sodir_field.sql",
        "sql/ddl/lake/no_sodir_field.sql",
        "sql/lake/no_sodir/field_full.sql",
    ]
    assert [p.name for p in lake.library_scripts("no_sodir", "field")] == [
        "no_sodir_field.sql", "no_sodir_field_dev.sql",
    ]


def test_std_types_dates_and_nulls(con):
    written = con.execute(
        f"SELECT fldNpdidField, wlbCompletionDate, fldMainSupplyBase, fldDateUpdated, DatesyncNPD "
        f"FROM read_parquet('{con.std_bucket + std_key(G1)}') ORDER BY 1"
    ).fetchall()
    assert written[0] == (43506, date(1972, 11, 26), None, date(2025, 5, 7), date(2026, 1, 1))
    assert len(written) == 3     # the trailing blank line is no row
    columns = [r[0] for r in con.execute(
        f"DESCRIBE FROM read_parquet('{con.std_bucket + std_key(G1)}')").fetchall()]
    assert columns[0] == "fldNpdidField"
    assert "fldCurrentActivitySatus" in columns       # Sodir's spelling kept


def test_std_fails_on_schema_change(con):
    key = PREFIX + "year_month=2026-04/field_20260401_1000.csv"
    path = Path(con.bucket) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    text = csv_text([("EKOFISK", "Producing")], "01.04.2026")
    path.write_text(text.replace("fldCurrentActivitySatus", "fldCurrentActivityStatus"), encoding="utf-8")
    (Path(con.std_bucket) / std_key(key)).parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(duckdb.Error, match="missing: fldCurrentActivitySatus; unexpected: fldCurrentActivityStatus"):
        run(con, std.std_scripts("no_sodir", "field")[1], {"raw_file": con.bucket + key})


def test_std_fails_on_a_bad_date(con):
    key = PREFIX + "year_month=2026-04/field_20260401_1000.csv"
    path = Path(con.bucket) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(csv_text([("EKOFISK", "Producing")], "2026-04-01"), encoding="utf-8")
    (Path(con.std_bucket) / std_key(key)).parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(duckdb.Error):
        run(con, std.std_scripts("no_sodir", "field")[1], {"raw_file": con.bucket + key})


def test_std_md5_ignores_export_dates(con):
    # EKOFISK differs between files only by fldDateUpdatedMax and DatesyncNPD
    md5s = con.execute(
        "SELECT count(DISTINCT ___Std_md5), count(DISTINCT DatesyncNPD) "
        "FROM hook.std_views.no_sodir_field WHERE fldName = 'EKOFISK'"
    ).fetchone()
    assert md5s == (1, 3)


def test_full_replays_files_oldest_first(con):
    assert load(con, "full") == 7
    assert changes(con, G1) == [("EKOFISK", "Producing", False), ("GULLFAKS", "Producing", False),
                                ("TROLL", "Producing", False)]
    # export dates alone make no row; changed, deleted and new do
    assert changes(con, G2) == [("GULLFAKS", "Producing", True), ("OSEBERG", "Producing", False),
                                ("TROLL", "Shut down", False)]
    assert changes(con, G3) == [("GULLFAKS", "Producing", False)]


def test_incremental_matches_full(con):
    for day, (key, expected) in enumerate(((G1, 3), (G2, 3), (G3, 1)), start=1):
        con.execute(
            "INSERT INTO hook.metadata.watermark (source, dataset, load_mode, raw_file, status, updated_at) "
            "VALUES ('no_sodir', 'field', 'incremental', ?, 'ok', ?)",
            [key, datetime(2026, 4, day, tzinfo=timezone.utc)],
        )
        assert load(con, "incremental") == expected
    assert load(con, "incremental") == 0     # same file again
    incremental = lake_rows(con)
    load(con, "full")
    assert lake_rows(con) == incremental


def test_frames_and_latest(con):
    load(con, "full")
    library(con)
    for suffix in ("", "_dev"):
        assert con.execute(f"SELECT count(*) FROM {FRAME}{suffix}").fetchone()[0] == 7
        latest = con.execute(f"SELECT fldName, fldCurrentActivitySatus FROM {LATEST}{suffix} ORDER BY 1").fetchall()
        assert latest == [("EKOFISK", "Producing"), ("GULLFAKS", "Producing"),
                          ("OSEBERG", "Producing"), ("TROLL", "Shut down")]
    versions = con.execute(
        f"SELECT ___Effective_From, CASE WHEN isfinite(___Effective_To) THEN ___Effective_To END, ___Is_Deleted "
        f"FROM {FRAME} WHERE fldName = 'GULLFAKS' ORDER BY 1"
    ).fetchall()
    assert versions == [(JAN, FEB, False), (FEB, MAR, True), (MAR, None, False)]


def test_development_hook_is_the_name(con):
    load(con, "full")
    library(con)
    hooks = con.execute(f"SELECT DISTINCT HK_FIELD FROM {LATEST}_dev ORDER BY 1").fetchall()
    assert [h[0] for h in hooks] == ["no_sodir.sup.field|EKOFISK", "no_sodir.sup.field|GULLFAKS",
                                     "no_sodir.sup.field|OSEBERG", "no_sodir.sup.field|TROLL"]


def test_production_hook_is_the_npdid_as_4_bytes(con):
    load(con, "full")
    library(con)
    hooks = dict(con.execute(f"SELECT fldName, HK_FIELD FROM {LATEST}").fetchall())
    # key_set_binary 0x080101, then 43506 = 0x0000A9F2 big-endian
    assert hooks["EKOFISK"] == b"\x08\x01\x01\x00\x00\xa9\xf2"
    assert {len(h) for h in hooks.values()} == {7}
    assert con.execute(f"SELECT typeof(HK_FIELD) FROM {FRAME} LIMIT 1").fetchone()[0] == "BLOB"


def test_production_hook_rejects_a_negative_npdid(con):
    load(con, "full")
    library(con)
    con.execute("UPDATE lake.no_sodir.field SET fldNpdidField = -1 WHERE fldName = 'EKOFISK'")
    with pytest.raises(duckdb.Error):
        con.execute(f"SELECT HK_FIELD FROM {FRAME}").fetchall()


# --- the scraper ------------------------------------------------------------

def scraper_with_previous(monkeypatch, previous: str):
    monkeypatch.setattr(base, "read_watermark", lambda s, d: {"raw_file": "prev"})
    monkeypatch.setattr(base.s3, "get_bytes", lambda key: previous.encode("utf-8"))
    return NoSodirField(client=None)


@pytest.mark.parametrize("rows, synced, new", [
    (SNAPSHOTS[G1][0], "05.01.2026", False),                     # only the export dates moved
    (list(reversed(SNAPSHOTS[G1][0])), "05.01.2026", False),     # row order doesn't matter
    ([("EKOFISK", "Shut down")] + SNAPSHOTS[G1][0][1:], "05.01.2026", True),
    (SNAPSHOTS[G1][0][:2], "01.01.2026", True),                  # a field removed
])
def test_is_new_content_ignores_export_dates(monkeypatch, tmp_path, rows, synced, new):
    scraper = scraper_with_previous(monkeypatch, csv_text(*SNAPSHOTS[G1]))
    path = tmp_path / "field.csv"
    path.write_bytes(csv_text(rows, synced).encode("utf-8"))
    assert scraper.is_new_content(path, ignore_columns=("fldDateUpdatedMax", "DatesyncNPD")) is new


def test_is_new_content_compares_bytes_without_ignored_columns(monkeypatch, tmp_path):
    scraper = scraper_with_previous(monkeypatch, csv_text(*SNAPSHOTS[G1]))
    path = tmp_path / "field.csv"
    path.write_bytes(csv_text(SNAPSHOTS[G1][0], "05.01.2026").encode("utf-8"))
    assert scraper.is_new_content(path) is True


def test_period_is_the_raw_key_month():
    assert _period("no_sodir/field/year_month=2026-10/field_20261006_1718.csv") == "2026-10"
