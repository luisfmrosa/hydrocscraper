"""
Row digests used for change detection.

md5_digest = MD5 of the record's values concatenated in a fixed field order:
  - None      -> ''
  - list/tuple -> items joined with ','
  - other     -> str(value)
Values are separated by the ASCII unit separator (\\x1f) so that
('a', 'bc') and ('ab', 'c') produce different digests.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence

SEPARATOR = "\x1f"


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ",".join(_as_text(v) for v in value)
    return str(value)


def row_md5(record: Mapping, fields: Sequence[str]) -> str:
    """Return the hex MD5 of *record*'s *fields*, in the given order."""
    payload = SEPARATOR.join(_as_text(record.get(f)) for f in fields)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()
