from pathlib import Path

# Root paths
PROJECT_ROOT = Path(__file__).parent
DATA_ROOT = PROJECT_ROOT / "data"
LAKE_ROOT = PROJECT_ROOT / "lake"

# HTTP defaults
HTTP_TIMEOUT = 120  # seconds — large files can be slow
HTTP_MAX_RETRIES = 4
HTTP_BACKOFF_MIN = 2   # seconds
HTTP_BACKOFF_MAX = 30  # seconds

# Registry: maps source_id -> scraper module/class name
# Used by main.py to resolve --sources arguments
SCRAPER_REGISTRY = {
    "npd": "scrapers.npd.NPDScraper",
    # More scrapers added here as they are implemented
}
