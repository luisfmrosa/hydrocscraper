"""
Sodir (Norwegian Offshore Directorate, formerly NPD) FactPages — companies.

Data: one row per company that is or was a licensee or operator on the
      Norwegian shelf — names, organisation number, nationality, NPDID and
      Y/N flags for its current and former roles
Source: https://factpages.sodir.no/en/company/TableView/All
Format: CSV (SSRS ReportServer export, UTF-8 with BOM, dates dd.mm.yyyy)
Granularity: company
Periodicity: snapshot (no time dimension)
Licence: NLOD (Norwegian Licence for Open Government Data)

Downloaded by the shared Sodir table view scraper (scrapers/no_sodir/
_tableview.py): one snapshot CSV per download. dateSyncNPD (export date)
changes on every export, so incremental mode compares the content without it,
and the Std view's MD5 leaves it out (sql/ddl/std_views/022_no_sodir_company.sql).

CSV columns (English locale):
  cmpLongName                    — company name
  cmpOrgNumberBrReg              — organisation number (Brønnøysund register;
                                   foreign numbers as text, sometimes blank)
  cmpShortName                   — short name
  cmpNationCode                  — country code (NO, GB, US…)
  cmpSurveyPrefix                — prefix used in survey names
  cmpNpdidCompany                — NPDID of the company (key)
  cmpLicenceOperCurrent/Former   — Y/N: current/former production licence operator
  cmpLicenceLicenseeCurrent/Former — Y/N: current/former production licence licensee
  cmpTufOperCurrent/Former       — Y/N: current/former TUF (pipelines and
                                   terminals) operator
  cmpTufPartnerCurrent/Former    — Y/N: current/former TUF partner
  cmpBsnsArrAreaOperCurrent/Former    — Y/N: current/former business
                                        arrangement area operator
  cmpBsnsArrAreaPartnerCurrent/Former — Y/N: current/former business
                                        arrangement area partner
  dateSyncNPD                    — export date

Tabular and readable by DuckDB: stored as received, then
sql/std/no_sodir/company.sql converts it to Std and the Lake
(lake.no_sodir.company) loads from Std, keyed by cmpNpdidCompany
(data/static/datasets.csv).
"""

from scrapers.no_sodir._tableview import SodirTableView


class NoSodirCompany(SodirTableView):
    dataset = "company"
    label = "companies"
    volatile_columns = ("dateSyncNPD",)
