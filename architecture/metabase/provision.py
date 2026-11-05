"""
Provision Metabase for hydrocscraper through its REST API (standard library
only, so it runs in any python3: the metabase-init container on Docker, the
hydroc-metabase container on Incus).

Idempotent; every run brings Metabase to this state:
  1. first-run setup done, with the admin MB_ADMIN_EMAIL / MB_ADMIN_PASSWORD
     (on later runs: logs in with them);
  2. a database connection "hydroc serve" to Postgres hydroc_serve, schema
     latest only, as the read-only user_metabase;
  3. a collection "hydroc" holding the questions below and the dashboard
     "Sodir - Norwegian shelf production" (updated in place, found by name).

Environment:
  MB_URL              Metabase base URL (default http://127.0.0.1:3000)
  MB_ADMIN_EMAIL      admin e-mail (required)
  MB_ADMIN_PASSWORD   admin password (required; Metabase rejects weak ones)
  SERVE_HOST          Postgres host of hydroc_serve (required)
  SERVE_PORT          default 5432
  SERVE_USER          default user_metabase
  SERVE_PASSWORD      required

The questions are native SQL over serve.latest (the copies of the Library
latest views, production mode): they don't depend on Metabase's table ids,
and they show an error until the first Lake load has filled the copies.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

MB_URL = os.environ.get("MB_URL", "http://127.0.0.1:3000").rstrip("/")
DATABASE_NAME = "hydroc serve"
COLLECTION_NAME = "hydroc"
DASHBOARD_NAME = "Sodir - Norwegian shelf production"
DASHBOARD_DESCRIPTION = (
    "Norwegian Offshore Directorate (Sodir) data from the Library layer "
    "(library.latest.no_sodir_*), served from Postgres hydroc_serve.latest. "
    "Volumes in million standard cubic metres (Sm3; gas in billion Sm3)."
)

# Latest 12 months present in the data (Sodir lags a few months behind today)
LAST_12 = """
WITH bounds AS (
    SELECT max(make_date("prfYear", "prfMonth", 1)) AS last_month
    FROM latest.no_sodir_field_production_monthly
)"""

# name -> (display, SQL, visualization settings, (row, col, width, height))
CARDS: dict[str, tuple[str, str, dict, tuple[int, int, int, int]]] = {
    "Oil equivalent, last 12 months (mill. Sm3)": (
        "scalar",
        LAST_12 + """
SELECT round(sum(p."prfPrdOeNetMillSm3")::numeric, 1) AS oe_mill_sm3
FROM latest.no_sodir_field_production_monthly p, bounds b
WHERE make_date(p."prfYear", p."prfMonth", 1) > b.last_month - INTERVAL '12 months'""",
        {},
        (0, 0, 6, 4),
    ),
    "Producing fields, latest month": (
        "scalar",
        LAST_12 + """
SELECT count(DISTINCT p."prfNpdidInformationCarrier") AS fields
FROM latest.no_sodir_field_production_monthly p, bounds b
WHERE make_date(p."prfYear", p."prfMonth", 1) = b.last_month
  AND p."prfPrdOeNetMillSm3" > 0""",
        {},
        (0, 6, 6, 4),
    ),
    "Latest production month": (
        "scalar",
        LAST_12 + """
SELECT to_char(last_month, 'YYYY-MM') AS latest_month FROM bounds""",
        {},
        (0, 12, 6, 4),
    ),
    "Remaining reserves (mill. Sm3 o.e.)": (
        "scalar",
        """
SELECT round(sum("cmpRemainingOE")::numeric, 0) AS remaining_oe_mill_sm3
FROM latest.no_sodir_company_reserves""",
        {},
        (0, 18, 6, 4),
    ),
    "Monthly net production by product": (
        "line",
        """
SELECT make_date("prfYear", "prfMonth", 1)  AS month,
       sum("prfPrdOilNetMillSm3")           AS "Oil (mill. Sm3)",
       sum("prfPrdGasNetBillSm3")           AS "Gas (bill. Sm3)",
       sum("prfPrdNGLNetMillSm3")           AS "NGL (mill. Sm3)",
       sum("prfPrdCondensateNetMillSm3")    AS "Condensate (mill. Sm3)"
