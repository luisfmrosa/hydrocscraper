"""
Library step: the frame and latest views of a Lake table, built by dbt
(transform/) on the quack server. The SQL is generated from the Hook metadata
by transform/macros/library.sql; per Lake table <code> = <source>_<table> the
models live in transform/models/library/<code>/:

  frame_<code>.sql        library.frame.<code>          production hooks
  frame_<code>_dev.sql    library.frame.<code>_dev      development hooks
  latest_<code>.sql       library.latest.<code>
  latest_<code>_dev.sql   library.latest.<code>_dev

storage/lake.py builds a table's models after each Lake load. To build every
model (e.g. after changing hooks.csv and restarting the server):

  python -m storage.library run                      # every model
  python -m storage.library run -s path:models/library/no_sodir_field

dbt runs in this process (dbtRunner), with transform/profiles.yml, which reads
HYDROC_QUACK_URL, HYDROC_QUACK_TOKEN and HYDROC_QUACK_DISABLE_SSL (config.py
loads .env into the environment).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import config  # noqa: F401  (loads .env into os.environ for the dbt profile)
from config import PROJECT_ROOT

logger = logging.getLogger(__name__)

PROJECT_DIR = PROJECT_ROOT / "transform"
MODELS_DIR = PROJECT_DIR / "models" / "library"


def models(source: str, table: str) -> list[Path]:
    """The table's Library model files (empty if it has none)."""
    folder = MODELS_DIR / f"{source}_{table}"
    return sorted(folder.glob("*.sql")) if folder.is_dir() else []


def dbt(args: list[str]) -> None:
    """Run a dbt command on transform/; raise if it fails."""
    from dbt.cli.main import dbtRunner

    # dbt-duckdb imports the quack plugin (storage.dbt_quack) by module path
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    full = [*args, "--project-dir", str(PROJECT_DIR), "--profiles-dir", str(PROJECT_DIR)]
    logger.info("dbt %s", " ".join(args))
    result = dbtRunner().invoke(full)
    if not result.success:
        raise RuntimeError(f"dbt {' '.join(args)} failed: {result.exception or 'see transform/logs/dbt.log'}")


def close() -> None:
    """Close dbt-duckdb's client connection (it keeps one per process, reused
    by later invocations with the same profile)."""
    from dbt.adapters.duckdb.connections import DuckDBConnectionManager

    env = DuckDBConnectionManager._ENV
    conn = getattr(env, "conn", None)
    if conn is not None:
        conn.close()
    DuckDBConnectionManager.close_all_connections()


def build(source: str, table: str) -> bool:
    """(Re)create the table's Library views; False if it has none."""
    if not models(source, table):
        logger.info("library: %s_%s has no models", source, table)
        return False
    dbt(["run", "--select", f"path:models/library/{source}_{table}"])
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s")
    try:
        dbt(sys.argv[1:] or ["run"])
    except RuntimeError as exc:
        logger.error("%s", exc)
        sys.exit(1)
