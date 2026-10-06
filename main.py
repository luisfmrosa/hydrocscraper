"""
hydrocscraper — CLI entry point.

Usage:
    # Download into Raw, then load the Lake
    python main.py --mode full
    python main.py --mode full --sources no_sodir
    python main.py --mode incremental --datasets no_sodir_field_production_monthly
    python main.py --mode full --rebuild-std     # after changing a Std script

DuckLake objects are created by the DuckDB server at startup (sql/ddl/);
Lake tables are created by the app on first load.
"""

import importlib
import logging
import sys

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


def _select(datasets: tuple[str, ...], sources: tuple[str, ...]) -> list[str]:
    """Dataset codes to run: the union of --datasets and --sources, or all."""
    if not datasets and not sources:
        return list(SCRAPER_REGISTRY)

    unknown = [d for d in datasets if d not in SCRAPER_REGISTRY]
    if unknown:
        raise click.BadParameter(
            f"Unknown dataset(s) {', '.join(unknown)}. Available: {', '.join(SCRAPER_REGISTRY)}"
        )
    registered = {entry["source"] for entry in SCRAPER_REGISTRY.values()}
    unknown = [s for s in sources if s not in registered]
    if unknown:
        raise click.BadParameter(
            f"Unknown source(s) {', '.join(unknown)}. Available: {', '.join(sorted(registered))}"
        )

    return [
        code for code, entry in SCRAPER_REGISTRY.items()
        if code in datasets or entry["source"] in sources
    ]


def _load_scraper(code: str, client):
    module_path, class_name = SCRAPER_REGISTRY[code]["class"].rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(client)


@click.command()
@click.option(
    "--mode",
    required=True,
    type=click.Choice(["full", "incremental"], case_sensitive=False),
    help=(
        "full: download the complete dataset, then rebuild its Lake table. "
        "incremental: download only new data, then append its changes to the Lake."
    ),
)
@click.option(
    "--datasets",
    multiple=True,
    help=(
        "Datasets to run (repeatable). "
        f"Available: {', '.join(SCRAPER_REGISTRY)}"
    ),
)
@click.option(
    "--sources",
    multiple=True,
    help=(
        "Run every dataset of these sources (repeatable). "
        f"Available: {', '.join(sorted({e['source'] for e in SCRAPER_REGISTRY.values()}))}"
    ),
)
@click.option(
    "--rebuild-std",
    is_flag=True,
    default=False,
    help=(
        "Full mode only: convert every Raw file to Std again, not only those "
        "without a Std file. Use after changing a Std script."
    ),
)
@click.option("--verbose", "-v", is_flag=True, default=False, help="Debug logging.")
def main(
    mode: str,
    datasets: tuple[str, ...],
    sources: tuple[str, ...],
    rebuild_std: bool,
    verbose: bool,
) -> None:
    _setup_logging(verbose)
    logger = logging.getLogger("hydrocscraper.main")
    if rebuild_std and mode != "full":
        raise click.BadParameter("--rebuild-std requires --mode full", param_hint="--rebuild-std")

    targets = _select(datasets, sources)
    logger.info("Mode: %s  |  Datasets: %s", mode, ", ".join(targets))

    errors: list[str] = []
    with build_client() as client:
        for code in targets:
            try:
                scraper = _load_scraper(code, client)
                logger.info("--- %s ---", scraper)

                if mode == "full":
                    scraper.full_load(rebuild_std=rebuild_std)
                elif mode == "incremental":
                    scraper.incremental_load()

            except Exception as exc:
                logger.error("FAILED %s: %s", code, exc, exc_info=True)
                errors.append(code)

    if errors:
        logger.error("Finished with errors in: %s", ", ".join(errors))
        sys.exit(1)
    else:
        logger.info("Done.")


if __name__ == "__main__":
    main()
