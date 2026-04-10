# Architecture

## Overview

hydrocscraper is a modular pipeline that collects official hydrocarbon production data from multiple sources, stores raw downloads, and will eventually transform them into a unified analytical layer.

```
┌─────────────────────────────────────────────────────┐
│                    Orchestrator                     │
│                    (main.py)                        │
└───────────────────────┬─────────────────────────────┘
                        │
          ┌─────────────┼──────────────┐
          ▼             ▼              ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐   ...
    │  Scraper │  │  Scraper │  │  Scraper │
    │   JODI   │  │   EIA    │  │   NPD    │
    └────┬─────┘  └────┬─────┘  └────┬─────┘
         │              │              │
         └──────────────┼──────────────┘
                        ▼
              ┌──────────────────┐
              │   Layer 0: Raw   │
              │   ./data/        │
              │  (files as-is)   │
              └────────┬─────────┘
                       │  (future)
                       ▼
              ┌──────────────────┐
              │  Layer 1: Clean  │
              │  (Lance format)  │
              └──────────────────┘
```

---

## Load Modes

The scraper supports two modes, selected via the `--mode` CLI flag.

### `full` — Full Load

Downloads the complete available history from each source. Used for:
- First-time setup
- Recovering from corruption
- Backfilling after a new source is added

Behavior:
- Ignores any existing files in `./data`
- Downloads the largest available dataset (full history)
- Saves to `./data/{source}/full/YYYY-MM-DD/` where `YYYY-MM-DD` is the run date
- Old full-load snapshots are retained (not overwritten)

### `incremental` — Incremental Load

Downloads only the most recent period(s) not yet captured. Used for:
- Scheduled daily/weekly runs
- Keeping data current with minimal bandwidth

Behavior:
- Reads the watermark file (`.watermark.json`) inside each source folder to determine the last successfully fetched period
- Downloads only new or updated periods
- Saves to `./data/{source}/incremental/YYYY-MM/` per period covered
- Updates the watermark on success

### Running

```bash
# First-time full load (all sources)
python main.py --mode full

# Full load for specific sources only
python main.py --mode full --sources jodi_oil eia npd

# Incremental update (all sources)
python main.py --mode incremental

# Incremental for specific sources
python main.py --mode incremental --sources jodi_oil opec_momr

# Search for new country data sources (see docs/discovery.md)
python main.py --mode discover

# Limit discovery to a region
python main.py --mode discover --regions middle_east africa
```

---

## Raw Data Layer — `./data/`

Raw files are stored exactly as received (no parsing, no transformation). Each source has its own subfolder. Within each subfolder, data is split by load type and then by date/period.