FROM latest.no_sodir_field_production_monthly
GROUP BY 1
ORDER BY 1""",
        {
            "graph.dimensions": ["month"],
            "graph.metrics": ["Oil (mill. Sm3)", "Gas (bill. Sm3)", "NGL (mill. Sm3)", "Condensate (mill. Sm3)"],
            "graph.x_axis.title_text": "Month",
        },
        (4, 0, 24, 8),
    ),
    "Top 15 fields, last 12 months (mill. Sm3 o.e.)": (
        "row",
        LAST_12 + """
SELECT p."prfInformationCarrier" AS field,
       round(sum(p."prfPrdOeNetMillSm3")::numeric, 2) AS oe_mill_sm3
FROM latest.no_sodir_field_production_monthly p, bounds b
WHERE make_date(p."prfYear", p."prfMonth", 1) > b.last_month - INTERVAL '12 months'
GROUP BY 1
ORDER BY 2 DESC
LIMIT 15""",
        {"graph.dimensions": ["field"], "graph.metrics": ["oe_mill_sm3"]},
        (12, 0, 12, 9),
    ),
    "Production by current operator, last 12 months (mill. Sm3 o.e.)": (
        "row",
        LAST_12 + """
SELECT coalesce(f."cmpLongName", '(no field record)') AS operator,
       round(sum(p."prfPrdOeNetMillSm3")::numeric, 2) AS oe_mill_sm3
FROM latest.no_sodir_field_production_monthly p
CROSS JOIN bounds b
LEFT JOIN latest.no_sodir_field f ON f."fldNpdidField" = p."prfNpdidInformationCarrier"
WHERE make_date(p."prfYear", p."prfMonth", 1) > b.last_month - INTERVAL '12 months'
GROUP BY 1
ORDER BY 2 DESC
LIMIT 15""",
        {"graph.dimensions": ["operator"], "graph.metrics": ["oe_mill_sm3"]},
        (12, 12, 12, 9),
    ),
    "Remaining reserves by company, top 15 (mill. Sm3 o.e.)": (
        "row",
        """
SELECT "cmpLongName" AS company,
       round(sum("cmpRemainingOE")::numeric, 1) AS remaining_oe_mill_sm3
FROM latest.no_sodir_company_reserves
GROUP BY 1
ORDER BY 2 DESC
LIMIT 15""",
        {"graph.dimensions": ["company"], "graph.metrics": ["remaining_oe_mill_sm3"]},
        (21, 0, 12, 9),
    ),
    "Fields by current activity status": (
        "pie",
        """
