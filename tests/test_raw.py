from datetime import datetime, timezone

from storage.raw import raw_key, timestamp

TS = datetime(2026, 9, 29, 10, 5, tzinfo=timezone.utc)


def test_timestamp_format():
    assert timestamp(TS) == "20260929_1005"


def test_raw_key_defaults_period_to_download_month():
    key = raw_key("no_sodir", "field_production_monthly", "field_production_monthly.csv", ts=TS)
    assert key == (
        "no_sodir/field_production_monthly/year_month=2026-09/"
        "field_production_monthly_20260929_1005.csv"
    )


def test_raw_key_explicit_period():
    key = raw_key("anp", "fields", "producao.xlsx", period="2026-07", ts=TS)
    assert key == "anp/fields/year_month=2026-07/producao_20260929_1005.xlsx"
