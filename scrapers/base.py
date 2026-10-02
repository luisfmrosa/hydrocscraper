"""
Abstract base class for all hydrocscraper scrapers.

Each scraper must:
  - declare a unique `source_id` class attribute
  - implement `full_load()` — downloads complete history
  - implement `incremental_load()` — downloads only new/updated periods
  - implement `parse(path)` — converts a raw file to ProductionRecord objects

The base class provides:
  - a shared httpx.Client
  - `fetch_to_temp()` — streamed, retried download into a temporary directory
  - `store_raw()` — upload a downloaded file to the Raw bucket
  - watermark read/write helpers (hook.metadata.watermark)
  - standard logging
"""

import logging
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx

from storage.raw import upload_raw
from storage.watermark import read_watermark, write_watermark
from utils.http import download_file as _download_file


class BaseScraper(ABC):
    source_id: str  # Must be set on each concrete subclass

    def __init__(self, client: httpx.Client) -> None:
        self.client = client
        self.logger = logging.getLogger(f"hydrocscraper.{self.source_id}")

    # ------------------------------------------------------------------
    # Interface — all three must be implemented by subclasses
    # ------------------------------------------------------------------

    @abstractmethod
    def full_load(self) -> None:
        """Download the complete production history for this source."""

    @abstractmethod
    def incremental_load(self) -> None:
        """Download only periods not yet captured since the last run."""

    @abstractmethod
    def parse(self, path: Path) -> list:
        """Parse a raw file at *path* into a list of ProductionRecord objects."""

    # ------------------------------------------------------------------
    # Helpers available to subclasses
    # ------------------------------------------------------------------

    @contextmanager
    def fetch_to_temp(self, url: str, filename: str, **request_kwargs) -> Iterator[Path]:
        """Download *url* to a temporary file named *filename*.

        The file (and its directory) is removed when the context exits, so
        call store_raw() inside the `with` block to keep it.
        """
        with tempfile.TemporaryDirectory(prefix=f"hydroc_{self.source_id}_") as tmp:
            dest = Path(tmp) / filename
            _download_file(self.client, url, dest, **request_kwargs)
            yield dest

    def store_raw(self, path: Path, dataset: str, period: str | None = None) -> str:
        """Upload *path* to the Raw bucket; return its object key."""
        return upload_raw(path, self.source_id, dataset, period=period)

    def watermark(self, dataset: str) -> dict:
        return read_watermark(self.source_id, dataset)

    def save_watermark(self, dataset: str, **fields) -> None:
        write_watermark(self.source_id, dataset, **fields)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} source_id={self.source_id!r}>"
