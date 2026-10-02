"""
Canonical production record schema.

Unified, source-independent shape of a production record — the target for
the future dwh.supply model. Individual scrapers parse raw files into lists
of ProductionRecord.
"""

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(slots=True)
class ProductionRecord:
    # Provenance
    source: str          # e.g. "npd", "jodi_oil"
    source_file: str     # originating raw file

    # Location
    country_iso3: str    # ISO 3166-1 alpha-3 (e.g. "NOR")
    region: str = ""     # Province / state (if available)
    field_name: str = "" # Field name (if available)
    well_id: str = ""    # Well identifier (if available)

    # Time
    period: date = field(default_factory=date.today)  # First day of reference month

    # Commodity & volume
    commodity: str = ""        # "crude_oil" | "natural_gas" | "ngl" | "condensate" | "oe"
    value: float = 0.0         # Production volume
    unit: str = ""             # e.g. "mill_sm3_month", "kb/d"

    # Metadata
    scraped_at: datetime = field(default_factory=datetime.utcnow)

    def period_str(self) -> str:
        """Return the period as 'YYYY-MM'."""
        return self.period.strftime("%Y-%m")


# Commodity constants — use these in scrapers for consistency
class Commodity:
    CRUDE_OIL = "crude_oil"
    NATURAL_GAS = "natural_gas"
    NGL = "ngl"
    CONDENSATE = "condensate"
    OIL_EQUIVALENT = "oe"
    WATER = "water"
