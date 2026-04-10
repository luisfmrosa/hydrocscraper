"""
Abstract base class for all hydrocscraper scrapers.

Each scraper must:
  - declare a unique `source_id` class attribute
  - implement `full_load()` — downloads complete history
  - implement `incremental_load()` — downloads only new/updated periods
  - implement `parse(path)` — converts a raw file to ProductionRecord objects

The base class provides:
  - a shared httpx.Client
  - `download_file()` convenience wrapper (streamed, retried)
  - watermark read/write helpers
  - `latest_raw_file()` — resolves the most recent raw file for convert mode
  - standard logging
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from storage.raw import latest_full_dir, read_watermark, write_watermark
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

    def download_file(self, url: str, dest: Path, **request_kwargs) -> None:
        """Stream *url* to *dest* with retries. See utils.http for details."""
        _download_file(self.client, url, dest, **request_kwargs)

    def latest_raw_files(self) -> list[Path]:
        """Return a list of raw files from the most recent full-load run.

        Subclasses may override this if their raw output is more complex
        (e.g. multiple files per run). The default looks in the latest
        full/ snapshot directory.
        """
        d = latest_full_dir(self.source_id)
        if d is None or not d.exists():
            return []
        return [p for p in d.iterdir() if p.is_file()]

    @property
    def watermark(self) -> dict:
        return read_watermark(self.source_id)

    def save_watermark(self, updates: dict) -> None:
        write_watermark(self.source_id, updates)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} source_id={self.source_id!r}>"
