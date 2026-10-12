"""The Sodir companies dataset end to end on a local DuckDB, with the real SQL
files: raw view, Std script, std view, Lake DDL and loads, Library views
(development and production). Plus the scraper. CSV snapshots are written
like Sodir's export (BOM, CRLF, trailing blank line, dd.mm.yyyy):

  C1 (Jan): Shell, Equinor, Aker BP
  C2 (Feb): the export date moved; Shell otherwise unchanged, Equinor no
            longer a current licence operator, Aker BP removed, Vår Energi new
  C3 (Mar): as C2 with a new export date, Aker BP back
"""

from datetime import date, datetime, timezone

import duckdb
import pytest

import sodir_tableview as st
from scrapers import base
from scrapers.no_sodir.company import NoSodirCompany
from storage import lake, std
from test_lake import DDL

DATASET = "company"
HEADER = (
    "cmpLongName,cmpOrgNumberBrReg,cmpShortName,cmpNationCode,cmpSurveyPrefix,cmpNpdidCompany,"
    "cmpLicenceOperCurrent,cmpLicenceOperFormer,cmpLicenceLicenseeCurrent,cmpLicenceLicenseeFormer,"
    "cmpTufOperCurrent,cmpTufOperFormer,cmpTufPartnerCurrent,cmpTufPartnerFormer,"
    "cmpBsnsArrAreaOperCurrent,cmpBsnsArrAreaOperFormer,cmpBsnsArrAreaPartnerCurrent,"
    "cmpBsnsArrAreaPartnerFormer,dateSyncNPD"
)
C1, C2, C3 = (st.raw_key(DATASET, m) for m in (1, 2, 3))
# name -> (org number, short name, nation, survey prefix, NPDID); Shell's org
# number is blank-only, as for some companies in the real export
COMPANIES = {
    "A/S Norske Shell": (" ", "SHELL NORGE", "NO", "SH", 562),
    "Equinor Energy AS": ("990888213", "EQUINOR ENERGY", "NO", "", 32011216),
    "Aker BP ASA": ("989795848", "AKER BP", "NO", "", 28544099),
    "Vår Energi ASA": ("919160357", "VÅR ENERGI", "NO", "", 50000032),
}
# (company, cmpLicenceOperCurrent) per file, and the file's export date
SNAPSHOTS = {
    C1: ([("A/S Norske Shell", "Y"), ("Equinor Energy AS", "Y"), ("Aker BP ASA", "Y")], "01.01.2026"),
    C2: ([("A/S Norske Shell", "Y"), ("Equinor Energy AS", "N"), ("Vår Energi ASA", "Y")], "01.02.2026"),
    C3: ([("A/S Norske Shell", "Y"), ("Equinor Energy AS", "N"), ("Aker BP ASA", "Y"),
          ("Vår Energi ASA", "Y")], "01.03.2026"),
}
FRAME, LATEST = "library.frame.no_sodir_company", "library.latest.no_sodir_company"
JAN, FEB, MAR = (datetime(2026, m, 1, 10, 0, tzinfo=timezone.utc) for m in (1, 2, 3))


def csv_bytes(rows, synced, flag=None):
    lines = []
    for name, oper_current in rows:
        org, short, nation, prefix, npdid = COMPANIES[name]
        flags = [oper_current] + ["Y", "N", "Y", "N", "N", "N", "N", "N", "N", "N", "N"]
        if flag is not None:
            flags[-1] = flag
        lines.append(f"{name},{org},{short},{nation},{prefix},{npdid},{','.join(flags)},{synced}")
    return st.sodir_csv(HEADER, lines)


@pytest.fixture
def con(tmp_path_factory):
    files = {key: csv_bytes(rows, synced) for key, (rows, synced) in SNAPSHOTS.items()}
    return st.build(tmp_path_factory, DATASET, files)


def changes(con, key):
    return sorted(con.execute(
        "SELECT cmpLongName, cmpLicenceOperCurrent, ___Lake_isdeleted FROM lake.no_sodir.company "
        "WHERE ___Lake_sourcefile = ?", [con.std_bucket + st.std_key(DATASET, key)],
    ).fetchall())


def test_scripts_resolve():
    root = DDL.parents[1]
    assert [p.relative_to(root).as_posix() for p in std.std_scripts("no_sodir", DATASET)] == [
        "sql/ddl/raw_views/022_no_sodir_company.sql",
        "sql/std/no_sodir/company.sql",
    ]
    assert [p.relative_to(root).as_posix() for p in lake.lake_scripts("no_sodir", DATASET, "full")] == [
        "sql/ddl/std_views/022_no_sodir_company.sql",
        "sql/ddl/lake/no_sodir_company.sql",
        "sql/lake/no_sodir/company_full.sql",
    ]
    assert [p.name for p in lake.library_scripts("no_sodir", DATASET)] == [
        "no_sodir_company.sql", "no_sodir_company_dev.sql",
    ]


def test_std_types_flags_and_blank_org_number(con):
    parquet = f"read_parquet('{con.std_bucket + st.std_key(DATASET, C1)}')"
    written = con.execute(
        f"SELECT cmpNpdidCompany, cmpOrgNumberBrReg, cmpLicenceOperCurrent, cmpLicenceOperFormer, dateSyncNPD "
        f"FROM {parquet} ORDER BY 1"
    ).fetchall()
    assert written[0] == (562, None, True, True, date(2026, 1, 1))     # blank-only org number -> NULL
    assert len(written) == 3     # the trailing blank line is no row
    types = dict(con.execute(f"SELECT column_name, column_type FROM (DESCRIBE FROM {parquet})").fetchall())
    assert list(types)[0] == "cmpNpdidCompany"
    assert types["cmpNpdidCompany"] == "BIGINT"
    assert types["cmpBsnsArrAreaPartnerFormer"] == "BOOLEAN"
    assert types["dateSyncNPD"] == "DATE"


