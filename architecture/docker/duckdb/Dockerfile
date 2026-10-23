FROM debian:12-slim

# Must be the same version as `duckdb==` in requirements.txt (the app talks
# to this server over quack).
ARG DUCKDB_VERSION=2.0.0

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --create-home --home-dir /opt/duckdb duckdb

USER duckdb
ENV HOME=/opt/duckdb
# Official install script; installs to $HOME/.duckdb/cli/<version>/duckdb (+ cli/latest)
RUN curl -fsSL https://install.duckdb.org | DUCKDB_VERSION=${DUCKDB_VERSION} sh \
 && mkdir -p /opt/duckdb/.duckdb/extensions

COPY --chown=duckdb entrypoint.sh /opt/duckdb/entrypoint.sh
# Strip CRLF in case the repo was checked out on Windows
RUN sed -i 's/\r$//' /opt/duckdb/entrypoint.sh && chmod 755 /opt/duckdb/entrypoint.sh

# sql/ddl is mounted here by compose
WORKDIR /opt/duckdb/ddl
EXPOSE 9494
ENTRYPOINT ["/opt/duckdb/entrypoint.sh"]
