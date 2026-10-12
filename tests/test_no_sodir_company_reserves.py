"""The Sodir company reserves dataset end to end on a local DuckDB, with the
real SQL files: raw view, Std script, std view, Lake DDL and loads, Library
views (development and production). Plus the scraper. CSV snapshots are
written like Sodir's export (BOM, CRLF, trailing blank line, dd.mm.yyyy).
One row per field and licensee company:

  R1 (Jan): Shell and Equinor in TROLL, Equinor in SNORRE
  R2 (Feb): the export date moved; Shell in TROLL otherwise unchanged,
            Equinor's TROLL reserves revised, Equinor's SNORRE share gone,
            Aker BP in SNORRE new
  R3 (Mar): as R2 with a new export date, Equinor in SNORRE back
"""

from datetime import date, datetime, timezone

import duckdb
import pytest

import sodir_tableview as st
from scrapers import base
from scrapers.no_sodir.company_reserves import NoSodirCompanyReserves
from storage import lake, std
from test_lake import DDL

DATASET = "company_reserves"
HEADER = (
    "cmpLongName,fldName,cmpRemainingOil,cmpRemainingGas,cmpRemainingNGL,cmpRemainingCondensate,"
    "cmpRemainingOE,cmpDateOffResEstDisplay,cmpShare,fldNpdidField,cmpNpdidCompany,DatesyncNPD"
)
R1, R2, R3 = (st.raw_key(DATASET, m) for m in (1, 2, 3))
COMPANIES = {"A/S Norske Shell": 562, "Equinor Energy AS": 32011216, "Aker BP ASA": 28544099}
FIELDS = {"TROLL": 46437, "SNORRE": 43718}
# (company, field, remaining oil, remaining OE, share) per file, and its export date
SNAPSHOTS = {
    R1: ([("A/S Norske Shell", "TROLL", "0.27", "47.17", "8.18531"),
          ("Equinor Energy AS", "TROLL", "1.50", "175.20", "30.58250"),
          ("Equinor Energy AS", "SNORRE", "12.40", "13.05", "33.27511")], "01.01.2026"),
    R2: ([("A/S Norske Shell", "TROLL", "0.27", "47.17", "8.18531"),
          ("Equinor Energy AS", "TROLL", "1.42", "170.03", "30.58250"),
          ("Aker BP ASA", "SNORRE", "4.10", "4.31", "11.57700")], "01.02.2026"),
    R3: ([("A/S Norske Shell", "TROLL", "0.27", "47.17", "8.18531"),
          ("Equinor Energy AS", "TROLL", "1.42", "170.03", "30.58250"),
          ("Equinor Energy AS", "SNORRE", "12.40", "13.05", "33.27511"),
          ("Aker BP ASA", "SNORRE", "4.10", "4.31", "11.57700")], "01.03.2026"),
}
FRAME, LATEST = "library.frame.no_sodir_company_reserves", "library.latest.no_sodir_company_reserves"
JAN, FEB, MAR = (datetime(2026, m, 1, 10, 0, tzinfo=timezone.utc) for m in (1, 2, 3))


def csv_bytes(rows, synced):
    lines = [
        f"{company},{field},{oil},0.00,0.00,0.00,{oe},31.12.2025,{share},{FIELDS[field]},{COMPANIES[company]},{synced}"
        for company, field, oil, oe, share in rows
    ]
    return st.sodir_csv(HEADER, lines)


@pytest.fixture
def con(tmp_path_factory):
    files = {key: csv_bytes(rows, synced) for key, (rows, synced) in SNAPSHOTS.items()}
    return st.build(tmp_path_factory, DATASET, files)


def changes(con, key):
    return sorted(con.execute(
        f"SELECT cmpLongName, fldName, cmpRemainingOE, ___Lake_isdeleted FROM lake.no_sodir.{DATASET} "
        "WHERE ___Lake_sourcefile = ?", [con.std_bucket + st.std_key(DATASET, key)],
    ).fetchall())


def test_scripts_resolve():
    root = DDL.parents[1]
    assert [p.relative_to(root).as_posix() for p in std.std_scripts("no_sodir", DATASET)] == [
        "sql/ddl/raw_views/023_no_sodir_company_reserves.sql",
        "sql/std/no_sodir/company_reserves.sql",
    ]
    assert [p.relative_to(root).as_posix() for p in lake.lake_scripts("no_sodir", DATASET, "full")] == [
        "sql/ddl/std_views/023_no_sodir_company_reserves.sql",
        "sql/ddl/lake/no_sodir_company_reserves.sql",
        "sql/lake/no_sodir/company_reserves_full.sql",
    ]
    assert [p.name for p in lake.library_scripts("no_sodir", DATASET)] == [
        "no_sodir_company_reserves.sql", "no_sodir_company_reserves_dev.sql",
    ]


def test_std_types(con):
    parquet = f"read_parquet('{con.std_bucket + st.std_key(DATASET, R1)}')"
    written = con.execute(
        f"SELECT fldNpdidField, cmpNpdidCompany, cmpRemainingOE, cmpShare, cmpDateOffResEstDisplay, DatesyncNPD "
        f"FROM {parquet} ORDER BY 1, 2"
    ).fetchall()
    assert written[0] == (43718, 32011216, 13.05, 33.27511, date(2025, 12, 31), date(2026, 1, 1))
    assert len(written) == 3     # the trailing blank line is no row
    types = dict(con.execute(f"SELECT column_name, column_type FROM (DESCRIBE FROM {parquet})").fetchall())
    assert list(types)[:2] == ["fldNpdidField", "cmpNpdidCompany"]
    assert types["cmpNpdidCompany"] == "BIGINT"
    assert types["cmpRemainingGas"] == "DOUBLE"
    assert types["cmpShare"] == "DOUBLE"
    assert types["cmpDateOffResEstDisplay"] == "DATE"


