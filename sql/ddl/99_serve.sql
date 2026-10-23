-- quack_serve returns immediately; the systemd unit keeps the CLI alive.
-- quack_address and quack_token are set in secrets.sql.
-- allow_other_hostname: quack only binds to localhost by default.
-- disable_ssl: since DuckDB 2.0.0 quack serves HTTPS with a self-signed
-- certificate on any address but localhost; we keep plain HTTP, as the app
-- expects (HYDROC_QUACK_DISABLE_SSL). The port is reachable only on the
-- private hydroc-br0 bridge (Incus) or the Compose network, published on
-- 127.0.0.1 only (Docker).
CALL quack_serve(
    getvariable('quack_address'),
    token = getvariable('quack_token'),
    allow_other_hostname = true,
    disable_ssl = true
);
