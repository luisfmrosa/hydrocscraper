"""
Sodir (Norwegian Offshore Directorate, formerly NPD) FactPages — fields.

Data: one row per field — name, operator, status, discovery wellbore, main
      area, licence, supply base, hydrocarbon type, NPDIDs, FactPage links
Source: https://factpages.sodir.no/en/field/TableView/Overview
Format: CSV (SSRS ReportServer export, UTF-8 with BOM, dates dd.mm.yyyy)
Granularity: field
Periodicity: snapshot (no time dimension)
Licence: NLOD (Norwegian Licence for Open Government Data)

Downloaded by the shared Sodir table view scraper (scrapers/no_sodir/
_tableview.py): one snapshot CSV per download. DatesyncNPD (export date) and
fldDateUpdatedMax change on every export, so incremental mode compares the
content without them, and the Std view's MD5 leaves them out
(sql/ddl/std_views/021_no_sodir_field.sql).

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

from scrapers.no_sodir._tableview import SodirTableView


class NoSodirField(SodirTableView):
    dataset = "field"
    label = "fields"
    volatile_columns = ("fldDateUpdatedMax", "DatesyncNPD")
