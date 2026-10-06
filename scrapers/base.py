"""
Abstract base class for all hydrocscraper scrapers.

One scraper class per source and dataset. Each concrete class must:
  - declare `source` (e.g. "npd") and `dataset` (e.g. "field_production_monthly");
    their code `<source>_<dataset>` is the dataset's `code` in
    data/static/datasets.csv and its key in config.SCRAPER_REGISTRY
  - implement `download_full()` — fetch the complete dataset into Raw
  - implement `download_incremental()` — fetch only if there is new data;
    return True when something was stored
  - store, as received, only what DuckDB can read; for a format it can't read
    (e.g. .xls, HTML) also store a Parquet conversion with store_table(),
    under the same timestamp, and put that key in the watermark

Python only collects data. The base class then runs the static SQL steps on
the DuckDB server (storage/std.py, storage/lake.py):

  full:        download_full()        -> Std for every Raw file without it
                                         (every Raw file with rebuild_std)
                                      -> Lake full load of every table (replays
                                         every Std file: keeps the change history)
  incremental: download_incremental() -> Std from the watermark's Raw file
                                      -> Lake incremental load of every table

The watermark (hook.metadata.watermark, append-only) records each step:
status 'raw' after the download, 'std' after the Std step, 'lake' when done.
An incremental run first finishes a file left at 'raw' or 'std'.

Helpers:
  - a shared httpx.Client
  - `fetch_to_temp()` — streamed, retried download into a temporary directory
  - `store_raw()` / `store_table()` — upload a file / a table (as Parquet) to Raw
  - `is_new_content()` — whether a download differs from the watermark's file
  - watermark read/write helpers
  - standard logging
"""

import hashlib
import logging
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from storage import datasets, lake, s3, std
from storage.raw import upload_raw
from storage.watermark import DONE, read_watermark, write_watermark
from utils.http import download_file as _download_file


class BaseScraper(ABC):
    source: str   # Must be set on each concrete subclass
    dataset: str  # Must be set on each concrete subclass

    def __init__(self, client: httpx.Client) -> None:
        self.client = client
        self.logger = logging.getLogger(f"hydrocscraper.{self.code}")

    @property
    def code(self) -> str:
        return f"{self.source}_{self.dataset}"

    @property
    def tables(self) -> list[str]:
        """Std/Lake tables fed by this dataset, without the source prefix."""
        prefix = f"{self.source}_"
        return [code.removeprefix(prefix) for code in datasets.tables(self.code)]

    # ------------------------------------------------------------------
    # Interface — implemented by subclasses
    # ------------------------------------------------------------------

    @abstractmethod
    def download_full(self) -> None:
        """Download the complete dataset into Raw and write a watermark."""

    @abstractmethod
    def download_incremental(self) -> bool:
        """Download new data into Raw and write a watermark, if there is any.

        Returns True when a file was stored.
        """

    # ------------------------------------------------------------------
    # Modes
    # ------------------------------------------------------------------

    def full_load(self, rebuild_std: bool = False) -> None:
        self.download_full()
        std.standardize_all(self.source, self.dataset, self.tables, rebuild=rebuild_std)
        self._advance("std")
        for table in self.tables:
            lake.load(self.source, table, "full")
        self._advance("lake")

    def incremental_load(self) -> None:
        self._finish_pending()
        if self.download_incremental():
            self._finish_pending()

    def _finish_pending(self) -> None:
        """Run the steps the latest watermark's file is still missing."""
        wm = self.watermark
        if not wm or wm["status"] in DONE:
            return
        if wm["status"] == "raw":
            std.standardize(self.source, self.dataset, wm["raw_file"])
            self._advance("std")
        for table in self.tables:
            lake.load(self.source, table, "incremental")
        self._advance("lake")

    def _advance(self, status: str) -> None:
        """Append a copy of the latest watermark with a new status."""
        wm = self.watermark
        self.save_watermark(
            load_mode=wm["load_mode"],
            last_period_fetched=wm["last_period_fetched"],
            status=status,
            raw_file=wm["raw_file"],
        )

    # ------------------------------------------------------------------
    # Helpers available to subclasses
    # ------------------------------------------------------------------

    @contextmanager
    def fetch_to_temp(self, url: str, filename: str, **request_kwargs) -> Iterator[Path]:
        """Download *url* to a temporary file named *filename*.

        The file (and its directory) is removed when the context exits, so
        call store_raw() inside the `with` block to keep it.
        """
        with tempfile.TemporaryDirectory(prefix=f"hydroc_{self.code}_") as tmp:
            dest = Path(tmp) / filename
            _download_file(self.client, url, dest, **request_kwargs)
            yield dest

    def store_raw(self, path: Path, period: str | None = None, ts: datetime | None = None) -> str:
        """Upload *path* to the Raw bucket; return its object key."""
        return upload_raw(path, self.source, self.dataset, period=period, ts=ts)

    def store_table(
        self, table, name: str, period: str | None = None, ts: datetime | None = None
    ) -> str:
        """Upload *table* (pyarrow Table or pandas DataFrame) to Raw as
        <name>.parquet; return its key.

        Use it for a Parquet conversion of a file DuckDB can't read (same *ts*
        as the original) or for data extracted from an API or a database.
        Keep the values as received: typing and checks belong to the Std SQL.
        """
        if not isinstance(table, pa.Table):
            table = pa.Table.from_pandas(table, preserve_index=False)
        with tempfile.TemporaryDirectory(prefix=f"hydroc_{self.code}_") as tmp:
            path = Path(tmp) / f"{name}.parquet"
            pq.write_table(table, path)
            return self.store_raw(path, period=period, ts=ts)

    def is_new_content(self, path: Path) -> bool:
        """True unless *path* has the same bytes as the watermark's Raw file.

        For sources that republish a whole snapshot: revisions of past periods
        change the file without changing its latest period.
        """
        key = self.watermark.get("raw_file")
        if not key:
            return True
        return _md5(path.read_bytes()) != _md5(s3.get_bytes(key))

    @property
    def watermark(self) -> dict:
        return read_watermark(self.source, self.dataset)

    def save_watermark(self, **fields) -> None:
        write_watermark(self.source, self.dataset, **fields)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} code={self.code!r}>"


def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()
