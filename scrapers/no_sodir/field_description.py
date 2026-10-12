"""
Sodir (Norwegian Offshore Directorate, formerly NPD) FactPages — field descriptions.

Data: one row per field and description heading (Development, Reservoir,
      Recovery strategy, Transport, Status) — Sodir's descriptive text
Source: https://factpages.sodir.no/en/field/TableView/Description
Format: CSV (SSRS ReportServer export, UTF-8 with BOM, dates dd.mm.yyyy;
        quoted texts may hold line breaks and commas)
Granularity: field and heading
Periodicity: snapshot (no time dimension)
Licence: NLOD (Norwegian Licence for Open Government Data)

Downloaded by the shared Sodir table view scraper (scrapers/no_sodir/
_tableview.py): one snapshot CSV per download. DatesyncNPD (export date)
changes on every export, so incremental mode compares the content without it,
and the Std view's MD5 leaves it out
(sql/ddl/std_views/024_no_sodir_field_description.sql).

CSV columns (English locale):
  fldName                    — field name
  fldDescriptionHeading      — heading of the description (key)
  fldDescriptionText         — description text
  fldNpdidField              — NPDID of the field (key)
  fldDescriptionDateUpdated  — date the description was last updated
  DatesyncNPD                — export date

Tabular and readable by DuckDB: stored as received, then
sql/std/no_sodir/field_description.sql converts it to Std and the Lake
(lake.no_sodir.field_description) loads from Std, keyed by fldNpdidField and
fldDescriptionHeading (data/static/datasets.csv).
"""

from scrapers.no_sodir._tableview import SodirTableView


class NoSodirFieldDescription(SodirTableView):
    dataset = "field_description"
    label = "field descriptions"
    volatile_columns = ("DatesyncNPD",)
