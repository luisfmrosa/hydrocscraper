"""The Sodir raw view, Std script, std view, Lake DDL and load scripts (the real
SQL files) on a local DuckDB. CSV snapshots are written to a temporary folder
laid out like the Raw bucket; s3://hydroc-raw/ and s3://hydroc-std/ in the
scripts are pointed at local folders.
"""

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from storage import lake, std

ROOT = Path(__file__).resolve().parents[1]
DDL = ROOT / "sql" / "ddl"
HEADER = (
    "prfInformationCarrier,prfYear,prfMonth,prfPrdOilNetMillSm3,prfPrdGasNetBillSm3,"
    "prfPrdNGLNetMillSm3,prfPrdCondensateNetMillSm3,prfPrdOeNetMillSm3,"
    "prfPrdProducedWaterInFieldMillSm3,prfNpdidInformationCarrier"
)
PREFIX = "no_sodir/field_production_monthly/"
F1 = PREFIX + "year_month=2026-01/field_production_monthly_20260101_1000.csv"
F2 = PREFIX + "year_month=2026-02/field_production_monthly_20260201_1000.csv"
F3 = PREFIX + "year_month=2026-03/field_production_monthly_20260301_1000.csv"

# (field, year, month, oil, npdid) per file; other production columns fixed
SNAPSHOTS = {
    F1: [("EKOFISK", 2025, 1, 1.0, 43506), ("TROLL", 2025, 1, 2.0, 46437), ("GULLFAKS", 2025, 1, 3.0, 43686)],
    # EKOFISK unchanged, TROLL changed, GULLFAKS removed, OSEBERG new
    F2: [("EKOFISK", 2025, 1, 1.0, 43506), ("TROLL", 2025, 1, 20.0, 46437), ("OSEBERG", 2025, 1, 4.0, 43625)],
    # GULLFAKS comes back unchanged; the rest as in F2
    F3: [("EKOFISK", 2025, 1, 1.0, 43506), ("TROLL", 2025, 1, 20.0, 46437),
         ("GULLFAKS", 2025, 1, 3.0, 43686), ("OSEBERG", 2025, 1, 4.0, 43625)],
}


@pytest.fixture
def raw(tmp_path):
    """Write the snapshots; return the local folder standing in for the bucket."""
    for key, rows in SNAPSHOTS.items():
        path = tmp_path / key
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [HEADER] + [f"{f},{y},{m},{oil},0.5,0,0,1.5,0.1,{npdid}" for f, y, m, oil, npdid in rows]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp_path


class Env:
    """A local connection plus the folders standing in for the Raw and Std buckets."""

    def __init__(self, db, bucket, std_bucket):
        self.db, self.bucket, self.std_bucket = db, bucket, std_bucket

    def execute(self, *args):
        return self.db.execute(*args)


@pytest.fixture
def con(raw, tmp_path_factory):
    std_dir = tmp_path_factory.mktemp("std")
    con = Env(duckdb.connect(), raw.as_posix() + "/", std_dir.as_posix() + "/")
    for layer in ("lake", "hook"):
        con.execute(f"ATTACH ':memory:' AS {layer}")
    for path in (DDL / "40_hook.sql", DDL / "41_hook_watermark.sql", std.std_scripts("no_sodir", "field_production_monthly")[0]):
        run(con, path)
    # The Std step, file by file (as standardize_all does)
    for key in SNAPSHOTS:
        # COPY to a local path needs the folder; S3 doesn't
        (std_dir / std_key(key)).parent.mkdir(parents=True, exist_ok=True)
        run(con, std.std_scripts("no_sodir", "field_production_monthly")[1], {"raw_file": con.bucket + key})
    for path in lake.lake_scripts("no_sodir", "field_production_monthly", "full")[:2]:
        run(con, path)
    return con


def std_key(raw_key):
    """Std key of a Raw key of this dataset (same year_month and timestamp)."""
    folder, name = raw_key.rsplit("/", 1)
    ts = name.rsplit("_", 2)[-2] + "_" + name.rsplit("_", 1)[-1].split(".")[0]
    return folder + "/no_sodir_field_production_monthly_" + ts + ".parquet"


def run(con, path, variables=None):
    sql = path.read_text(encoding="utf-8")
    sql = sql.replace("s3://hydroc-raw/", con.bucket).replace("s3://hydroc-std/", con.std_bucket)
    for name, value in (variables or {}).items():
        con.execute(f"SET VARIABLE {name} = ?", [value])
    return con.execute(sql).fetchall()


def load(con, mode):
    return run(con, lake.lake_scripts("no_sodir", "field_production_monthly", mode)[2])[0][0]


def watermark(con, key, day):
    con.execute(
        "INSERT INTO hook.metadata.watermark (source, dataset, load_mode, raw_file, status, updated_at) "
        "VALUES ('no_sodir', 'field_production_monthly', 'incremental', ?, 'ok', ?)",
        [key, datetime(2026, 4, day, tzinfo=timezone.utc)],
    )


def changes(con, key):
    return sorted(con.execute(
        "SELECT prfInformationCarrier, prfPrdOilNetMillSm3, ___Lake_isdeleted "
        "FROM lake.no_sodir.field_production_monthly WHERE ___Lake_sourcefile = ?",
        [con.std_bucket + std_key(key)],
    ).fetchall())


