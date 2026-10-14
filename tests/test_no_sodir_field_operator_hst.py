"""The Sodir field operators dataset end to end on a local DuckDB, with the real
SQL files: raw view, Std script, std view, Lake DDL and loads, Library views
(development and production). Plus the scraper. CSV snapshots are written like
Sodir's export (BOM, CRLF, trailing blank line, dd.mm.yyyy). One row per field,
operator company and start date; a company can operate a field more than once:

  O1 (Jan): TROLL Hydro twice (1986-1995, 2000-2006), TROLL Equinor (current),
            SNORRE Saga
  O2 (Feb): the export date moved; TROLL Hydro otherwise unchanged (its
            second period only re-dated by Sodir: fldOperatorDateUpdated
            moved), TROLL Equinor closed, TROLL Aker new (current), SNORRE
            Saga gone
  O3 (Mar): as O2 with a new export date, SNORRE Saga back
"""

from datetime import date, datetime, timezone

import duckdb
import pytest

import sodir_tableview as st
from scrapers import base
from scrapers.no_sodir.field_operator_hst import NoSodirFieldOperatorHst
from storage import lake, std
from test_lake import DDL

DATASET = "field_operator_hst"
HEADER = ("fldName,cmpLongName,fldOperatorFrom,fldOperatorTo,fldNpdidField,cmpNpdidCompany,"
          "fldOperatorDateUpdated,datesyncNPD")
O1, O2, O3 = (st.raw_key(DATASET, m) for m in (1, 2, 3))
FIELDS = {"TROLL": 46437, "SNORRE": 43718}
COMPANIES = {"Norsk Hydro": 2367, "Equinor": 17237817, "Aker": 28111080, "Saga": 3176}
HYDRO_1 = ("TROLL", "Norsk Hydro", "01.01.1986", "31.12.1995", "20.02.2026")
HYDRO_2 = ("TROLL", "Norsk Hydro", "01.01.2000", "31.12.2006", "20.02.2026")
HYDRO_2_REDATED = HYDRO_2[:4] + ("01.02.2026",)
EQUINOR = ("TROLL", "Equinor", "01.01.2007", "", "20.02.2026")
EQUINOR_2 = ("TROLL", "Equinor", "01.01.2007", "31.01.2026", "01.02.2026")
AKER = ("TROLL", "Aker", "01.02.2026", "", "01.02.2026")
SAGA = ("SNORRE", "Saga", "01.01.1988", "31.12.1999", "20.02.2026")
# (field, company, from, to, date updated) per file, and its export date
SNAPSHOTS = {
    O1: ([HYDRO_1, HYDRO_2, EQUINOR, SAGA], "01.01.2026"),
    O2: ([HYDRO_1, HYDRO_2_REDATED, EQUINOR_2, AKER], "01.02.2026"),
    O3: ([HYDRO_1, HYDRO_2_REDATED, EQUINOR_2, AKER, SAGA], "01.03.2026"),
}
FRAME, LATEST = "library.frame.no_sodir_field_operator_hst", "library.latest.no_sodir_field_operator_hst"
JAN, FEB, MAR = (datetime(2026, m, 1, 10, 0, tzinfo=timezone.utc) for m in (1, 2, 3))


def csv_bytes(rows, synced):
    lines = [
        f"{field},{company},{start},{end},{FIELDS[field]},{COMPANIES[company]},{updated},{synced}"
        for field, company, start, end, updated in rows
    ]
    return st.sodir_csv(HEADER, lines)


@pytest.fixture
def con(tmp_path_factory):
    files = {key: csv_bytes(rows, synced) for key, (rows, synced) in SNAPSHOTS.items()}
    return st.build(tmp_path_factory, DATASET, files)


def changes(con, key):
    return sorted(con.execute(
        f"SELECT cmpLongName, fldOperatorFrom, ___Lake_isdeleted FROM lake.no_sodir.{DATASET} "
        "WHERE ___Lake_sourcefile = ?", [con.std_bucket + st.std_key(DATASET, key)],
    ).fetchall())


