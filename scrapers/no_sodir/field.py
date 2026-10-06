"""
Sodir (Norwegian Offshore Directorate, formerly NPD) FactPages — fields.

Data: one row per field — name, operator, status, discovery wellbore, main
      area, licence, supply base, hydrocarbon type, NPDIDs, FactPage links
Source: https://factpages.sodir.no/en/field/TableView/Overview
Format: CSV (SSRS ReportServer export, UTF-8 with BOM, dates dd.mm.yyyy)
Granularity: field
Periodicity: snapshot (no time dimension)
Licence: NLOD (Norwegian Licence for Open Government Data)

Sodir publishes the current list of fields as one CSV, so both full and
incremental modes download the same file, stored under the download month.
DatesyncNPD (export date) and fldDateUpdatedMax change on every export, so
incremental mode compares the content without them: it only stores the file
when another column changed. For the same reason they are left out of the
Std view's MD5 (sql/ddl/std_views/021_no_sodir_field.sql).

CSV columns (English locale; fldCurrentActivitySatus is Sodir's spelling):
  fldName                  — field name
  cmpLongName              — operator
  fldCurrentActivitySatus  — Producing, Shut down, Approved for production
  wlbName                  — discovery wellbore
  wlbCompletionDate        — completion date of the discovery wellbore
  fldMainArea              — North sea, Norwegian sea, Barents sea
  fldOwnerKind             — owner kind (production licence, business arrangement)
  fldOwnerName             — owner (licence)
  fldMainSupplyBase        — main supply base
  fldHcType                — hydrocarbon type (OIL, GAS, GAS/CONDENSATE, …)
  fldNpdidOwner            — NPDID of the owner
  fldNpdidField            — NPDID of the field (key)
  wlbNpdidWellbore         — NPDID of the discovery wellbore
  cmpNpdidCompany          — NPDID of the operator
  fldFactPageUrl           — FactPage URL
  fldFactMapUrl            — FactMap URL
  fldDateUpdated           — date the field's main data was updated
  fldDateUpdatedMax        — date any of the field's data was updated
  DatesyncNPD              — export date

Tabular and readable by DuckDB: stored as received, then
sql/std/no_sodir/field.sql converts it to Std and the Lake
(lake.no_sodir.field) loads from Std, keyed by fldNpdidField
(data/static/datasets.csv).
"""

from scrapers.base import BaseScraper

_CSV_URL = (
    "https://factpages.sodir.no/public?/Factpages/external/tableview/"
    "field"
    "&rs:Command=Render"
    "&rc:Toolbar=false"
    "&rc:Parameters=f"
    "&IpAddress=not_used"
    "&CultureCode=en"
    "&rs:Format=CSV"
    "&Top100=false"
)

# Columns that change on every export: ignored when comparing downloads
_VOLATILE_COLUMNS = ("fldDateUpdatedMax", "DatesyncNPD")


class NoSodirField(BaseScraper):
    source = "no_sodir"
    dataset = "field"

    @property
    def filename(self) -> str:
        return f"{self.dataset}.csv"

    def download_full(self) -> None:
        self.logger.info("Full load: downloading Sodir fields CSV.")
        with self.fetch_to_temp(_CSV_URL, self.filename) as path:
            key = self.store_raw(path)
        self.save_watermark(load_mode="full", last_period_fetched=_period(key), status="raw", raw_file=key)
        self.logger.info("Download complete: %s", key)

    def download_incremental(self) -> bool:
        self.logger.info("Incremental load: downloading Sodir fields CSV.")
        with self.fetch_to_temp(_CSV_URL, self.filename) as path:
            if not self.is_new_content(path, ignore_columns=_VOLATILE_COLUMNS):
                self.logger.info("No new data (fields unchanged). Nothing stored.")
                return False
            key = self.store_raw(path)
        self.save_watermark(
            load_mode="incremental", last_period_fetched=_period(key), status="raw", raw_file=key
        )
        self.logger.info("New data detected: %s", key)
        return True


def _period(key: str) -> str:
    """The Raw key's year_month (the download month: a snapshot has no period)."""
    return key.split("year_month=", 1)[1].split("/", 1)[0]
