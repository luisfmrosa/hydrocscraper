"""Step order and watermark statuses of BaseScraper, with the SQL steps and
the watermark table replaced by in-memory fakes."""

import pytest

from scrapers import base
from storage import datasets, std


class FakeScraper(base.BaseScraper):
    source = "no_sodir"
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
    monkeypatch.setattr(base.std, "standardize_all",
                        lambda s, d, tables, rebuild=False: calls.append(("std_all", tuple(tables), rebuild)))
    monkeypatch.setattr(base.lake, "load", lambda s, t, mode: calls.append(("lake", t, mode)))
    return FakeScraper(client=None), calls, rows


def test_tables_of_a_tabular_dataset():
    assert datasets.tables("no_sodir_field_production_monthly") == ["no_sodir_field_production_monthly"]
    with pytest.raises(KeyError):
        datasets.tables("no_sodir_unknown")


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
    assert calls == [
        ("std_all", ("field_production_monthly",), False),
        ("lake", "field_production_monthly", "full"),
    ]
    assert [r["status"] for r in rows] == ["raw", "std", "lake"]
    assert {r["raw_file"] for r in rows} == {"k1"}


def test_full_rebuild_std(run):
    scraper, calls, rows = run
    scraper.full_load(rebuild_std=True)
    assert calls[0] == ("std_all", ("field_production_monthly",), True)


def test_std_path_keeps_raw_period_and_timestamp():
    raw = "s3://hydroc-raw/no_sodir/field_production_monthly/year_month=2026-09/field_production_monthly_20260929_1000.csv"
    assert std.std_path("no_sodir", "field_production_monthly", raw) == (
        "s3://hydroc-std/no_sodir/field_production_monthly/year_month=2026-09/"
        "no_sodir_field_production_monthly_20260929_1000.parquet"
    )
    assert std.std_path("x", "doc_wells", raw).endswith("/x/doc_wells/year_month=2026-09/x_doc_wells_20260929_1000.parquet")
    with pytest.raises(ValueError):
        std.std_path("no_sodir", "t", "s3://hydroc-raw/no_sodir/t/no_partition.csv")


def test_standardize_all_skips_converted_files(monkeypatch):
    raw = "s3://hydroc-raw/no_sodir/t/year_month=2026-0{m}/t_2026010{m}_1000.csv"
    files = [raw.format(m=m) for m in (1, 2, 3)]
    ran = []
    monkeypatch.setattr(std, "std_scripts", lambda s, d: ["raw_view", "std_script"])
    monkeypatch.setattr(std.scripts, "run", lambda path, variables=None: ran.append((path, variables)))
    monkeypatch.setattr(std, "raw_files", lambda s, d: files)
    monkeypatch.setattr(std, "std_files", lambda s, tables: {std.std_path("no_sodir", "t", files[0])})

    assert std.standardize_all("no_sodir", "t", ["t"]) == 2
    assert [v["raw_file"] for p, v in ran if p == "std_script"] == files[1:]

    ran.clear()
    assert std.standardize_all("no_sodir", "t", ["t"], rebuild=True) == 3


def test_is_new_content(run, tmp_path, monkeypatch):
    scraper, calls, rows = run
    path = tmp_path / "f.csv"
    path.write_bytes(b"a,b\n1,2\n")
    assert scraper.is_new_content(path)                     # no watermark yet
    rows.append({"load_mode": "full", "last_period_fetched": "2026-07", "status": "lake", "raw_file": "k0"})
    monkeypatch.setattr(base.s3, "get_bytes", lambda key: b"a,b\n1,2\n")
    assert not scraper.is_new_content(path)
    monkeypatch.setattr(base.s3, "get_bytes", lambda key: b"a,b\n1,3\n")
    assert scraper.is_new_content(path)


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