def test_std_keeps_non_ascii_names(con):
    names = [r[0] for r in con.execute(
        f"SELECT cmpLongName FROM read_parquet('{con.std_bucket + st.std_key(DATASET, C2)}') ORDER BY 1"
    ).fetchall()]
    assert "Vår Energi ASA" in names


def test_std_fails_on_schema_change(con):
    key = st.raw_key(DATASET, 4)
    st.write_raw(con, key, csv_bytes(SNAPSHOTS[C1][0], "01.04.2026").replace(b"dateSyncNPD", b"DatesyncNPD"))
    with pytest.raises(duckdb.Error, match="missing: dateSyncNPD; unexpected: DatesyncNPD"):
        st.run_std(con, DATASET, key)


@pytest.mark.parametrize("flag", ["X", ""])
def test_std_fails_on_a_flag_other_than_y_or_n(con, flag):
    key = st.raw_key(DATASET, 4)
    st.write_raw(con, key, csv_bytes(SNAPSHOTS[C1][0], "01.04.2026", flag=flag))
    with pytest.raises(duckdb.Error, match="Unexpected flag values .*cmpBsnsArrAreaPartnerFormer="):
        st.run_std(con, DATASET, key)


def test_std_md5_ignores_the_export_date(con):
    # Shell differs between files only by dateSyncNPD
    md5s = con.execute(
        "SELECT count(DISTINCT ___Std_md5), count(DISTINCT dateSyncNPD) "
        "FROM hook.std_views.no_sodir_company WHERE cmpNpdidCompany = 562"
    ).fetchone()
    assert md5s == (1, 3)


def test_full_replays_files_oldest_first(con):
    assert st.load(con, DATASET, "full") == 7
    assert changes(con, C1) == [("A/S Norske Shell", True, False), ("Aker BP ASA", True, False),
                                ("Equinor Energy AS", True, False)]
    # the export date alone makes no row; changed, deleted and new do
    assert changes(con, C2) == [("Aker BP ASA", True, True), ("Equinor Energy AS", False, False),
                                ("Vår Energi ASA", True, False)]
    assert changes(con, C3) == [("Aker BP ASA", True, False)]


def test_incremental_matches_full(con):
    for day, (key, expected) in enumerate(((C1, 3), (C2, 3), (C3, 1)), start=1):
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
            f"SELECT cmpLongName, cmpLicenceOperCurrent FROM {LATEST}{suffix} ORDER BY 1").fetchall()
        assert latest == [("A/S Norske Shell", True), ("Aker BP ASA", True),
                          ("Equinor Energy AS", False), ("Vår Energi ASA", True)]
    versions = con.execute(
        f"SELECT ___Effective_From, CASE WHEN isfinite(___Effective_To) THEN ___Effective_To END, ___Is_Deleted "
        f"FROM {FRAME} WHERE cmpNpdidCompany = 28544099 ORDER BY 1"
    ).fetchall()
    assert versions == [(JAN, FEB, False), (FEB, MAR, True), (MAR, None, False)]


def test_hooks(con):
    st.load(con, DATASET, "full")
    st.library(con, DATASET)
    dev = dict(con.execute(f"SELECT cmpNpdidCompany, HK_COMPANY FROM {LATEST}_dev").fetchall())
    prod = dict(con.execute(f"SELECT cmpNpdidCompany, HK_COMPANY FROM {LATEST}").fetchall())
    assert dev[562] == "no_sodir.sup.cmp|A/S Norske Shell"
    assert dev[50000032] == "no_sodir.sup.cmp|Vår Energi ASA"
    # key_set_binary 0x080102, then the NPDID big-endian: 562 = 0x00000232
    assert prod[562] == bytes.fromhex("08010200000232")
    assert prod[32011216] == bytes.fromhex("08010201E873D0")     # as HK_COMPANY__Operator in the fields frame
    assert {len(h) for h in prod.values()} == {7}


# --- the scraper ------------------------------------------------------------

def test_url_is_the_company_report():
    url = NoSodirCompany(client=None).url
    assert "/tableview/company&" in url and "rs:Format=CSV" in url


@pytest.mark.parametrize("rows, synced, new", [
    (SNAPSHOTS[C1][0], "05.01.2026", False),                         # only the export date moved
    ([("A/S Norske Shell", "N")] + SNAPSHOTS[C1][0][1:], "05.01.2026", True),
    (SNAPSHOTS[C1][0][:2], "01.01.2026", True),                      # a company removed
])
def test_is_new_content_ignores_the_export_date(monkeypatch, tmp_path, rows, synced, new):
    monkeypatch.setattr(base, "read_watermark", lambda s, d: {"raw_file": "prev"})
    monkeypatch.setattr(base.s3, "get_bytes", lambda key: csv_bytes(*SNAPSHOTS[C1]))
    scraper = NoSodirCompany(client=None)
    path = tmp_path / "company.csv"
    path.write_bytes(csv_bytes(rows, synced))
    assert scraper.is_new_content(path, ignore_columns=scraper.volatile_columns) is new