def test_std_fails_on_schema_change(con):
    key = st.raw_key(DATASET, 4)
    st.write_raw(con, key, csv_bytes(SNAPSHOTS[R1][0], "01.04.2026").replace(b"cmpShare", b"cmpSharePct"))
    with pytest.raises(duckdb.Error, match="missing: cmpShare; unexpected: cmpSharePct"):
        st.run_std(con, DATASET, key)


def test_std_fails_on_a_value_that_does_not_cast(con):
    key = st.raw_key(DATASET, 4)
    st.write_raw(con, key, csv_bytes(SNAPSHOTS[R1][0], "01.04.2026").replace(b"47.17", b"n/a"))
    with pytest.raises(duckdb.Error):
        st.run_std(con, DATASET, key)


def test_std_md5_ignores_the_export_date(con):
    # Shell in TROLL differs between files only by DatesyncNPD
    md5s = con.execute(
        "SELECT count(DISTINCT ___Std_md5), count(DISTINCT DatesyncNPD) "
        f"FROM hook.std_views.no_sodir_{DATASET} WHERE cmpNpdidCompany = 562"
    ).fetchone()
    assert md5s == (1, 3)


def test_full_replays_files_oldest_first(con):
    assert st.load(con, DATASET, "full") == 7
    assert changes(con, R1) == [("A/S Norske Shell", "TROLL", 47.17, False),
                                ("Equinor Energy AS", "SNORRE", 13.05, False),
                                ("Equinor Energy AS", "TROLL", 175.2, False)]
    # the export date alone makes no row; changed, deleted and new do
    assert changes(con, R2) == [("Aker BP ASA", "SNORRE", 4.31, False),
                                ("Equinor Energy AS", "SNORRE", 13.05, True),
                                ("Equinor Energy AS", "TROLL", 170.03, False)]
    assert changes(con, R3) == [("Equinor Energy AS", "SNORRE", 13.05, False)]


def test_same_company_in_two_fields_is_two_keys(con):
    st.load(con, DATASET, "full")
    keys = con.execute(
        f"SELECT count(DISTINCT (fldNpdidField, cmpNpdidCompany)) FROM lake.no_sodir.{DATASET} "
        "WHERE cmpNpdidCompany = 32011216"
    ).fetchone()[0]
    assert keys == 2


def test_incremental_matches_full(con):
    for day, (key, expected) in enumerate(((R1, 3), (R2, 3), (R3, 1)), start=1):
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
        assert con.execute(f"SELECT count(*) FROM {FRAME}{suffix}").fetchone()[0] == 7
        latest = con.execute(
            f"SELECT cmpLongName, fldName, cmpRemainingOE FROM {LATEST}{suffix} ORDER BY 1, 2").fetchall()
        assert latest == [("A/S Norske Shell", "TROLL", 47.17), ("Aker BP ASA", "SNORRE", 4.31),
                          ("Equinor Energy AS", "SNORRE", 13.05), ("Equinor Energy AS", "TROLL", 170.03)]
    versions = con.execute(
        f"SELECT ___Effective_From, CASE WHEN isfinite(___Effective_To) THEN ___Effective_To END, ___Is_Deleted "
        f"FROM {FRAME} WHERE fldNpdidField = 43718 AND cmpNpdidCompany = 32011216 ORDER BY 1"
    ).fetchall()
    assert versions == [(JAN, FEB, False), (FEB, MAR, True), (MAR, None, False)]


def test_hooks(con):
    st.load(con, DATASET, "full")
    st.library(con, DATASET)
    dev = con.execute(
        f"SELECT HK_COMPANY, HK_FIELD FROM {LATEST}_dev WHERE cmpNpdidCompany = 562").fetchone()
    assert dev == ("no_sodir.sup.cmp|A/S Norske Shell", "no_sodir.sup.field|TROLL")
    # key_set_binary 0x080102 (company) / 0x080101 (field), then the NPDID
    # big-endian: 562 = 0x00000232, 46437 = 0x0000B565
    prod = con.execute(
        f"SELECT HK_COMPANY, HK_FIELD FROM {LATEST} WHERE cmpNpdidCompany = 562").fetchone()
    assert prod == (bytes.fromhex("08010200000232"), bytes.fromhex("0801010000B565"))
    lengths = con.execute(f"SELECT DISTINCT octet_length(HK_COMPANY), octet_length(HK_FIELD) FROM {LATEST}")
    assert lengths.fetchall() == [(7, 7)]


# --- the scraper ------------------------------------------------------------

def test_url_is_the_company_reserves_report():
    url = NoSodirCompanyReserves(client=None).url
    assert "/tableview/company_reserves&" in url and "rs:Format=CSV" in url


@pytest.mark.parametrize("rows, synced, new", [
    (SNAPSHOTS[R1][0], "05.01.2026", False),                         # only the export date moved
    (SNAPSHOTS[R2][0], "01.01.2026", True),                          # reserves changed
    (SNAPSHOTS[R1][0][:2], "01.01.2026", True),                      # a row removed
])
def test_is_new_content_ignores_the_export_date(monkeypatch, tmp_path, rows, synced, new):
    monkeypatch.setattr(base, "read_watermark", lambda s, d: {"raw_file": "prev"})
    monkeypatch.setattr(base.s3, "get_bytes", lambda key: csv_bytes(*SNAPSHOTS[R1]))
    scraper = NoSodirCompanyReserves(client=None)
    path = tmp_path / "company_reserves.csv"
    path.write_bytes(csv_bytes(rows, synced))
    assert scraper.is_new_content(path, ignore_columns=scraper.volatile_columns) is new
