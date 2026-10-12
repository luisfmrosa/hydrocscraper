"""Shared setup for the tests of the Sodir table view datasets (snapshot CSVs):
write snapshots like Sodir's export, then run the dataset's real SQL files
(raw view, Std script, std view, Lake DDL and loads, Library views) on a local
DuckDB, with s3://hydroc-raw/ and s3://hydroc-std/ pointed at local folders.
"""

from pathlib import Path

import duckdb

from storage import lake, std
from test_lake import DDL, Env, run


def sodir_csv(header: str, lines: list[str]) -> bytes:
    """A CSV as Sodir exports it: UTF-8 with BOM, CRLF, a trailing blank line."""
    return ("﻿" + "\r\n".join([header] + lines) + "\r\n\r\n").encode("utf-8")


def raw_key(dataset: str, month: int) -> str:
    """Raw key of a snapshot downloaded on the 1st of <month> 2026 at 10:00."""
    return f"no_sodir/{dataset}/year_month=2026-{month:02d}/{dataset}_2026{month:02d}01_1000.csv"


def std_key(dataset: str, key: str) -> str:
    """Std key of a Raw key (same year_month and timestamp)."""
    folder, name = key.rsplit("/", 1)
    return f"{folder}/no_sodir_{dataset}_{name[len(dataset) + 1:-len('.csv')]}.parquet"


def write_raw(con: Env, key: str, data: bytes) -> None:
    path = Path(con.bucket) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def run_std(con: Env, dataset: str, key: str) -> None:
    """The Std step for one Raw file (COPY to a local path needs the folder)."""
    (Path(con.std_bucket) / std_key(dataset, key)).parent.mkdir(parents=True, exist_ok=True)
    run(con, std.std_scripts("no_sodir", dataset)[1], {"raw_file": con.bucket + key})


def build(tmp_path_factory, dataset: str, files: dict[str, bytes]) -> Env:
    """Write the snapshots, run the Std step for each and create the std view
    and Lake table. Returns the connection, Lake still empty."""
    raw = tmp_path_factory.mktemp("raw")
    std_dir = tmp_path_factory.mktemp("std")
    con = Env(duckdb.connect(), raw.as_posix() + "/", std_dir.as_posix() + "/")
    for layer in ("lake", "hook", "library"):
        con.execute(f"ATTACH ':memory:' AS {layer}")
    for path in (DDL / "20_library.sql", DDL / "40_hook.sql", DDL / "41_hook_watermark.sql"):
        run(con, path)
    for key, data in files.items():
        write_raw(con, key, data)
    run(con, std.std_scripts("no_sodir", dataset)[0])
    for key in files:
        run_std(con, dataset, key)
    for path in lake.lake_scripts("no_sodir", dataset, "full")[:2]:
        run(con, path)
    return con


def load(con: Env, dataset: str, mode: str) -> int:
    """Run the full or incremental Lake load; return the rows inserted."""
    return run(con, lake.lake_scripts("no_sodir", dataset, mode)[2])[0][0]


def library(con: Env, dataset: str) -> None:
    for path in lake.library_scripts("no_sodir", dataset):
        run(con, path)


def lake_rows(con: Env, dataset: str) -> list[tuple]:
    return con.execute(f"SELECT * EXCLUDE (___Lake_sourcefile) FROM lake.no_sodir.{dataset} ORDER BY ALL").fetchall()


def add_watermark(con: Env, dataset: str, key: str, day: int) -> None:
    """A watermark row pointing at <key>, as an incremental download leaves it."""
    con.execute(
        "INSERT INTO hook.metadata.watermark (source, dataset, load_mode, raw_file, status, updated_at) "
        f"VALUES ('no_sodir', '{dataset}', 'incremental', '{key}', 'ok', TIMESTAMPTZ '2026-04-{day:02d} 00:00:00+00')"
    )
