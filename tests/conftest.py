import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _stop_quack_servers():
    """Stop the quack servers a test started to run dbt (tests/library_dbt.py)."""
    yield
    import library_dbt

    library_dbt.stop_all()
