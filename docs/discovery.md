# Source Discovery

## Purpose

The discovery module periodically searches the web for new official national hydrocarbon production data sources, compares the results against the existing catalog in `docs/data_sources.md`, and produces a report of candidates not yet covered.

This is intentionally a **research aid**, not an automatic ingestion pipeline. A human reviews the candidates before any new scraper is built.

---

## How It Works

```
┌─────────────────────────────────────────────┐
│            discovery/runner.py              │
└──────────────────────┬──────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   ┌────────────┐ ┌─────────┐ ┌──────────┐
   │  Searcher  │ │  Parser │ │ Differ   │
   │(web search)│ │(extract │ │(compare  │
   │            │ │ URLs,   │ │ vs known │
   │            │ │ formats)│ │ sources) │
   └────────────┘ └─────────┘ └──────────┘
                                    │
                                    ▼
                        ┌───────────────────────┐
                        │ discovery/reports/     │
                        │ YYYY-MM-DD_report.md   │
                        └───────────────────────┘
```

### Steps

1. **Search** — Issue a set of predefined queries targeting official government and regulatory energy portals (e.g. `"[country] oil gas production statistics open data download"`). Queries are templated across a list of target countries not yet covered at field/well level.

2. **Extract** — Parse search results to identify candidate URLs. Filter for government or quasi-governmental domains (`.gov`, `.gob`, `.gouv`, regulatory agency known domains, etc.).

3. **Deduplicate** — Load the current known-source list from `docs/data_sources.md` (parsed as structured data from `discovery/known_sources.json`, kept in sync). Remove any candidate already present.

4. **Score** — Rank remaining candidates by signals of data quality:
   - Is the domain official/governmental?
   - Does the page mention CSV, Excel, or API download?
   - Does it mention production (vs. reserves, exploration only)?
   - Is it in English or a widely-supported language?

5. **Report** — Write a Markdown report to `discovery/reports/YYYY-MM-DD_report.md` with:
   - Candidate sources ranked by score
   - URL, country, inferred format, inferred granularity
   - Reason flagged (search query that found it)
   - Action column (blank — for human review)

---

## Running Discovery

```bash
# Run a discovery scan
python main.py --mode discover

# Limit to specific regions
python main.py --mode discover --regions "middle_east" "africa"

# Dry run (print candidates, don't write report)
python main.py --mode discover --dry-run
```

---

## Module Layout

```
discovery/
├── __init__.py
├── runner.py          # Orchestrates the full discovery flow
├── searcher.py        # Issues web search queries per country/region
├── extractor.py       # Parses results, scores candidates
├── differ.py          # Compares candidates vs. known_sources.json
├── reporter.py        # Writes the Markdown report
└── known_sources.json # Machine-readable mirror of docs/data_sources.md
```

### `known_sources.json` schema

```json
[
  {
    "id": "jodi_oil",
    "name": "JODI Oil",
    "url": "https://www.jodidata.org/oil/database/data-downloads.aspx",
    "format": "CSV",
    "granularity": "country",
    "periodicity": "monthly",
    "scope": "international",
    "countries": "all"
  },
  {
    "id": "npd",
    "name": "Norway Sokkeldirektoratet (NPD)",
    "url": "https://factpages.sodir.no/en/field",
    "format": "CSV",
    "granularity": "field",
    "periodicity": "monthly",
    "scope": "national",
    "countries": ["NOR"]
  }
]
```

---

## Search Query Templates

Queries are generated per uncovered country using templates such as:

- `"{country}" oil gas production statistics open data download`
- `"{agency}" hydrocarbon production monthly CSV download`
- `site:.gov.{tld} oil production statistics download`
- `"{country}" national petroleum authority production report download`

Target countries are maintained in `discovery/target_countries.json`, which lists countries not yet covered at field level.

---

## Report Format

```markdown
# Source Discovery Report — 2025-04-10

## New Candidates Found

| # | Country | URL | Inferred Format | Inferred Granularity | Score | Found Via | Action |
|---|---------|-----|-----------------|---------------------|-------|-----------|--------|
| 1 | Angola  | https://www.anpg.co.ao/... | XLSX | Field | 8/10 | "angola oil production open data" | |
| 2 | Libya   | https://www.noc.ly/...      | PDF  | Country | 4/10 | "libya NOC oil statistics download" | |

## Already Covered (skipped)

- JODI Oil, EIA, IEA, NPD, NSTA, ANP, ...

## Search Queries Used

- "angola oil production statistics open data download"
- ...
```

---

## Scheduling

Discovery runs can be scheduled via cron or a task scheduler. Recommended cadence: **monthly**.

```bash
# Example cron (first day of each month at 08:00)
0 8 1 * * cd /path/to/hydrocscraper && python main.py --mode discover
```

Reports accumulate in `discovery/reports/` for audit trail.
