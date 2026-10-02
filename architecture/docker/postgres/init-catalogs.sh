#!/bin/sh
# One DuckLake catalog per layer: database cat_hydroc_<layer> owned by
# user_hydroc_<layer>. Runs once, when the Postgres data volume is empty.
set -eu

for layer in lake library dwh hook; do
    var="PG_PASSWORD_$(echo "$layer" | tr '[:lower:]' '[:upper:]')"
    eval "password=\${$var}"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" \
        -v user="user_hydroc_$layer" -v db="cat_hydroc_$layer" -v pw="$password" <<'SQL'
CREATE USER :"user" WITH PASSWORD :'pw';
CREATE DATABASE :"db" OWNER :"user";
SQL
done
