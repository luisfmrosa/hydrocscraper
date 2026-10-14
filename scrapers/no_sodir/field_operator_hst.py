"""
Sodir (Norwegian Offshore Directorate, formerly NPD) FactPages — field operators.

Data: one row per field, operator company and start date — the history of
      each field's operators
Source: https://factpages.sodir.no/en/field/TableView/Operators
Format: CSV (SSRS ReportServer export, UTF-8 with BOM, dates dd.mm.yyyy)
Granularity: field, operator company and period
Periodicity: snapshot (no time dimension)
Licence: NLOD (Norwegian Licence for Open Government Data)

Downloaded by the shared Sodir table view scraper (scrapers/no_sodir/
_tableview.py): one snapshot CSV per download. datesyncNPD (export date)
changes on every export, so incremental mode compares the content without it,
and the Std view's MD5 leaves it out
(sql/ddl/std_views/025_no_sodir_field_operator_hst.sql).

CSV columns (English locale):
  fldName                 — field name
  cmpLongName             — operator company name
  fldOperatorFrom         — first day as operator (key)
  fldOperatorTo           — last day as operator; empty for the current operator
  fldNpdidField           — NPDID of the field (key)
  cmpNpdidCompany         — NPDID of the operator company (key)
  fldOperatorDateUpdated  — date the row was last updated
  datesyncNPD             — export date

Tabular and readable by DuckDB: stored as received, then
sql/std/no_sodir/field_operator_hst.sql converts it to Std and the Lake
(lake.no_sodir.field_operator_hst) loads from Std, keyed by fldNpdidField,
cmpNpdidCompany and fldOperatorFrom (data/static/datasets.csv).
"""

from scrapers.no_sodir._tableview import SodirTableView


class NoSodirFieldOperatorHst(SodirTableView):
    dataset = "field_operator_hst"
    label = "field operators"
    volatile_columns = ("datesyncNPD",)
