"""
Scraper for the Norwegian Offshore Directorate (Sokkeldirektoratet) FactPages.

Data: monthly field production — oil, gas, NGL, condensate, water
Source: https://factpages.sodir.no/en/field/TableView/Production/Saleable/Monthly
Format: CSV (SSRS ReportServer export)
Granularity: field level
Periodicity: monthly
Licence: NLOD (Norwegian Licence for Open Government Data)

NPD publishes a single CSV containing the complete production history for all
fields. There is no incremental API endpoint, so both full and incremental
modes download the same file. Incremental mode only stores the file in the
Raw bucket if its latest period differs from the watermark.

CSV columns (English locale):
  prfInformationCarrier  — NPDID of the field
  prfYear                — year (int)
  prfMonth               — month (int)
  prfNpdidInformationCarrier — same NPDID (numeric key)
  prfPrdOilNetMillSm3    — net oil production [mill Sm³]
  prfPrdGasNetBillSm3    — net gas production [bill Sm³]
  prfPrdNGLNetMillSm3    — net NGL [mill Sm³]
  prfPrdCondensateNetMillSm3 — net condensate [mill Sm³]
  prfPrdOeNetMillSm3     — net oil equivalents [mill Sm³]
  prfPrdProducedWaterInFieldMillSm3 — produced water [mill Sm³]
"""

import csv
import io
import logging
from datetime import date
from pathlib import Path

import httpx

from models.production import Commodity, ProductionRecord
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

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

_DATASET = "field_production_monthly"
_FILENAME = f"{_DATASET}.csv"

# Map CSV column -> (commodity constant, unit)
_COMMODITY_COLS: list[tuple[str, str, str]] = [
    ("prfPrdOilNetMillSm3",            Commodity.CRUDE_OIL,    "mill_sm3_month"),
    ("prfPrdGasNetBillSm3",            Commodity.NATURAL_GAS,  "bill_sm3_month"),
    ("prfPrdNGLNetMillSm3",            Commodity.NGL,          "mill_sm3_month"),
    ("prfPrdCondensateNetMillSm3",     Commodity.CONDENSATE,   "mill_sm3_month"),
    ("prfPrdOeNetMillSm3",             Commodity.OIL_EQUIVALENT, "mill_sm3_month"),
    ("prfPrdProducedWaterInFieldMillSm3", Commodity.WATER,     "mill_sm3_month"),
]


class NPDScraper(BaseScraper):
    source_id = "npd"

    def full_load(self) -> None:
        self.logger.info("Full load: downloading NPD field production CSV.")
        with self.fetch_to_temp(_CSV_URL, _FILENAME) as path:
            latest_period = _latest_period_in_file(path)
            key = self.store_raw(path, _DATASET)
        self.save_watermark(
            _DATASET,
            load_mode="full",
            last_period_fetched=latest_period,
            status="ok",
            raw_file=key,
        )
        self.logger.info("Full load complete. Latest period in file: %s", latest_period)

    def incremental_load(self) -> None:
        last_period = self.watermark(_DATASET).get("last_period_fetched")

        # NPD always publishes the full dataset; the watermark tells us
        # whether new data has actually been added.
        self.logger.info("Incremental load: downloading NPD field production CSV.")
        with self.fetch_to_temp(_CSV_URL, _FILENAME) as path:
            latest_period = _latest_period_in_file(path)
            if latest_period == last_period:
                self.logger.info(
                    "No new data (latest period still %s). Nothing stored.",
                    latest_period,
                )
                return
            key = self.store_raw(path, _DATASET)

        self.logger.info(
            "New data detected: %s -> %s", last_period or "never", latest_period
        )
        self.save_watermark(
            _DATASET,
            load_mode="incremental",
            last_period_fetched=latest_period,
            status="ok",
            raw_file=key,
        )

    def parse(self, csv_path: Path) -> list[ProductionRecord]:
        """Parse a downloaded NPD CSV into ProductionRecord objects.

        Returns one record per commodity per field per month.
        Rows with all-zero production are included (they are valid zero months).
        """
        records: list[ProductionRecord] = []
        source_file = csv_path.name

        with csv_path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                try:
                    year = int(row["prfYear"])
                    month = int(row["prfMonth"])
                    period = date(year, month, 1)
                except (KeyError, ValueError):
                    logger.warning("Skipping malformed row: %s", row)
                    continue

                field_name = row.get("prfInformationCarrier", "").strip()

                for col, commodity, unit in _COMMODITY_COLS:
                    raw = row.get(col, "").strip()
                    if not raw:
                        continue
                    try:
                        value = float(raw.replace(",", "."))
                    except ValueError:
                        continue

                    records.append(
                        ProductionRecord(
                            source=self.source_id,
                            source_file=source_file,
                            country_iso3="NOR",
                            field_name=field_name,
                            period=period,
                            commodity=commodity,
                            value=value,
                            unit=unit,
                        )
                    )

        logger.info("Parsed %d records from %s", len(records), csv_path.name)
        return records


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
