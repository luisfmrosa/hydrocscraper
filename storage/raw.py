"""
Raw storage layer.

Files are stored exactly as received in the hydroc-raw bucket:
  <source>/<dataset>/year_month=<YYYY-MM>/<stem>_<YYYYMMDD_HHmm><ext>

`year_month` defaults to the (UTC) month of the download; a scraper may pass
the reference period instead when the source publishes one file per period.

No parsing happens here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from config import TIMESTAMP_FORMAT
from storage import s3


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(ts: datetime | None = None) -> str:
    """Return *ts* (default: now, UTC) formatted as YYYYMMDD_HHmm."""
    return (ts or utc_now()).strftime(TIMESTAMP_FORMAT)


def raw_key(
    source: str,
    dataset: str,
    filename: str,
    period: str | None = None,
    ts: datetime | None = None,
) -> str:
    """Build the Raw-layer object key for *filename*.

    period — 'YYYY-MM'; defaults to the month of *ts*.
    ts     — download time; defaults to now (UTC).
    """
    ts = ts or utc_now()
    period = period or ts.strftime("%Y-%m")
    name = PurePosixPath(filename)
    stamped = f"{name.stem}_{timestamp(ts)}{name.suffix}"
    return f"{source}/{dataset}/year_month={period}/{stamped}"


def upload_raw(
    local_path: Path, source: str, dataset: str, period: str | None = None
) -> str:
    """Upload *local_path* to the Raw bucket and return its key."""
    key = raw_key(source, dataset, local_path.name, period=period)
    s3.put_file(local_path, key)
    return key
