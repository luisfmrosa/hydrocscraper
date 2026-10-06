import os
from pathlib import Path

from dotenv import load_dotenv

# Root paths
PROJECT_ROOT = Path(__file__).parent

# Settings and credentials come from the environment (see .env.example).
load_dotenv(PROJECT_ROOT / ".env")

# Raw layer — S3-compatible bucket (Incus storage bucket)
RAW_BUCKET = "hydroc-raw"
# Std layer — written only by the DuckDB server (SQL); the app never touches it
STD_BUCKET = "hydroc-std"
S3_ENDPOINT = os.getenv("HYDROC_S3_ENDPOINT", "")
S3_RAW_KEY = os.getenv("HYDROC_S3_RAW_KEY", "")
S3_RAW_SECRET = os.getenv("HYDROC_S3_RAW_SECRET", "")
# Path to a CA bundle trusting the bucket endpoint; empty = system default
S3_CA_BUNDLE = os.getenv("HYDROC_S3_CA_BUNDLE") or None

# DuckDB quack server (attaches the Lake/Library/DWH/Hook DuckLakes)
QUACK_URL = os.getenv("HYDROC_QUACK_URL", "")          # e.g. quack:10.10.40.20:9494
QUACK_TOKEN = os.getenv("HYDROC_QUACK_TOKEN", "")
# quack_serve only speaks plain HTTP; CONNECT uses HTTPS for non-localhost hosts
QUACK_DISABLE_SSL = os.getenv("HYDROC_QUACK_DISABLE_SSL", "false").lower() == "true"

# Timestamp suffix for files written to the Raw layer (UTC)
TIMESTAMP_FORMAT = "%Y%m%d_%H%M"

# HTTP defaults
HTTP_TIMEOUT = 120  # seconds — large files can be slow
HTTP_MAX_RETRIES = 4
HTTP_BACKOFF_MIN = 2   # seconds
HTTP_BACKOFF_MAX = 30  # seconds

# Registry: one scraper class per dataset, keyed by dataset code
# (<source>_<dataset>, as in data/static/datasets.csv).
# Used by main.py to resolve --datasets and --sources arguments.
SCRAPER_REGISTRY = {
    "no_sodir_field_production_monthly": {
        "source": "no_sodir",
        "class": "scrapers.no_sodir.field_production_monthly.NoSodirFieldProductionMonthly",
    },
    # More datasets added here as they are implemented
}
