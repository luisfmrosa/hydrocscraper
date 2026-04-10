# hydrocscraper

A modular pipeline that collects official hydrocarbon production data from national and international sources, stores raw downloads, and transforms them into a unified analytical dataset.

## Overview

```
Scrapers (per source)
      │
      ▼
Layer 0 — Raw files   ./data/      (exact as received, git-ignored)
      │
      ▼
Layer 1 — Clean data  ./lake/      (Lance columnar format, git-ignored)
```

Data flows from multiple official sources through source-specific scrapers, lands as raw files, and is then parsed into a unified production schema queryable via Lance.

## Data Sources

### International organizations

| Source | Granularity | Format | Notes |
|--------|-------------|--------|-------|
| JODI Oil | Country | CSV | ~100 countries, ~2-month lag |
| JODI Gas | Country | CSV | Same model as JODI Oil |
| EIA International | Country | JSON API | Free API key required |
| IEA Monthly Oil Statistics | Country | XLSX | Free for OECD; subscription for non-OECD |
| OPEC MOMR | Country | XLSX/PDF | OPEC members only |
| OPEC Annual Statistical Bulletin | Country | XLSX | Historical series |
| Energy Institute Statistical Review | Country | XLSX | Formerly BP Statistical Review |

### National agencies — field / well level

| Country | Agency | Granularity | Data Quality |
|---------|--------|-------------|--------------|
| Norway | Sokkeldirektoratet (NPD) | Field / Well | Excellent |
| United Kingdom | NSTA | Field | Excellent |
| Brazil | ANP | Field / Well | Good |
| Canada | CER | Province | Good |
| Netherlands | NLOG | Field | Good |
| Mexico | CNH | Field | Fair |
| Colombia | ANH | Field | Fair |
| Argentina | Secretaría de Energía | Field / Well | Fair |

## Installation

```bash
pip install -r requirements.txt
```

**Dependencies:** `httpx`, `tenacity`, `click`, `pandas`, `openpyxl`, `pyarrow`, `lancedb`

## Usage

```bash
# First-time full download (all registered sources)
python main.py --mode full

# Full download for specific sources only
python main.py --mode full --sources npd

# Incremental update — fetches only periods not yet captured
python main.py --mode incremental

# Parse latest raw files and write to Lance (Layer 1)
python main.py --mode convert
python main.py --mode convert --sources npd --lance-mode overwrite

# Show Lance dataset summary
python main.py --mode info

# Verbose / debug logging
python main.py --mode full -v
```

## Project Structure

```
hydrocscraper/
├── main.py              # CLI entry point and orchestrator
├── config.py            # Source registry, paths, settings
├── requirements.txt
│
├── scrapers/
│   ├── base.py          # Abstract BaseScraper class
│   └── npd.py           # Norway Sokkeldirektoratet (implemented)
│
├── models/
│   └── production.py    # ProductionRecord schema
│
├── storage/
│   ├── raw.py           # File I/O, watermarks, path helpers
│   └── lance_layer.py   # Lance read/write layer
│
├── utils/
│   └── http.py          # HTTP client, retries, rate limiting
│
├── discovery/           # Source discovery tooling
│   ├── known_sources.json
│   └── reports/
│
├── docs/
│   ├── data_sources.md  # Full source catalog with URLs
│   ├── architecture.md  # Architecture and data layout reference
│   └── discovery.md     # Discovery feature documentation
│
├── data/                # Raw downloads — git-ignored
└── lake/                # Lance tables — git-ignored
```

## Load Modes

**`full`** — Downloads the complete available history. Use for first-time setup or after adding a new source. Saves to `./data/{source}/full/YYYY-MM-DD/`.

**`incremental`** — Downloads only periods not yet captured, using a `.watermark.json` file in each source folder. Saves to `./data/{source}/incremental/YYYY-MM/`.

**`convert`** — Parses the latest raw files for each source and writes `ProductionRecord` rows to `./lake/production.lance`. Supports `append` (default) and `overwrite` write modes.

## Unified Schema (Layer 1)

| Column | Type | Description |
|--------|------|-------------|
| `source` | string | Source identifier (e.g. `npd`, `jodi_oil`) |
| `country_iso3` | string | ISO 3166-1 alpha-3 country code |
| `region` | string | Sub-national region, if available |
| `field_name` | string | Field name, if available |
| `well_id` | string | Well identifier, if available |
| `period` | date | First day of the reference month |
| `commodity` | string | `crude_oil`, `natural_gas`, `ngl`, `condensate` |
| `value` | float64 | Production volume |
| `unit` | string | Unit of measure (e.g. `kb/d`, `mcm/month`) |
| `scraped_at` | timestamp | When the raw file was downloaded |
| `source_file` | string | Relative path to the originating raw file |

## Adding a New Scraper

1. Create `scrapers/{source_id}.py` inheriting from `scrapers.base.BaseScraper`
2. Implement `full_load()`, `incremental_load()`, `latest_raw_files()`, and `parse()`
3. Register the class in `config.py` under `SCRAPER_REGISTRY`
