-- quack_serve returns immediately; the systemd unit keeps the CLI alive.
-- quack_address and quack_token are set in secrets.sql.
-- allow_other_hostname: quack only binds to localhost by default. The port is
-- reachable only on the private hydroc-br0 bridge (no TLS in quack).
CALL quack_serve(
    getvariable('quack_address'),
    token = getvariable('quack_token'),
    allow_other_hostname = true
);
