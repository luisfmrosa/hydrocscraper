#!/bin/sh
# Render /opt/duckdb/secrets.sql from the environment (the Docker counterpart of
# the Incus Ansible template), then start the server with sql/ddl/init_server.sql.
# Values are embedded in SQL literals: they must not contain single quotes.
set -eu

: "${QUACK_PORT:?}" "${QUACK_TOKEN:?}" "${S3_ENDPOINT:?}" "${S3_ACCESS_KEY:?}" "${S3_SECRET_KEY:?}" "${PG_HOST:?}"

umask 077
{
    echo "-- Rendered by entrypoint.sh. Contains credentials."
    echo "SET VARIABLE quack_address = 'quack:0.0.0.0:${QUACK_PORT}';"
    echo "SET VARIABLE quack_token = '${QUACK_TOKEN}';"

    # RustFS: one root key for every bucket, plain HTTP inside the compose network
    for layer in raw lake library dwh hook; do
        echo "CREATE SECRET s3_${layer} (TYPE s3, KEY_ID '${S3_ACCESS_KEY}', SECRET '${S3_SECRET_KEY}', ENDPOINT '${S3_ENDPOINT}', URL_STYLE 'path', USE_SSL false, REGION 'us-east-1', SCOPE 's3://hydroc-${layer}');"
    done

    # DuckLake: catalog in Postgres cat_hydroc_<layer>, data in s3://hydroc-<layer>/
    for layer in lake library dwh hook; do
        var="PG_PASSWORD_$(echo "$layer" | tr '[:lower:]' '[:upper:]')"
        eval "password=\${$var:?}"
        echo "CREATE SECRET pg_${layer} (TYPE postgres, HOST '${PG_HOST}', PORT 5432, DATABASE 'cat_hydroc_${layer}', USER 'user_hydroc_${layer}', PASSWORD '${password}');"
        echo "CREATE SECRET ducklake_${layer} (TYPE ducklake, METADATA_PATH '', DATA_PATH 's3://hydroc-${layer}/', METADATA_PARAMETERS MAP {'TYPE': 'postgres', 'SECRET': 'pg_${layer}'});"
    done
} > /opt/duckdb/secrets.sql

# quack_serve() returns immediately; an open stdin keeps the CLI running.
exec sh -c 'tail -f /dev/null | exec /opt/duckdb/.duckdb/cli/latest/duckdb -init init_server.sql'
