from scrapers.npd import _latest_period_in_file


def test_latest_period_in_file(tmp_path):
    csv = tmp_path / "f.csv"
    csv.write_text(
        "\ufeffprfInformationCarrier,prfYear,prfMonth\n"
        "EKOFISK,2025,12\n"
        "EKOFISK,2026,7\n"
        "TROLL,2026,3\n"
        "BAD,,\n",
        encoding="utf-8",
    )
    assert _latest_period_in_file(csv) == "2026-07"


def test_latest_period_empty(tmp_path):
    csv = tmp_path / "f.csv"
    csv.write_text("prfYear,prfMonth\n", encoding="utf-8")
    assert _latest_period_in_file(csv) is None
