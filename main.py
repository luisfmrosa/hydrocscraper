"""
hydrocscraper — CLI entry point.

Usage:
    # Download raw data
    python main.py --mode full
    python main.py --mode full --sources npd
    python main.py --mode incremental

    # Snapshot the known-sources catalog to the Raw layer
    python main.py --mode discover
    python main.py --mode discover --seed discovery/known_sources.json

DuckLake objects are created by the DuckDB server at startup (sql/ddl/).
"""

import importlib
import logging
import json
import sys
from pathlib import Path

import click

from config import SCRAPER_REGISTRY
from utils.http import build_client


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _load_scraper(source_id: str, client):
    dotted = SCRAPER_REGISTRY.get(source_id)
    if dotted is None:
        raise click.BadParameter(
            f"Unknown source '{source_id}'. "
            f"Available: {', '.join(SCRAPER_REGISTRY)}"
        )
    module_path, class_name = dotted.rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(client)


@click.command()
@click.option(
    "--mode",
    required=True,
    type=click.Choice(["full", "incremental", "discover"], case_sensitive=False),
    help=(
        "full: download complete history. "
        "incremental: download only new periods. "
        "discover: write a new known-sources snapshot to the Raw layer."
    ),
)
@click.option(
    "--sources",
    multiple=True,
    default=None,
    help=(
        "Which sources to run (repeatable: --sources npd --sources eia). "
        "Omit to run all registered sources. "
        f"Available: {', '.join(SCRAPER_REGISTRY)}"
    ),
)
@click.option(
    "--seed",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="discover only: import known sources from a local JSON file.",
)
@click.option("--verbose", "-v", is_flag=True, default=False, help="Debug logging.")
def main(mode: str, sources: tuple[str, ...], seed: Path | None, verbose: bool) -> None:
    _setup_logging(verbose)
    logger = logging.getLogger("hydrocscraper.main")

    if mode == "discover":
        _cmd_discover(seed, logger)
        return

    targets = list(sources) if sources else list(SCRAPER_REGISTRY)
    logger.info("Mode: %s  |  Sources: %s", mode, ", ".join(targets))

    errors: list[str] = []
    with build_client() as client:
        for source_id in targets:
            try:
                scraper = _load_scraper(source_id, client)
                logger.info("--- %s ---", scraper)

                if mode == "full":
                    scraper.full_load()
                elif mode == "incremental":
                    scraper.incremental_load()

            except Exception as exc:
                logger.error("FAILED %s: %s", source_id, exc, exc_info=True)
                errors.append(source_id)

    if errors:
        logger.error("Finished with errors in: %s", ", ".join(errors))
        sys.exit(1)
    else:
        logger.info("Done.")


# ---------------------------------------------------------------------------
# Sub-command implementations
# ---------------------------------------------------------------------------

def _cmd_discover(seed: Path | None, logger: logging.Logger) -> None:
    from discovery.store import latest_known_sources, save_known_sources

    if seed is not None:
        records = json.loads(seed.read_text(encoding="utf-8"))
        logger.info("Seeding %d known sources from %s", len(records), seed)
    else:
        records = latest_known_sources()
        if not records:
            logger.error("No known-sources snapshot found. Run with --seed first.")
            sys.exit(1)
        # The web-search discovery flow (docs/discovery.md) is not implemented
        # yet; this snapshots the current catalog.

    key = save_known_sources(records)
    logger.info("Known sources snapshot written: %s (%d records)", key, len(records))


if __name__ == "__main__":
    main()
