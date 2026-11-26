"""
dbt-duckdb plugin: run every dbt statement on the DuckDB quack server.

dbt-duckdb has no quack support. It opens a local in-memory database and gives
each thread its own cursor; CONNECT applies to one connection only, so a cursor
opened after it would not be connected. This plugin runs CONNECT on every
cursor, so all SQL executes on the server, like storage/duck.py. The client
needs no catalog credentials.

Configured in transform/profiles.yml:

  plugins:
    - module: storage.dbt_quack
      config:
        url: quack:<host>:9494
        token: <quack token>
        disable_ssl: "true"            # quack_serve speaks plain HTTP

dbt-duckdb can't tell that the server's catalogs are DuckLakes (it only knows
the ones it attaches itself), so transform/macros/drop_relation.sql drops
without CASCADE, which DuckLake rejects.
"""

from __future__ import annotations

from dbt.adapters.duckdb.plugins import BasePlugin


def _literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


class Plugin(BasePlugin):
    def initialize(self, config):
        self.url = config["url"]
        self.token = config["token"]
        self.disable_ssl = str(config.get("disable_ssl", "false")).lower() == "true"
        if not self.url:
            raise ValueError("dbt_quack: url is empty (set HYDROC_QUACK_URL)")

    def configure_cursor(self, cursor):
        cursor.execute("LOAD quack")
        cursor.execute(f"CREATE SECRET IF NOT EXISTS quack_server (TYPE quack, TOKEN {_literal(self.token)})")
        options = " (DISABLE_SSL true)" if self.disable_ssl else ""
        cursor.execute(f"CONNECT {_literal(self.url)}{options}")