def test_scripts_resolve():
    root = DDL.parents[1]
    assert [p.relative_to(root).as_posix() for p in std.std_scripts("no_sodir", DATASET)] == [
        "sql/ddl/raw_views/025_no_sodir_field_operator_hst.sql",
        "sql/std/no_sodir/field_operator_hst.sql",
    ]
    assert [p.relative_to(root).as_posix() for p in lake.lake_scripts("no_sodir", DATASET, "full")] == [
        "sql/ddl/std_views/025_no_sodir_field_operator_hst.sql",
        "sql/ddl/lake/no_sodir_field_operator_hst.sql",
        "sql/lake/no_sodir/field_operator_hst_full.sql",
    ]
    assert [p.name for p in lake.library_scripts("no_sodir", DATASET)] == [
        "no_sodir_field_operator_hst.sql", "no_sodir_field_operator_hst_dev.sql",
    ]


def test_std_types(con):
    parquet = f"read_parquet('{con.std_bucket + st.std_key(DATASET, O1)}')"
    written = con.execute(
        f"SELECT fldNpdidField, cmpNpdidCompany, fldOperatorFrom, fldOperatorTo, fldOperatorDateUpdated, "
        f"datesyncNPD FROM {parquet} ORDER BY 1, 2, 3"
    ).fetchall()
    assert len(written) == 4     # the trailing blank line is no row
    # the current operator has no end date
    assert written[-1] == (46437, 17237817, date(2007, 1, 1), None, date(2026, 2, 20), date(2026, 1, 1))
    types = dict(con.execute(f"SELECT column_name, column_type FROM (DESCRIBE FROM {parquet})").fetchall())
    assert list(types)[:3] == ["fldNpdidField", "cmpNpdidCompany", "fldOperatorFrom"]
    assert types["cmpNpdidCompany"] == "BIGINT"
    assert types["fldOperatorFrom"] == "DATE"


def test_std_fails_on_schema_change(con):
    key = st.raw_key(DATASET, 4)
    st.write_raw(con, key, csv_bytes(SNAPSHOTS[O1][0], "01.04.2026").replace(b"datesyncNPD", b"DatesyncNPD"))
    with pytest.raises(duckdb.Error, match="missing: datesyncNPD; unexpected: DatesyncNPD"):
        st.run_std(con, DATASET, key)


def test_std_fails_on_an_empty_start_date(con):
    key = st.raw_key(DATASET, 4)
    st.write_raw(con, key, csv_bytes([HYDRO_1, ("SNORRE", "Saga", "", "", "20.02.2026")], "01.04.2026"))
    with pytest.raises(duckdb.Error, match="Empty fldOperatorFrom in .*: SNORRE/Saga"):
        st.run_std(con, DATASET, key)


def test_std_md5_ignores_the_export_and_update_dates(con):
    # TROLL Hydro differs between files only by datesyncNPD (first period),
    # or by datesyncNPD and fldOperatorDateUpdated (second period)
    md5s = con.execute(
        "SELECT fldOperatorFrom, count(DISTINCT ___Std_md5), count(DISTINCT datesyncNPD), "
        f"count(DISTINCT fldOperatorDateUpdated) FROM hook.std_views.no_sodir_{DATASET} "
        "WHERE cmpNpdidCompany = 2367 GROUP BY 1 ORDER BY 1"
    ).fetchall()
    assert md5s == [(date(1986, 1, 1), 1, 3, 1), (date(2000, 1, 1), 1, 3, 2)]


def test_full_replays_files_oldest_first(con):
    assert st.load(con, DATASET, "full") == 8
    assert changes(con, O1) == [("Equinor", date(2007, 1, 1), False), ("Norsk Hydro", date(1986, 1, 1), False),
                                ("Norsk Hydro", date(2000, 1, 1), False), ("Saga", date(1988, 1, 1), False)]
    # the export and update dates alone make no row; changed, deleted and new do
    assert changes(con, O2) == [("Aker", date(2026, 2, 1), False), ("Equinor", date(2007, 1, 1), False),
                                ("Saga", date(1988, 1, 1), True)]
    assert changes(con, O3) == [("Saga", date(1988, 1, 1), False)]


def test_incremental_matches_full(con):
    for day, (key, expected) in enumerate(((O1, 4), (O2, 3), (O3, 1)), start=1):
        st.add_watermark(con, DATASET, key, day)
        assert st.load(con, DATASET, "incremental") == expected
    assert st.load(con, DATASET, "incremental") == 0     # same file again
    incremental = st.lake_rows(con, DATASET)
    st.load(con, DATASET, "full")
    assert st.lake_rows(con, DATASET) == incremental