SELECT "fldCurrentActivitySatus" AS status, count(*) AS fields
FROM latest.no_sodir_field
GROUP BY 1
ORDER BY 2 DESC""",
        {"pie.dimension": "status", "pie.metric": "fields"},
        (21, 12, 12, 9),
    ),
}


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value:
        sys.exit(f"provision.py: {name} is not set")
    return value


class Metabase:
    def __init__(self, url: str) -> None:
        self.url = url
        self.session: str | None = None

    def call(self, method: str, path: str, body: object | None = None) -> object:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.session:
            req.add_header("X-Metabase-Session", self.session)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            sys.exit(f"provision.py: {method} {path} -> HTTP {exc.code}: {exc.read().decode(errors='replace')[:500]}")
        return json.loads(raw) if raw else None

    def wait_healthy(self, timeout: int = 600) -> None:
        deadline = time.monotonic() + timeout
        while True:
            try:
                with urllib.request.urlopen(self.url + "/api/health", timeout=10) as resp:
                    if json.loads(resp.read()).get("status") == "ok":
                        return
            except (OSError, ValueError):
                pass
            if time.monotonic() > deadline:
                sys.exit(f"provision.py: Metabase at {self.url} not healthy after {timeout}s")
            time.sleep(5)


def items(response: object) -> list[dict]:
    """List endpoints return either a list or {"data": [...]}."""
    return response["data"] if isinstance(response, dict) else response  # type: ignore[index,return-value]


def login(mb: Metabase, email: str, password: str) -> None:
    props = mb.call("GET", "/api/session/properties")
    if not props.get("has-user-setup"):  # type: ignore[union-attr]
        result = mb.call("POST", "/api/setup", {
            "token": props["setup-token"],  # type: ignore[index]
            "user": {"email": email, "password": password, "first_name": "hydroc", "last_name": "admin",
                     "site_name": "hydroc"},
            "prefs": {"site_name": "hydroc", "allow_tracking": False},
        })
        print("Metabase: first-run setup done")
    else:
        result = mb.call("POST", "/api/session", {"username": email, "password": password})
    mb.session = result["id"]  # type: ignore[index]


def ensure_database(mb: Metabase) -> int:
    details = {
        "host": env("SERVE_HOST"),
        "port": int(os.environ.get("SERVE_PORT", "5432")),
        "dbname": "hydroc_serve",
        "user": os.environ.get("SERVE_USER", "user_metabase"),
        "password": env("SERVE_PASSWORD"),
        "ssl": False,
        "schema-filters-type": "inclusion",
        "schema-filters-patterns": "latest",
    }
    for db in items(mb.call("GET", "/api/database")):
        if db["name"] == DATABASE_NAME:
            mb.call("PUT", f"/api/database/{db['id']}", {"details": details})
            database_id = db["id"]
            break
    else:
        database_id = mb.call("POST", "/api/database", {  # type: ignore[index]
            "engine": "postgres", "name": DATABASE_NAME, "details": details,
            "is_full_sync": True, "auto_run_queries": True,
        })["id"]
        print(f"Metabase: database '{DATABASE_NAME}' added")
    mb.call("POST", f"/api/database/{database_id}/sync_schema")
    return database_id


def ensure_collection(mb: Metabase) -> int:
    for col in items(mb.call("GET", "/api/collection")):
        if col.get("name") == COLLECTION_NAME and not col.get("archived") and isinstance(col.get("id"), int):
            return col["id"]
    return mb.call("POST", "/api/collection", {"name": COLLECTION_NAME, "parent_id": None})["id"]  # type: ignore[index]


def ensure_cards(mb: Metabase, database_id: int, collection_id: int) -> dict[str, int]:
    existing = {
        c["name"]: c["id"]
        for c in items(mb.call("GET", "/api/card?f=all"))
        if c.get("collection_id") == collection_id and not c.get("archived")
    }
    ids = {}
    for name, (display, sql, viz, _) in CARDS.items():
        body = {
            "name": name,
            "collection_id": collection_id,
            "display": display,
            "type": "question",
            "dataset_query": {"type": "native", "database": database_id, "native": {"query": sql.strip()}},
            "visualization_settings": viz,
        }
        if name in existing:
            mb.call("PUT", f"/api/card/{existing[name]}", body)
            ids[name] = existing[name]
        else:
            ids[name] = mb.call("POST", "/api/card", body)["id"]  # type: ignore[index]
    return ids


def ensure_dashboard(mb: Metabase, collection_id: int, card_ids: dict[str, int]) -> int:
    for dash in items(mb.call("GET", "/api/dashboard")):
        if dash["name"] == DASHBOARD_NAME and dash.get("collection_id") == collection_id and not dash.get("archived"):
            dashboard_id = dash["id"]
            break
    else:
        dashboard_id = mb.call("POST", "/api/dashboard", {  # type: ignore[index]
            "name": DASHBOARD_NAME, "collection_id": collection_id,
        })["id"]
    dashcards = [
        {"id": -(i + 1), "card_id": card_ids[name], "row": row, "col": col, "size_x": w, "size_y": h,
         "parameter_mappings": [], "visualization_settings": {}}
        for i, (name, (_, _, _, (row, col, w, h))) in enumerate(CARDS.items())
    ]
    # Replaces the dashboard's cards with this layout
    mb.call("PUT", f"/api/dashboard/{dashboard_id}", {
        "description": DASHBOARD_DESCRIPTION, "dashcards": dashcards, "tabs": [],
    })
    return dashboard_id


def main() -> None:
    mb = Metabase(MB_URL)
    mb.wait_healthy()
    login(mb, env("MB_ADMIN_EMAIL"), env("MB_ADMIN_PASSWORD"))
    database_id = ensure_database(mb)
    collection_id = ensure_collection(mb)
    card_ids = ensure_cards(mb, database_id, collection_id)
    dashboard_id = ensure_dashboard(mb, collection_id, card_ids)
    print(f"Metabase: dashboard '{DASHBOARD_NAME}' ready: {MB_URL}/dashboard/{dashboard_id}")


if __name__ == "__main__":
    main()
