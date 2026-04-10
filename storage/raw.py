"""
Raw storage layer (Layer 0).

Manages the ./data/ directory tree:
  data/{source_id}/full/{YYYY-MM-DD}/   — full-load snapshots
  data/{source_id}/incremental/{YYYY-MM}/  — incremental periods
  data/{source_id}/.watermark.json       — incremental state

No parsing happens here — files are stored exactly as received.
"""

import json
import logging
from datetime import date, datetime
from pathlib import Path

from config import DATA_ROOT

logger = logging.getLogger(__name__)


def full_dir(source_id: str, run_date: date | None = None) -> Path:
    """Return the directory for a full-load run.

    run_date defaults to today.
    """
    d = run_date or date.today()
    return DATA_ROOT / source_id / "full" / d.isoformat()


def incremental_dir(source_id: str, period: str) -> Path:
    """Return the directory for an incremental period.

    period — reference month in 'YYYY-MM' format.
    """
    return DATA_ROOT / source_id / "incremental" / period


def read_watermark(source_id: str) -> dict:
    path = DATA_ROOT / source_id / ".watermark.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Corrupt watermark for %s, treating as empty.", source_id)
        return {}


def write_watermark(source_id: str, updates: dict) -> None:
    """Merge *updates* into the existing watermark and persist."""
    path = DATA_ROOT / source_id / ".watermark.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    current = read_watermark(source_id)
    current.update(updates)
    current["source"] = source_id
    current["updated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    logger.debug("Watermark updated for %s: %s", source_id, current)


def latest_full_dir(source_id: str) -> Path | None:
    """Return the most recent full-load directory for a source, or None."""
    base = DATA_ROOT / source_id / "full"
    if not base.exists():
        return None
    runs = sorted(base.iterdir(), reverse=True)
    return runs[0] if runs else None