def test_frames_and_latest(con):
    st.load(con, DATASET, "full")
    st.library(con, DATASET)
    for suffix in ("", "_dev"):
        assert con.execute(f"SELECT count(*) FROM {FRAME}{suffix}").fetchone()[0] == 8
        latest = con.execute(
            f"SELECT fldName, cmpLongName, fldOperatorFrom, fldOperatorTo FROM {LATEST}{suffix} ORDER BY 1, 3"
        ).fetchall()
        assert latest == [("SNORRE", "Saga", date(1988, 1, 1), date(1999, 12, 31)),
                          ("TROLL", "Norsk Hydro", date(1986, 1, 1), date(1995, 12, 31)),
                          ("TROLL", "Norsk Hydro", date(2000, 1, 1), date(2006, 12, 31)),
                          ("TROLL", "Equinor", date(2007, 1, 1), date(2026, 1, 31)),
                          ("TROLL", "Aker", date(2026, 2, 1), None)]
    versions = con.execute(
        f"SELECT ___Effective_From, CASE WHEN isfinite(___Effective_To) THEN ___Effective_To END, "
        f"fldOperatorTo FROM {FRAME} WHERE cmpNpdidCompany = 17237817 ORDER BY 1"
    ).fetchall()
    assert versions == [(JAN, FEB, None), (FEB, None, date(2026, 1, 31))]


def test_hooks(con):
    st.load(con, DATASET, "full")
    st.library(con, DATASET)
    dev = set(con.execute(f"SELECT HK_FIELD, HK_COMPANY__Operator FROM {LATEST}_dev").fetchall())
    assert dev == {
        ("no_sodir.sup.field|TROLL", "no_sodir.sup.cmp|Norsk Hydro"),
        ("no_sodir.sup.field|TROLL", "no_sodir.sup.cmp|Equinor"),
        ("no_sodir.sup.field|TROLL", "no_sodir.sup.cmp|Aker"),
        ("no_sodir.sup.field|SNORRE", "no_sodir.sup.cmp|Saga"),
    }
    # key sets 0x080101 (field) and 0x080102 (company), then the NPDID
    # big-endian: 46437 = 0x0000B565, 2367 = 0x0000093F, 17237817 = 0x01070739
    prod = dict(con.execute(
        f"SELECT cmpNpdidCompany, (HK_FIELD, HK_COMPANY__Operator) FROM {LATEST} WHERE fldName = 'TROLL'"
    ).fetchall())
    assert prod[2367] == (bytes.fromhex("0801010000B565"), bytes.fromhex("0801020000093F"))
    assert prod[17237817] == (bytes.fromhex("0801010000B565"), bytes.fromhex("08010201070739"))


# --- the scraper ------------------------------------------------------------

def test_url_is_the_field_operator_report():
    url = NoSodirFieldOperatorHst(client=None).url
    assert "/tableview/field_operator_hst&" in url and "rs:Format=CSV" in url


@pytest.mark.parametrize("rows, synced, new", [
    (SNAPSHOTS[O1][0], "05.01.2026", False),                         # only the export date moved
    ([HYDRO_1, HYDRO_2_REDATED, EQUINOR, SAGA], "05.01.2026", False),  # and an update date
    (SNAPSHOTS[O2][0], "01.01.2026", True),                          # operators changed
    (SNAPSHOTS[O1][0][:3], "01.01.2026", True),                      # a row removed
])
def test_is_new_content_ignores_the_export_and_update_dates(monkeypatch, tmp_path, rows, synced, new):
    monkeypatch.setattr(base, "read_watermark", lambda s, d: {"raw_file": "prev"})
    monkeypatch.setattr(base.s3, "get_bytes", lambda key: csv_bytes(*SNAPSHOTS[O1]))
    scraper = NoSodirFieldOperatorHst(client=None)
    path = tmp_path / "field_operator_hst.csv"
    path.write_bytes(csv_bytes(rows, synced))
    assert scraper.is_new_content(path, ignore_columns=scraper.volatile_columns) is new
