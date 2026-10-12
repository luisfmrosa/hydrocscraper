"""
Sodir (Norwegian Offshore Directorate, formerly NPD) FactPages — company reserves.

Data: one row per field and licensee company — the company's share of the
      field's remaining reserves (oil, gas, NGL, condensate, oil equivalents)
      as of the latest official estimate, and its licence share
Source: https://factpages.sodir.no/en/company/TableView/Reserves
Format: CSV (SSRS ReportServer export, UTF-8 with BOM, dates dd.mm.yyyy)
Granularity: field and company
Periodicity: snapshot (no time dimension)
Licence: NLOD (Norwegian Licence for Open Government Data)

Downloaded by the shared Sodir table view scraper (scrapers/no_sodir/
_tableview.py): one snapshot CSV per download. DatesyncNPD (export date)
changes on every export, so incremental mode compares the content without it,
and the Std view's MD5 leaves it out
(sql/ddl/std_views/023_no_sodir_company_reserves.sql).

CSV columns (English locale):
  cmpLongName              — company name
  fldName                  — field name
  cmpRemainingOil          — company's remaining oil [mill Sm3]
  cmpRemainingGas          — company's remaining gas [bill Sm3]
  cmpRemainingNGL          — company's remaining NGL [mill tonnes]
  cmpRemainingCondensate   — company's remaining condensate [mill Sm3]
  cmpRemainingOE           — company's remaining oil equivalents [mill Sm3 o.e.]
  cmpDateOffResEstDisplay  — date of the official reserves estimate
  cmpShare                 — company's share of the field [%]; the shares of
                             a field don't always sum to 100
  fldNpdidField            — NPDID of the field (key)
  cmpNpdidCompany          — NPDID of the company (key)
  DatesyncNPD              — export date

Tabular and readable by DuckDB: stored as received, then
sql/std/no_sodir/company_reserves.sql converts it to Std and the Lake
(lake.no_sodir.company_reserves) loads from Std, keyed by fldNpdidField and
cmpNpdidCompany (data/static/datasets.csv).
"""

from scrapers.no_sodir._tableview import SodirTableView


class NoSodirCompanyReserves(SodirTableView):
    dataset = "company_reserves"
    label = "company reserves"
    volatile_columns = ("DatesyncNPD",)