```
data/
│
├── jodi_oil/
│   ├── full/
│   │   └── YYYY-MM-DD/          # date the full download was run
│   │       └── world_primary_csv.zip
│   ├── incremental/
│   │   └── YYYY-MM/             # reference month of the data
│   │       └── world_primary_csv.zip
│   └── .watermark.json
│
├── jodi_gas/
│   ├── full/
│   │   └── YYYY-MM-DD/
│   │       └── world_gas_csv.zip
│   ├── incremental/
│   │   └── YYYY-MM/
│   │       └── world_gas_csv.zip
│   └── .watermark.json
│
├── eia/
│   ├── full/
│   │   └── YYYY-MM-DD/
│   │       ├── international_oil.json
│   │       └── international_gas.json
│   ├── incremental/
│   │   └── YYYY-MM/
│   │       ├── international_oil.json
│   │       └── international_gas.json
│   └── .watermark.json
│
├── iea/
│   ├── oil/
│   │   ├── full/
│   │   │   └── YYYY-MM-DD/
│   │   │       └── monthly_oil_statistics.xlsx
│   │   └── incremental/
│   │       └── YYYY-MM/
│   │           └── monthly_oil_statistics.xlsx
│   ├── gas/
│   │   ├── full/
│   │   │   └── YYYY-MM-DD/
│   │   └── incremental/
│   │       └── YYYY-MM/
│   └── .watermark.json
│
├── opec_momr/
│   ├── full/
│   │   └── YYYY-MM-DD/
│   │       ├── momr_YYYY_MM.xlsx   # appendix tables
│   │       └── momr_YYYY_MM.pdf    # full report
│   ├── incremental/
│   │   └── YYYY-MM/
│   │       ├── momr_YYYY_MM.xlsx
│   │       └── momr_YYYY_MM.pdf
│   └── .watermark.json
│
├── opec_asb/
│   ├── full/
│   │   └── YYYY/                  # annual
│   │       └── asb_YYYY.xlsx
│   └── .watermark.json
│
├── energy_institute/
│   ├── full/
│   │   └── YYYY/
│   │       └── statistical_review_YYYY.xlsx
│   └── .watermark.json
│
├── npd/                           # Norway — Sokkeldirektoratet
│   ├── fields/
│   │   ├── full/
│   │   │   └── YYYY-MM-DD/
│   │   │       └── field_production_monthly.csv
│   │   └── incremental/
│   │       └── YYYY-MM/
│   │           └── field_production_monthly.csv
│   ├── wells/
│   │   ├── full/
│   │   │   └── YYYY-MM-DD/
│   │   │       └── wellbore_production_monthly.csv
│   │   └── incremental/
│   │       └── YYYY-MM/
│   │           └── wellbore_production_monthly.csv
│   └── .watermark.json
│
├── nsta/                          # United Kingdom
│   ├── fields/
│   │   ├── full/
│   │   │   └── YYYY-MM-DD/
│   │   │       └── ukcs_field_production.csv
│   │   └── incremental/
│   │       └── YYYY-MM/
│   │           └── ukcs_field_production.csv
│   └── .watermark.json
│
├── anp/                           # Brazil
│   ├── fields/
│   │   ├── full/
│   │   │   └── YYYY-MM-DD/
│   │   │       └── producao_campo_YYYY.xlsx
│   │   └── incremental/
│   │       └── YYYY-MM/
│   │           └── producao_campo_YYYY_MM.xlsx
│   ├── wells/
│   │   ├── full/
│   │   │   └── YYYY-MM-DD/
│   │   │       └── producao_poco_YYYY.xlsx
│   │   └── incremental/
│   │       └── YYYY-MM/
│   │           └── producao_poco_YYYY_MM.xlsx
│   └── .watermark.json
│
├── cer/                           # Canada
│   ├── full/
│   │   └── YYYY-MM-DD/
│   │       ├── crude_oil_production.xlsx
│   │       └── natural_gas_production.xlsx
│   ├── incremental/
│   │   └── YYYY-MM/
│   │       ├── crude_oil_production.xlsx
│   │       └── natural_gas_production.xlsx
│   └── .watermark.json
│
├── cnh/                           # Mexico
│   ├── fields/
│   │   ├── full/
│   │   │   └── YYYY-MM-DD/
│   │   │       └── produccion_campo_YYYY_MM.xlsx
│   │   └── incremental/
│   │       └── YYYY-MM/
│   │           └── produccion_campo_YYYY_MM.xlsx
│   └── .watermark.json
│
├── anh/                           # Colombia
│   ├── fields/
│   │   ├── full/
│   │   │   └── YYYY-MM-DD/
│   │   │       └── produccion_campo_YYYY_MM.xlsx
│   │   └── incremental/
│   │       └── YYYY-MM/
│   │           └── produccion_campo_YYYY_MM.xlsx
│   └── .watermark.json
│
├── argentina_se/                  # Argentina — Secretaría de Energía
│   ├── fields/
│   │   ├── full/
│   │   │   └── YYYY-MM-DD/
│   │   │       └── produccion_campo_YYYY.csv
│   │   └── incremental/
│   │       └── YYYY-MM/
│   │           └── produccion_campo_YYYY_MM.csv
│   ├── wells/
│   │   ├── full/
│   │   │   └── YYYY-MM-DD/
│   │   │       └── produccion_pozo_YYYY.csv
│   │   └── incremental/
│   │       └── YYYY-MM/
│   │           └── produccion_pozo_YYYY_MM.csv
│   └── .watermark.json
│
└── nlog/                          # Netherlands
    ├── fields/
    │   ├── full/
    │   │   └── YYYY-MM-DD/
    │   │       └── production_data.csv
    │   └── incremental/
    │       └── YYYY-MM/
    │           └── production_data.csv
    └── .watermark.json
```

