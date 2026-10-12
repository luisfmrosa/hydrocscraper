"""
Shared scraper for Sodir FactPages table views published as a snapshot CSV.

Each table view (fields, companies, reserves…) is one SSRS ReportServer report
exported as CSV (UTF-8 with BOM, dates dd.mm.yyyy). Sodir publishes only the
current state, so both full and incremental modes download the same file,
stored under the download month (a snapshot has no period).

Every export carries columns that change on each export without the data
changing (the export date, DatesyncNPD under various spellings). A subclass
lists them in volatile_columns: incremental mode compares the content without
them and only stores the file when another column changed. The dataset's
std view leaves them out of the MD5 for the same reason.

A subclass sets source, dataset (the Sodir report name, also the Raw folder
and file stem), label (for the log) and volatile_columns.
"""

from scrapers.base import BaseScraper

_CSV_URL = (
    "https://factpages.sodir.no/public?/Factpages/external/tableview/"
    "{report}"
    "&rs:Command=Render"
    "&rc:Toolbar=false"
    "&rc:Parameters=f"
    "&IpAddress=not_used"
    "&CultureCode=en"
    "&rs:Format=CSV"
    "&Top100=false"
)


class SodirTableView(BaseScraper):
    source = "no_sodir"
    label: str
    volatile_columns: tuple[str, ...] = ()

    @property
    def url(self) -> str:
        return _CSV_URL.format(report=self.dataset)

    @property
    def filename(self) -> str:
        return f"{self.dataset}.csv"

    def download_full(self) -> None:
        self.logger.info("Full load: downloading Sodir %s CSV.", self.label)
        with self.fetch_to_temp(self.url, self.filename) as path:
            key = self.store_raw(path)
        self.save_watermark(load_mode="full", last_period_fetched=_period(key), status="raw", raw_file=key)
        self.logger.info("Download complete: %s", key)

    def download_incremental(self) -> bool:
        self.logger.info("Incremental load: downloading Sodir %s CSV.", self.label)
        with self.fetch_to_temp(self.url, self.filename) as path:
            if not self.is_new_content(path, ignore_columns=self.volatile_columns):
                self.logger.info("No new data (%s unchanged). Nothing stored.", self.label)
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
