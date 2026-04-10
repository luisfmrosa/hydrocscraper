# hydrocscraper — Claude context

## User

- **Name:** Luis Fernando Marques Rosa
- **Email:** falecomluisao@gmail.com

## Project overview

`hydrocscraper` is a modular pipeline that collects official hydrocarbon production data from multiple national/international sources, stores raw downloads (Layer 0 in `./data/`), and transforms them into a unified analytical layer (Layer 1 in `./lake/` using Lance columnar format).

## Running

```bash
python main.py --mode full                        # first-time full load
python main.py --mode full --sources npd          # single source
python main.py --mode incremental                 # scheduled updates
python main.py --mode discover                    # find new sources
```

## Key conventions

- Raw files are stored exactly as received under `./data/{source}/{full|incremental}/{date}/`
- Each source folder has a `.watermark.json` tracking incremental state
- Scraper registry is in `config.py` — maps source IDs to scraper class paths
- New scrapers go in `scrapers/`, inheriting from `scrapers/base.py`
- `./data/` and `./lake/` are git-ignored
