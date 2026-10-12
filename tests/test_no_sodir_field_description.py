"""The Sodir field descriptions dataset end to end on a local DuckDB, with the
real SQL files: raw view, Std script, std view, Lake DDL and loads, Library
views (development and production). Plus the scraper. CSV snapshots are
written like Sodir's export (BOM, CRLF, trailing blank line, dd.mm.yyyy, quoted
texts with commas, doubled quotes and line breaks). One row per field and
heading:

  D1 (Jan): TROLL Status and Transport, SNORRE Status
  D2 (Feb): the export date moved; TROLL Status otherwise unchanged, TROLL
            Transport rewritten, SNORRE Status gone, SNORRE Transport new
  D3 (Mar): as D2 with a new export date, SNORRE Status back
"""

from datetime import date, datetime, timezone

import duckdb
import pytest

import sodir_tableview as st
from scrapers import base
from scrapers.no_sodir.field_description import NoSodirFieldDescription
from storage import lake, std
from test_lake import DDL

DATASET = "field_description"
HEADER = "fldName,fldDescriptionHeading,fldDescriptionText,fldNpdidField,fldDescriptionDateUpdated,DatesyncNPD"
D1, D2, D3 = (st.raw_key(DATASET, m) for m in (1, 2, 3))
FIELDS = {"TROLL": 46437, "SNORRE": 43718}
TROLL_STATUS = 'Troll is producing.\n\nThe "Troll B" platform, which stays in use, was upgraded.'
TROLL_TRANSPORT = "Gas is piped to Kollsnes, oil to Mongstad."
TROLL_TRANSPORT_2 = "Gas is piped to Kollsnes; oil goes to Mongstad."
SNORRE_STATUS = "Snorre is producing."
SNORRE_TRANSPORT = "Oil is piped to Statfjord."
# (field, heading, text, date updated) per file, and its export date
SNAPSHOTS = {
    D1: ([("TROLL", "Status", TROLL_STATUS, "08.05.2025"),
          ("TROLL", "Transport", TROLL_TRANSPORT, "08.05.2025"),
          ("SNORRE", "Status", SNORRE_STATUS, "20.02.2025")], "01.01.2026"),
    D2: ([("TROLL", "Status", TROLL_STATUS, "08.05.2025"),
          ("TROLL", "Transport", TROLL_TRANSPORT_2, "15.01.2026"),
          ("SNORRE", "Transport", SNORRE_TRANSPORT, "20.02.2025")], "01.02.2026"),
    D3: ([("TROLL", "Status", TROLL_STATUS, "08.05.2025"),
          ("TROLL", "Transport", TROLL_TRANSPORT_2, "15.01.2026"),
          ("SNORRE", "Status", SNORRE_STATUS, "20.02.2025"),
          ("SNORRE", "Transport", SNORRE_TRANSPORT, "20.02.2025")], "01.03.2026"),
}
FRAME, LATEST = "library.frame.no_sodir_field_description", "library.latest.no_sodir_field_description"
JAN, FEB, MAR = (datetime(2026, m, 1, 10, 0, tzinfo=timezone.utc) for m in (1, 2, 3))


def quoted(text):
    return '"' + text.replace('"', '""') + '"'


def csv_bytes(rows, synced):
    lines = [
        f"{field},{heading},{quoted(text)},{FIELDS[field]},{updated},{synced}"
        for field, heading, text, updated in rows
    ]
    return st.sodir_csv(HEADER, lines)


@pytest.fixture
def con(tmp_path_factory):
    files = {key: csv_bytes(rows, synced) for key, (rows, synced) in SNAPSHOTS.items()}
    return st.build(tmp_path_factory, DATASET, files)


def changes(con, key):
    return sorted(con.execute(
        f"SELECT fldName, fldDescriptionHeading, ___Lake_isdeleted FROM lake.no_sodir.{DATASET} "
        "WHERE ___Lake_sourcefile = ?", [con.std_bucket + st.std_key(DATASET, key)],
    ).fetchall())


def test_scripts_resolve():
    root = DDL.parents[1]
    assert [p.relative_to(root).as_posix() for p in std.std_scripts("no_sodir", DATASET)] == [
        "sql/ddl/raw_views/024_no_sodir_field_description.sql",
        "sql/std/no_sodir/field_description.sql",
    ]
    assert [p.relative_to(root).as_posix() for p in lake.lake_scripts("no_sodir", DATASET, "full")] == [
        "sql/ddl/std_views/024_no_sodir_field_description.sql",
        "sql/ddl/lake/no_sodir_field_description.sql",
        "sql/lake/no_sodir/field_description_full.sql",
    ]
    assert [p.name for p in lake.library_scripts("no_sodir", DATASET)] == [
        "no_sodir_field_description.sql", "no_sodir_field_description_dev.sql",
    ]


