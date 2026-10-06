"""
Sodir (Norwegian Offshore Directorate, formerly NPD) FactPages — monthly field production.

Data: monthly field production — oil, gas, NGL, condensate, water
Source: https://factpages.sodir.no/en/field/TableView/Production/Saleable/Monthly
Format: CSV (SSRS ReportServer export)
Granularity: field level
Periodicity: monthly
Licence: NLOD (Norwegian Licence for Open Government Data)

Sodir publishes a single CSV containing the complete production history for all
fields. There is no incremental API endpoint, so both full and incremental
modes download the same file. Incremental mode only stores the file in the
Raw bucket if its content differs from the watermark's file: a new period,
or a revision of past ones (the export is byte-identical when nothing
changed).

CSV columns (English locale):
  prfInformationCarrier  — field name
  prfYear                — year (int)
  prfMonth               — month (int)
  prfNpdidInformationCarrier — NPDID of the field (numeric key)
  prfPrdOilNetMillSm3    — net oil production [mill Sm³]
  prfPrdGasNetBillSm3    — net gas production [bill Sm³]
  prfPrdNGLNetMillSm3    — net NGL [mill Sm³]
  prfPrdCondensateNetMillSm3 — net condensate [mill Sm³]
  prfPrdOeNetMillSm3     — net oil equivalents [mill Sm³]
  prfPrdProducedWaterInFieldMillSm3 — produced water [mill Sm³]

Tabular and readable by DuckDB: stored as received, then
sql/std/no_sodir/field_production_monthly.sql converts it to Std and the Lake
(lake.no_sodir.field_production_monthly) loads from Std, keyed by
prfNpdidInformationCarrier, prfYear, prfMonth (data/static/datasets.csv).
"""

import csv
from pathlib import Path

from scrapers.base import BaseScraper

_CSV_URL = (
    "https://factpages.sodir.no/public?/Factpages/external/tableview/"
    "field_production_monthly"
    "&rs:Command=Render"
    "&rc:Toolbar=false"
    "&rc:Parameters=f"
    "&IpAddress=not_used"
    "&CultureCode=en"
    "&rs:Format=CSV"
    "&Top100=false"
)


class NoSodirFieldProductionMonthly(BaseScraper):
    source = "no_sodir"
    dataset = "field_production_monthly"

    @property
    def filename(self) -> str:
        return f"{self.dataset}.csv"

    def download_full(self) -> None:
        self.logger.info("Full load: downloading Sodir field production CSV.")
        with self.fetch_to_temp(_CSV_URL, self.filename) as path:
            latest_period = _latest_period_in_file(path)
            key = self.store_raw(path)
        self.save_watermark(
            load_mode="full",
            last_period_fetched=latest_period,
            status="raw",
            raw_file=key,
        )
        self.logger.info("Download complete. Latest period in file: %s", latest_period)

    def download_incremental(self) -> bool:
        last_period = self.watermark.get("last_period_fetched")

        # Sodir always publishes the full dataset; compare it with the last
        # stored file to see whether anything changed.
        self.logger.info("Incremental load: downloading Sodir field production CSV.")
        with self.fetch_to_temp(_CSV_URL, self.filename) as path:
            latest_period = _latest_period_in_file(path)
            if not self.is_new_content(path):
                self.logger.info(
                    "No new data (file unchanged, latest period %s). Nothing stored.",
                    latest_period,
                )
                return False
            key = self.store_raw(path)

        self.logger.info(
            "New data detected (latest period %s -> %s)", last_period or "never", latest_period
        )
        self.save_watermark(
            load_mode="incremental",
            last_period_fetched=latest_period,
            status="raw",
            raw_file=key,
        )
        return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _latest_period_in_file(path: Path) -> str | None:
    """Scan the CSV and return the most recent 'YYYY-MM' period found."""
    latest: tuple[int, int] | None = None

    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                y, m = int(row["prfYear"]), int(row["prfMonth"])
            except (KeyError, ValueError):
                continue
            if latest is None or (y, m) > latest:
                latest = (y, m)

    if latest is None:
        return None
    return f"{latest[0]:04d}-{latest[1]:02d}"