def lake_rows(con):
    return sorted(con.execute(
        "SELECT * EXCLUDE (___Lake_sourcefile) FROM lake.no_sodir.field_production_monthly"
    ).fetchall())


def test_scripts_resolve():
    assert [p.relative_to(ROOT).as_posix() for p in std.std_scripts("no_sodir", "field_production_monthly")] == [
        "sql/ddl/raw_views/020_no_sodir_field_production_monthly.sql",
        "sql/std/no_sodir/field_production_monthly.sql",
    ]
    assert [p.relative_to(ROOT).as_posix() for p in lake.lake_scripts("no_sodir", "field_production_monthly", "incremental")] == [
        "sql/ddl/std_views/020_no_sodir_field_production_monthly.sql",
        "sql/ddl/lake/no_sodir_field_production_monthly.sql",
        "sql/lake/no_sodir/field_production_monthly_incremental.sql",
    ]
    with pytest.raises(ValueError):
        lake.lake_scripts("no_sodir", "field_production_monthly", "weekly")


def test_raw_view_metadata_columns(con):
    row = con.execute(
        "SELECT ___Raw_filename, ___Raw_year_month, ___Raw_file_timestamp "
        "FROM hook.raw_views.no_sodir_field_production_monthly WHERE ___Raw_filename LIKE '%20260201_1000.csv' LIMIT 1"
    ).fetchone()
    assert row[0] == con.bucket + F2
    assert row[1] == "2026-02"
    assert row[2] == datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)


def test_std_writes_one_typed_file_per_raw_file(con):
    for key, rows in SNAPSHOTS.items():
        written = con.execute(f"FROM read_parquet('{con.std_bucket + std_key(key)}')").fetchall()
        assert len(written) == len(rows)
    types = dict(con.execute(
        f"SELECT column_name, column_type FROM (DESCRIBE FROM read_parquet('{con.std_bucket + std_key(F1)}'))"
    ).fetchall())
    assert types["prfNpdidInformationCarrier"] == "BIGINT"
    assert types["prfYear"] == "INTEGER"
    assert types["prfPrdOilNetMillSm3"] == "DOUBLE"


def test_std_fails_on_schema_change(con, raw):
    # Sodir renames a column: without the check it would silently become NULL
    key = PREFIX + "year_month=2026-04/field_production_monthly_20260401_1000.csv"
    path = raw / key
    path.parent.mkdir(parents=True, exist_ok=True)
    header = HEADER.replace("prfPrdOilNetMillSm3", "prfPrdOilNetMillSm3_v2") + ",prfNewColumn"
    path.write_text(header + "\nEKOFISK,2025,1,1.0,0.5,0,0,1.5,0.1,43506,x\n", encoding="utf-8")
    (Path(con.std_bucket) / std_key(key)).parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(duckdb.Error, match="missing: prfPrdOilNetMillSm3; unexpected: prfNewColumn, prfPrdOilNetMillSm3_v2"):
        run(con, std.std_scripts("no_sodir", "field_production_monthly")[1], {"raw_file": con.bucket + key})


def test_std_view_metadata_columns(con):
    row = con.execute(
        "SELECT ___Std_filename, ___Std_year_month, ___Std_file_timestamp "
        "FROM hook.std_views.no_sodir_field_production_monthly WHERE ___Std_filename LIKE '%20260201_1000.parquet' LIMIT 1"
    ).fetchone()
    assert row[0] == con.std_bucket + std_key(F2)
    assert row[1] == "2026-02"
    assert row[2] == datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)


def test_std_md5_ignores_key_columns(con):
    # EKOFISK in F1 and F2: same values -> same digest; changing only a key would
    # not change it either, since keys are not part of the digest
    md5s = con.execute(
        "SELECT DISTINCT ___Std_md5 FROM hook.std_views.no_sodir_field_production_monthly "
        "WHERE prfInformationCarrier = 'EKOFISK'"
    ).fetchall()
    assert len(md5s) == 1


def test_full_replays_files_oldest_first(con):
    assert load(con, "full") == 7
    assert changes(con, F1) == [("EKOFISK", 1.0, False), ("GULLFAKS", 3.0, False), ("TROLL", 2.0, False)]
    # changed, deleted (last known values) and new
    assert changes(con, F2) == [("GULLFAKS", 3.0, True), ("OSEBERG", 4.0, False), ("TROLL", 20.0, False)]
    # a deleted key that comes back is new again, even unchanged
    assert changes(con, F3) == [("GULLFAKS", 3.0, False)]


def test_full_rerun_truncates(con):
    load(con, "full")
    assert load(con, "full") == 7
    assert con.execute("SELECT count(*) FROM lake.no_sodir.field_production_monthly").fetchone()[0] == 7


def test_incremental_matches_full(con):
    for day, (key, expected) in enumerate(((F1, 3), (F2, 3), (F3, 1)), start=1):
        watermark(con, key, day)
        assert load(con, "incremental") == expected
    incremental = lake_rows(con)
    load(con, "full")
    assert lake_rows(con) == incremental


def test_incremental_rerun_and_older_file_add_nothing(con):
    load(con, "full")
    watermark(con, F3, 1)
    assert load(con, "incremental") == 0     # same file again
    watermark(con, F1, 2)
    assert load(con, "incremental") == 0     # older than the Lake's latest load
    assert con.execute("SELECT count(*) FROM lake.no_sodir.field_production_monthly").fetchone()[0] == 7
