"""
Static dataset metadata (data/static/datasets.csv), read by the app to know
which Std/Lake tables a downloaded dataset feeds.

One row per Std/Lake table. A tabular dataset is one row with keys. A
non-tabular dataset is one row without keys (no table of its own) plus one row
per flattened sub-table, linked to it through `parent_code` (a nested
sub-table points at the sub-table its `parent` column refers to).
"""

from __future__ import annotations

import csv
from functools import lru_cache

from config import PROJECT_ROOT

DATASETS_CSV = PROJECT_ROOT / "data" / "static" / "datasets.csv"


@lru_cache(maxsize=1)
def _rows() -> dict[str, dict]:
    with DATASETS_CSV.open(encoding="utf-8", newline="") as fh:
        return {row["code"]: row for row in csv.DictReader(fh)}


def tables(code: str) -> list[str]:
    """Codes of the Std/Lake tables fed by dataset *code*, parents first."""
    rows = _rows()
    if code not in rows:
        raise KeyError(f"Dataset '{code}' is not in {DATASETS_CSV.name}")

    result: list[str] = []
    pending = [code]
    while pending:
        current = pending.pop(0)
        if rows[current]["keys"].strip():
            result.append(current)
        pending.extend(c for c, row in rows.items() if row["parent_code"] == current)
    if not result:
        raise ValueError(f"Dataset '{code}' has no row with keys in {DATASETS_CSV.name}")
    return result
