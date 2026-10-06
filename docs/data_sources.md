# Data Sources

This document catalogs all official data sources targeted by hydrocscraper for hydrocarbon production data.

Granularity levels:
- **Country** — aggregated national totals
- **Province/State** — sub-national aggregation
- **Field** — individual oil/gas field
- **Well** — individual wellbore

Data quality ratings:
- **Excellent** — fully documented methodology, high coverage, machine-readable, timely
- **Good** — reliable, minor gaps or delays, some manual steps
- **Fair** — incomplete coverage, inconsistent formatting, or significant publication lags

---

## International Organizations

| # | Source | URL | Format | Granularity | Periodicity | Data Quality | Notes |
|---|--------|-----|--------|-------------|-------------|--------------|-------|
| 1 | JODI Oil | https://www.jodidata.org/oil/database/data-downloads.aspx | CSV (zip) | Country | Monthly | Good | ~100 countries; submissions by national agencies; ~2-month lag |
| 2 | JODI Gas | https://www.jodidata.org/gas/database/data-downloads.aspx | CSV (zip) | Country | Monthly | Good | Beta since 2009; same submission model as JODI Oil |
| 3 | EIA International | https://api.eia.gov/v2/international/ | JSON API | Country | Monthly / Annual | Excellent | Free API key required; covers oil, gas, NGL; broad country coverage |
| 4 | IEA Monthly Oil Statistics | https://www.iea.org/data-and-statistics/data-product/monthly-oil-statistics | XLSX / CSV | Country | Monthly | Excellent | Free for OECD countries; non-OECD requires subscription (MODS) |
| 5 | OPEC MOMR Tables | https://www.opec.org/opec_web/en/publications/338.htm | Excel / PDF | Country | Monthly | Good | OPEC members only; Excel appendix tables since Feb 2019 |
| 6 | OPEC Annual Statistical Bulletin | https://www.opec.org/opec_web/en/data_graphs/330.htm | Excel / PDF | Country | Annual | Good | Broader coverage than MOMR; historical series |
| 7 | Energy Institute Statistical Review | https://www.energyinst.org/statistical-review | XLSX | Country | Annual | Excellent | Formerly BP Statistical Review; gold standard for long-run series |

---

## National Agencies — Field / Well Level

| # | Country | Agency | URL | Format | Granularity | Periodicity | Data Quality | Notes |
|---|---------|--------|-----|--------|-------------|-------------|--------------|-------|
| 8 | Norway | Norwegian Offshore Directorate (Sodir) | https://factpages.sodir.no/en/field | CSV (FactPages) | Field / Well | Monthly | Excellent | Formerly the Norwegian Petroleum Directorate (NPD; npd.no now redirects to sodir.no). Daily-synced FactPages; full production history; open licence (NLOD). Loaded: `no_sodir_field_production_monthly` (monthly field production), `no_sodir_field` (fields: one row per field, snapshot) |
| 9 | United Kingdom | NSTA | https://www.nstauthority.co.uk/data-and-insights/data/themes/production/ | CSV | Field | Monthly | Excellent | Full UKCS field history; export via dashboard or data.gov.uk |
| 10 | Brazil | ANP | https://www.gov.br/anp/pt-br/assuntos/producao-e-royalties/producao | XLSX / BI portal | Field / Well | Monthly | Good | Monthly bulletin; BI portal for interactive access; some PDF parsing needed |
| 11 | Canada | CER | https://www.cer-rec.gc.ca/en/data-analysis/energy-commodities/crude-oil-petroleum-products/statistics/ | XLSX / CSV | Province | Monthly | Good | Province-level only (no field); open.canada.ca portal |
| 12 | Mexico | CNH | https://hidrocarburos.gob.mx/estadisticas-de-produccion/ | XLSX | Field | Monthly | Fair | Spanish only; formatting inconsistent across vintages |
| 13 | Colombia | ANH | https://www.anh.gov.co/es/administracion-del-recurso/gestion-del-recurso-hidrocarburifero/estadisticas-hidrocarburos | XLSX | Field | Monthly | Fair | Field-level data available; portal structure changes periodically |
| 14 | Argentina | Secretaría de Energía | https://www.argentina.gob.ar/economia/energia/hidrocarburos/produccion | XLSX / CSV | Field / Well | Monthly | Fair | Open data portal; well-level detail; formatting varies by vintage |
| 15 | Netherlands | NLOG | https://www.nlog.nl/en/production-data | CSV | Field | Monthly | Good | Dutch continental shelf; clean CSV exports; English interface |

---

## Coverage Summary

| Scope | Sources |
|-------|---------|
| Global country-level | JODI Oil, JODI Gas, EIA International, IEA, Energy Institute |
| OPEC members | OPEC MOMR, OPEC ASB |
| Field/well (Europe) | Norway Sodir, UK NSTA, Netherlands NLOG |
| Field/well (Americas) | Brazil ANP, Canada CER, Mexico CNH, Colombia ANH, Argentina SE |

---

## Known Gaps and Limitations

- **Russia, China, Saudi Arabia, Iraq** do not publish field-level data through open portals. Country totals are available via JODI, EIA, and IEA.
- **IEA non-OECD** monthly data requires a paid MODS subscription; free tier covers OECD only.
- **OPEC** data covers member countries only and excludes US, Canada, Norway, Brazil, etc.
- **ANP (Brazil)** well-level data requires navigating a BI portal; no bulk CSV endpoint is officially documented.
