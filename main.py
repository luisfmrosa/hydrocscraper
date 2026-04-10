"""
hydrocscraper — CLI entry point.

Usage:
    # Download raw data
    python main.py --mode full
    python main.py --mode full --sources npd
    python main.py --mode incremental

    # Convert latest raw files to Lance (Layer 1)
    python main.py --mode convert
    python main.py --mode convert --sources npd --lance-mode overwrite

    # Show Lance dataset info
    python main.py --mode info
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
    type=click.Choice(["full", "incremental", "convert", "info"], case_sensitive=False),
    help=(
        "full: download complete history. "
        "incremental: download only new periods. "
        "convert: parse latest raw files and write to Lance. "
        "info: print Lance dataset summary."
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
    "--lance-mode",
    default="append",
    type=click.Choice(["overwrite", "append"], case_sensitive=False),
    show_default=True,
    help="Lance write mode used by --mode convert.",
)
@click.option("--verbose", "-v", is_flag=True, default=False, help="Debug logging.")
def main(mode: str, sources: tuple[str, ...], lance_mode: str, verbose: bool) -> None:
    _setup_logging(verbose)
    logger = logging.getLogger("hydrocscraper.main")

    if mode == "info":
        _cmd_info(logger)
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
                elif mode == "convert":
                    _cmd_convert(scraper, lance_mode, logger)

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

def _cmd_convert(scraper, lance_mode: str, logger: logging.Logger) -> None:
    from storage.lance_layer import write

    raw_files = scraper.latest_raw_files()
    if not raw_files:
        logger.warning(
            "%s: no raw files found. Run --mode full first.", scraper.source_id
        )
        return

    all_records: list = []
    for path in raw_files:
        logger.info("Parsing %s", path)
        records = scraper.parse(path)
        logger.info("  -> %d records", len(records))
        all_records.extend(records)

    if not all_records:
        logger.warning("%s: parse() returned 0 records.", scraper.source_id)
        return

    logger.info(
        "Writing %d records to Lance (lance_mode=%s) ...", len(all_records), lance_mode
    )
    ds = write(all_records, mode=lance_mode)
    logger.info("Lance write complete. Total rows: %d", ds.count_rows())


def _cmd_info(logger: logging.Logger) -> None:
    try:
        from storage.lance_layer import dataset_info
        info = dataset_info()
    except FileNotFoundError as exc:
        logger.error(str(exc))
        sys.exit(1)

    print(f"\nLance dataset: {info['path']}")
    print(f"  Rows      : {info['rows']:,}")
    print(f"  Versions  : {info['versions']}")
    print(f"  Latest v  : {info['latest_version']}")
    print(f"  Columns   : {', '.join(info['columns'])}\n")


if __name__ == "__main__":
    main()
