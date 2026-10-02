# Introduction

This file describes a proposition of a major overhaul of this project.

The main goals of these changes:

* adapt the project structure to be "cloud-ready"
* conform the project to Hook methodology

The following sessions describe how the new version of the project should look like.

# Architecture

The project must be "cloud-ready". This means the following:

* data storage must be S3-API compatible
* DuckDB "server" must run inside a container
* We will make use of DuckLake and we will use Postgres as the catalog
* Postgres must run on a separate container

## Infrastructure

For this first version, infrastructure must be built on top of a Incus server.

Infrastructure and configuration must be defined as code:

* OpenTofu with Incus extension to interact with Incus
* Ansible to define the configuration of each necessary container

these scripts must be stored in this project on the following folders:

- architecture/incus/tofu
- architecture/incus/ansible

An alternative Docker Compose setup, with RustFS as the S3 server, lives in `architecture/docker`.

Credentials should not be exposed to Github.

## Data layers and formats

The following structure must replace the existing layers described in Architecture.md (Layer: 0 and Layer 1). Lance format should not be used anymore.

The projects must have the following layers:

* *Raw* - used to store raw data for file or API-based data sources.
* *Lake* - it represents the "Lake" layer in Hook methodology.
* *Library* - this represents the "Data Library" layer in the Hook methodology.
* *DWH* - This layer to store business views built on top of the Library.
* *Hook* - This is a transversal layer used to store metadata and supportive objects.

Each layer has its own, dedicated S3 bucket, named "hydroc-<layer>".

Except the "Raw" layer, all layers are defined as a DuckLake object.

These DuckLake objects must be defined as follows:

* pointing to its own S3 bucket
* use the same Postgres instance as catalog, each DuckLake object having its dedicated Postgres database named "cat_hydroc_<layer>" and a dedicated Postgres user, "user_hydroc_<layer>".

This gives us more flexibility for future, necessary segregations.

### Raw layer

Files are written inside each `year_month=<period>` folder with a `_YYYYMMDD_HHmm` timestamp suffix (e.g. `field_production_monthly_20260929_1000.csv`). The period defaults to the month of the download; a scraper may use the reference period of the data instead.

This layer is just an S3 bucket where files are saved following this structure:

Bucket: hydroc-raw
   ./<data-source-1>
        /<dataset-1>
            ./year_month=<period-1>
                ./filename1
                ./filename2
                ./filename3
            ./year_month=<period-2>
                ./filename1
                ./filename2
                ./filename3
        /<dataset-2>
            ./year_month=<period-1>
                ./filename1
                ./filename2
                ./filename3
            ./year_month=<period-2>
                ./filename1
                ./filename2
                ./filename3
   ./<data-source-2>
        /<dataset-1>
            ./year_month=<period-1>
                ./filename1
                ./filename2
                ./filename3
            ./year_month=<period-2>
                ./filename1
                ./filename2
                ./filename3
        /<dataset-2>
            ./year_month=<period-1>
                ./filename1
                ./filename2
                ./filename3
            ./year_month=<period-2>
                ./filename1
                ./filename2
                ./filename3

These folders will be mapped as external, partitioned views in DuckDB when the underlying file format allows it.

## DuckDB Server scripts

We need a script that attaches all DuckLake objects and starts listening the quack protocol to create a "DuckDB server".

This script must be stored in this project at `sql/ddl`.

Implementation (`sql/ddl/init_server.sql`, run as `duckdb -init init_server.sql` in container `hydroc-duckdb`). At every start it:

1. loads the `httpfs`, `postgres`, `ducklake` and `quack` extensions;
2. reads `/opt/duckdb/secrets.sql` (rendered by Ansible, never committed): S3 secrets scoped per bucket and one DuckLake secret per layer;
3. attaches the four DuckLakes with fixed aliases `lake`, `library`, `dwh`, `hook`;
4. creates the objects described below (`IF NOT EXISTS` everywhere, so restarts are safe);
5. starts the quack listener: `quack_serve('quack:0.0.0.0:9494', token = ...)`.