### Watermark File

Each source folder contains a `.watermark.json` that tracks the state of incremental loads:

```json
{
  "source": "jodi_oil",
  "last_full_run": "2025-01-15",
  "last_incremental_run": "2025-04-09",
  "last_period_fetched": "2025-02",
  "status": "ok"
}
```

---

## Layer 1: Clean Layer (Planned — Lance Format)

A second processing layer will transform raw downloads into a unified, queryable dataset using [Lance](https://lancedb.github.io/lance/) columnar format.

Planned schema for the unified production record:

| Column | Type | Description |
|--------|------|-------------|
| `source` | string | Source identifier (e.g. `jodi_oil`, `npd`) |
| `country_iso3` | string | ISO 3166-1 alpha-3 country code |
| `region` | string | Sub-national region / province (if available) |
| `field_name` | string | Field name (if available) |
| `well_id` | string | Well identifier (if available) |
| `period` | date | First day of the reference month |
| `commodity` | string | `crude_oil`, `natural_gas`, `ngl`, `condensate` |
| `value` | float64 | Production volume |
| `unit` | string | Unit of measure (e.g. `kb/d`, `mcm/month`) |
| `scraped_at` | timestamp | When the raw file was downloaded |
| `source_file` | string | Relative path to the originating raw file |

Storage location (to be defined): `./lake/production.lance`

---

## Project Structure

```
hydrocscraper/
├── main.py              # CLI entry point and orchestrator
├── config.py            # Source registry, paths, API keys
├── requirements.txt
├── .gitignore
│
├── scrapers/
│   ├── base.py          # Abstract BaseScraper class
│   ├── jodi.py          # JODI Oil + Gas
│   ├── eia.py           # EIA International API
│   ├── iea.py           # IEA Monthly Oil Statistics
│   ├── opec.py          # OPEC MOMR + ASB
│   ├── energy_institute.py
│   ├── npd.py           # Norway Sokkeldirektoratet
│   ├── nsta.py          # UK NSTA
│   ├── anp.py           # Brazil ANP
│   ├── cer.py           # Canada CER
│   ├── cnh.py           # Mexico CNH
│   ├── anh.py           # Colombia ANH
│   ├── argentina_se.py  # Argentina Secretaría de Energía
│   └── nlog.py          # Netherlands NLOG
│
├── models/
│   └── production.py    # ProductionRecord dataclass / schema
│
├── storage/
│   └── raw.py           # File I/O, watermark read/write, path helpers
│
├── utils/
│   └── http.py          # Session, retry logic, rate limiting
│
├── discovery/           # Source discovery module (see docs/discovery.md)
│   ├── runner.py        # Orchestrates discovery flow
│   ├── searcher.py      # Web search queries per country/region
│   ├── extractor.py     # Parses results, scores candidates
│   ├── differ.py        # Compares candidates vs. known sources
│   ├── reporter.py      # Writes Markdown report
│   ├── known_sources.json  # Machine-readable mirror of docs/data_sources.md
│   └── reports/         # Discovery run reports (YYYY-MM-DD_report.md)
│
├── data/                # Raw downloads (Layer 0) — git-ignored
├── lake/                # Lance tables (Layer 1, future) — git-ignored
└── docs/
    ├── data_sources.md  # Source catalog with URLs and metadata
    ├── architecture.md  # This file
    └── discovery.md     # Source discovery feature documentation
```
