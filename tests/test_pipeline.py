"""Step order and watermark statuses of BaseScraper, with the SQL steps and
the watermark table replaced by in-memory fakes."""

import pytest

from scrapers import base
from storage import datasets


class FakeScraper(base.BaseScraper):
    source = "npd"
    dataset = "field_production_monthly"
    new_data = True

    def download_full(self):
        self.save_watermark(load_mode="full", last_period_fetched="2026-08", status="raw", raw_file="k1")

    def download_incremental(self):
        if not self.new_data:
            return False
        self.save_watermark(load_mode="incremental", last_period_fetched="2026-09", status="raw", raw_file="k2")
        return True


@pytest.fixture
def run(monkeypatch):
    """Patch the steps; return (scraper, calls, watermark rows)."""
    calls, rows = [], []
    monkeypatch.setattr(base, "read_watermark", lambda s, d: dict(rows[-1]) if rows else {})
    monkeypatch.setattr(base, "write_watermark", lambda s, d, **f: rows.append(f))
    monkeypatch.setattr(base.std, "standardize", lambda s, d, key: calls.append(("std", key)))
    monkeypatch.setattr(base.std, "standardize_all", lambda s, d: calls.append(("std_all",)))
    monkeypatch.setattr(base.lake, "load", lambda s, t, mode: calls.append(("lake", t, mode)))
    return FakeScraper(client=None), calls, rows


def test_tables_of_a_tabular_dataset():
    assert datasets.tables("npd_field_production_monthly") == ["npd_field_production_monthly"]
    with pytest.raises(KeyError):
        datasets.tables("npd_unknown")


def test_tables_of_a_flattened_dataset(monkeypatch):
    rows = {
        "x_doc": {"code": "x_doc", "keys": "", "parent_code": ""},
        "x_doc_wells": {"code": "x_doc_wells", "keys": "parent, well", "parent_code": "x_doc_fields"},
        "x_doc_fields": {"code": "x_doc_fields", "keys": "field", "parent_code": "x_doc"},
        "y_other": {"code": "y_other", "keys": "id", "parent_code": ""},
    }
    monkeypatch.setattr(datasets, "_rows", lambda: rows)
    assert datasets.tables("x_doc") == ["x_doc_fields", "x_doc_wells"]


def test_full(run):
    scraper, calls, rows = run
    scraper.full_load()
    assert calls == [("std_all",), ("lake", "field_production_monthly", "full")]
    assert [r["status"] for r in rows] == ["raw", "std", "lake"]
    assert {r["raw_file"] for r in rows} == {"k1"}


def test_incremental(run):
    scraper, calls, rows = run
    scraper.incremental_load()
    assert calls == [("std", "k2"), ("lake", "field_production_monthly", "incremental")]
    assert [r["status"] for r in rows] == ["raw", "std", "lake"]


def test_incremental_without_new_data_does_nothing(run):
    scraper, calls, rows = run
    scraper.new_data = False
    scraper.incremental_load()
    assert calls == [] and rows == []


@pytest.mark.parametrize("status, expected", [
    ("raw", [("std", "k0"), ("lake", "field_production_monthly", "incremental")]),
    ("std", [("lake", "field_production_monthly", "incremental")]),
    ("lake", []),
    ("ok", []),
])
def test_incremental_finishes_a_pending_file_first(run, status, expected):
    scraper, calls, rows = run
    scraper.new_data = False
    rows.append({"load_mode": "incremental", "last_period_fetched": "2026-07", "status": status, "raw_file": "k0"})
    scraper.incremental_load()
    assert calls == expected
    assert rows[-1]["status"] in ("lake", "ok")