def test_std_types_and_text(con):
    parquet = f"read_parquet('{con.std_bucket + st.std_key(DATASET, D1)}')"
    written = con.execute(
        f"SELECT fldNpdidField, fldDescriptionHeading, fldDescriptionText, fldDescriptionDateUpdated, DatesyncNPD "
        f"FROM {parquet} ORDER BY 1, 2"
    ).fetchall()
    assert len(written) == 3     # the trailing blank line is no row
    # line breaks, commas and quotes survive
    assert written[1] == (46437, "Status", TROLL_STATUS, date(2025, 5, 8), date(2026, 1, 1))
    types = dict(con.execute(f"SELECT column_name, column_type FROM (DESCRIBE FROM {parquet})").fetchall())
    assert list(types)[:2] == ["fldNpdidField", "fldDescriptionHeading"]
    assert types["fldNpdidField"] == "BIGINT"
    assert types["fldDescriptionDateUpdated"] == "DATE"


def test_std_fails_on_schema_change(con):
    key = st.raw_key(DATASET, 4)
    st.write_raw(con, key, csv_bytes(SNAPSHOTS[D1][0], "01.04.2026").replace(b"DatesyncNPD", b"dateSyncNPD"))
    with pytest.raises(duckdb.Error, match="missing: DatesyncNPD; unexpected: dateSyncNPD"):
        st.run_std(con, DATASET, key)


def test_std_md5_ignores_the_export_date(con):
    # TROLL Status differs between files only by DatesyncNPD
    md5s = con.execute(
        "SELECT count(DISTINCT ___Std_md5), count(DISTINCT DatesyncNPD) "
        f"FROM hook.std_views.no_sodir_{DATASET} WHERE fldNpdidField = 46437 AND fldDescriptionHeading = 'Status'"
    ).fetchone()
    assert md5s == (1, 3)


def test_full_replays_files_oldest_first(con):
    assert st.load(con, DATASET, "full") == 7
    assert changes(con, D1) == [("SNORRE", "Status", False), ("TROLL", "Status", False),
                                ("TROLL", "Transport", False)]
    # the export date alone makes no row; changed, deleted and new do
    assert changes(con, D2) == [("SNORRE", "Status", True), ("SNORRE", "Transport", False),
                                ("TROLL", "Transport", False)]
    assert changes(con, D3) == [("SNORRE", "Status", False)]


def test_incremental_matches_full(con):
    for day, (key, expected) in enumerate(((D1, 3), (D2, 3), (D3, 1)), start=1):
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
            f"SELECT fldName, fldDescriptionHeading, fldDescriptionText FROM {LATEST}{suffix} ORDER BY 1, 2"
        ).fetchall()
        assert latest == [("SNORRE", "Status", SNORRE_STATUS), ("SNORRE", "Transport", SNORRE_TRANSPORT),
                          ("TROLL", "Status", TROLL_STATUS), ("TROLL", "Transport", TROLL_TRANSPORT_2)]
    versions = con.execute(
        f"SELECT ___Effective_From, CASE WHEN isfinite(___Effective_To) THEN ___Effective_To END, ___Is_Deleted "
        f"FROM {FRAME} WHERE fldNpdidField = 43718 AND fldDescriptionHeading = 'Status' ORDER BY 1"
    ).fetchall()
    assert versions == [(JAN, FEB, False), (FEB, MAR, True), (MAR, None, False)]


def test_hooks(con):
    st.load(con, DATASET, "full")
    st.library(con, DATASET)
    dev = dict(con.execute(f"SELECT DISTINCT fldNpdidField, HK_FIELD FROM {LATEST}_dev").fetchall())
    assert dev == {46437: "no_sodir.sup.field|TROLL", 43718: "no_sodir.sup.field|SNORRE"}
    # key_set_binary 0x080101, then the NPDID big-endian: 46437 = 0x0000B565,
    # 43718 = 0x0000AAC6; the same hook for every heading of a field
    prod = dict(con.execute(f"SELECT DISTINCT fldNpdidField, HK_FIELD FROM {LATEST}").fetchall())
    assert prod == {46437: bytes.fromhex("0801010000B565"), 43718: bytes.fromhex("0801010000AAC6")}


# --- the scraper ------------------------------------------------------------

def test_url_is_the_field_description_report():
    url = NoSodirFieldDescription(client=None).url
    assert "/tableview/field_description&" in url and "rs:Format=CSV" in url


@pytest.mark.parametrize("rows, synced, new", [
    (SNAPSHOTS[D1][0], "05.01.2026", False),                         # only the export date moved
    (SNAPSHOTS[D2][0], "01.01.2026", True),                          # texts changed
    (SNAPSHOTS[D1][0][:2], "01.01.2026", True),                      # a row removed
])
def test_is_new_content_ignores_the_export_date(monkeypatch, tmp_path, rows, synced, new):
    monkeypatch.setattr(base, "read_watermark", lambda s, d: {"raw_file": "prev"})
    monkeypatch.setattr(base.s3, "get_bytes", lambda key: csv_bytes(*SNAPSHOTS[D1]))
    scraper = NoSodirFieldDescription(client=None)
    path = tmp_path / "field_description.csv"
    path.write_bytes(csv_bytes(rows, synced))
    assert scraper.is_new_content(path, ignore_columns=scraper.volatile_columns) is new