Clients run `CONNECT 'quack:<host>:9494' (DISABLE_SSL true)` (with a `quack` secret holding the token); afterwards every statement executes on the server. Notes (DuckDB 2.0.0-dev):

* `quack_serve` returns immediately, so the systemd unit keeps the CLI's stdin open.
* The listener speaks plain HTTP only (clients set `disable_ssl`); the port stays on the private `hydroc-br0` bridge.
* Binding to `0.0.0.0` requires `allow_other_hostname = true`; by default quack accepts only localhost.
* Client and server must run the exact same DuckDB build (`duckdb==` in `requirements.txt`; `duckdb_staged` in Ansible, `DUCKDB_STAGED` in the Docker image); mismatched dev builds fail with HTTP 500.
* In Python, use `execute()` after `CONNECT` (`sql()` resolves names on the client), and render values as literals: bound parameters are not forwarded.
* The 2.0 dev builds need an AVX2 CPU; the homelab Incus server (Pentium J5005) has none.
* The init file runs with `.bail off`: views over empty Raw prefixes fail harmlessly until data exists. Restart the service to create them.

### Lake layer

This layer stores denormalized, incremental changes from the raw data sources.

This is an immutable layer: changes are always appended.

Suppose we have a raw dataset that is stored as hierachical JSON files: we first denormalize it into several tables before store it here.
Also, we store only changes detected to the same datasource:
    - new rows
    - modified rows
    - deleted rows

Each table must contain the following metadata columns:

- ___Lake_load_timestamp
- ___Lake_datasource
- ___Lake_sourcefile
- ___Lake_isdeleted

### Library layer

This DuckLake layer contains 2 schemas:

* *Frame* - this schema contains SCD2-like objects based on one object (no joins allowed) from "Lake" layer (a table, a view or a materialized view). It also contain the "Hook" columns associated with this object (defined by user at creation moment).
* *Latest* - this schema contains views created on top of *Frame* objects showing only the latest version of each row

### DWH layer

This layer is a space for business to create their views and models on top of the *Library* layer.

For the purpose of this project, it will initially contain only a schema, called *Supply*.

### Hook layer

This is the place to store metadata and supportive objects.

It will contain 2 schemas:

* *Metadata* - objects created to support Hook methodology
* *Raw_Views* - a space to store views mapping tables on top of "Raw" layer when convenient

#### Metadata schema

Metadata schema will contain tables supporting Hook methodology:

- *Sources* - a SCD2-like view on top of table "known_sources" from the raw layer.
- *Datasets* - a table describing all datasets extracted from each source.
- *Business_Concepts* - a table listing all identified business concepts.

This tables will be defined later.

# Application changes

## Discovery mode

### known_sources.json

The file `known_sources.json` must not be stored on the project workspace, but on the *Raw* layer.
It must be stored at `/metadata/known_sources`.
It execution of the discovery must generated a timestamped file and stored on this folder.
The timestamp mask: `%Y%m%d_%H%M`, in UTC (this granularity is enough for our purposes).

Examples:

/metadata
   /known_sources
         known_sources_20260929_1000.json
         known_sources_20260929_1130.json

#### New columns

The column "md5_digest" must be included.
It should be calculated as the result of MD5 calculated on the concatenation of all columns for each record.

To keep the digest unambiguous, columns are concatenated in a fixed order (`id, name, url, format, granularity, periodicity, scope, countries`), separated by the ASCII unit separator (`\x1f`); `null` becomes an empty string and lists are joined with `,` (see `utils/hashing.py`).

### watermark.json

This must be converted to a table in hook layer, metadata schema.

`hook.metadata.watermark` is append-only (one row per successful load) with columns `source, dataset, load_mode, last_period_fetched, status, raw_file, updated_at`. The view `hook.metadata.watermark_latest` returns the latest row per `(source, dataset)`.

