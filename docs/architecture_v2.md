# Introduction

This file describes a proposition of a major overhaul of this project.

The main goals of these changes:

* adapt the project structure to be "cloud-ready"
* conform the project to Hook methodology

The following sections describe how the new version of the project should look like.

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

* *Raw* - used to store raw data from data sources, as received.
* *Std* - standardised data: every Raw file converted to typed Parquet (and flattened when needed). The Lake loads from here.
* *Lake* - it represents the "Lake" layer in Hook methodology.
* *Library* - this represents the "Data Library" layer in the Hook methodology.
* *DWH* - This layer to store business views built on top of the Library.
* *Hook* - This is a transversal layer used to store metadata and supportive objects.

Each layer has its own, dedicated S3 bucket, named "hydroc-<layer>".

Except the "Raw" and "Std" layers (plain buckets of files), all layers are defined as a DuckLake object.

These DuckLake objects must be defined as follows:

* pointing to its own S3 bucket
* use the same Postgres instance as catalog, each DuckLake object having its dedicated Postgres database named "cat_hydroc_<layer>" and a dedicated Postgres user, "user_hydroc_<layer>".

This gives us more flexibility for future, necessary segregations.

### Raw layer

This layer is just an S3 bucket where files are saved, as received, following this structure:

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
   ./<data-source-2>
        /<dataset-1>
            ./year_month=<period-1>
                ./filename1
                ./filename2
                ./filename3

Files are written inside each `year_month=<period>` folder with a `_YYYYMMDD_HHmm` timestamp suffix in UTC (e.g. `npd/field_production_monthly/year_month=2026-09/field_production_monthly_20260929_1000.csv`). The period defaults to the month of the download; a scraper may use the reference period of the data instead.

Python only collects data. Depending on the source:

1. **A file DuckDB can read** (CSV, TSV, xlsx, JSON, Parquet…): stored as received.
2. **A legacy format DuckDB can't read** (e.g. `.xls`, HTML): stored as received, **plus** a Parquet conversion written next to it with the same period and timestamp. The conversion is dataset-specific (e.g. which tab to load) and keeps the values as received: typing and checks belong to the Std step.
3. **A database table or an API read with an SDK**: the extract is written as Parquet; that file is what was received.

Every dataset has a raw view, `hook.raw_views.<source>_<dataset>`, over the files DuckDB reads (in case 2, the Parquet conversions). It maps them as received (CSV-like files as text) and adds the `___Raw_*` metadata columns: file name, `year_month`, file timestamp.

Keeping every source in Raw means Std can always be rebuilt from Raw.

### Std layer

This layer is an S3 bucket, `hydroc-std`, holding every Raw file converted to typed Parquet. It is derived data: it can be rebuilt from Raw at any time, and a full load does so. All transformations from here on (Raw → Std → Lake) are static SQL scripts run on the DuckDB server.

* **Std script**, `sql/std/<source>/<dataset>.sql`: dataset-specific; reads **one** Raw file through the raw view (the file is passed as the variable `raw_file`), checks its columns against the expected list, casts types, flattens when needed and writes one Parquet file per Std table with `COPY … TO`. A schema change or a value that doesn't cast fails the step: data-quality expectations (column values) are added here too.
* **Std view**, `hook.std_views.<code>`: one per Std table, over its Parquet files, with the `___Std_*` metadata columns (MD5 of the non-key columns, file name, `year_month`, file timestamp). The Lake loads read these views.

Std files keep the `year_month` and timestamp of the Raw file they come from. This links them to their Raw file and the watermark, and the timestamp becomes `___Lake_load_timestamp`.

Bucket: hydroc-std
   ./<data-source>
        /<dataset>                             (tabular dataset)
            ./year_month=<period>
                ./<source>_<dataset>_<YYYYMMDD_HHmm>.parquet
        /<dataset>_<sub_table>                 (one per flattened table)
            ./year_month=<period>
                ./<source>_<dataset>_<sub_table>_<YYYYMMDD_HHmm>.parquet

#### Flattened tables

Flattening happens **only** for non-tabular datasets (e.g. JSON with nested structures). It is part of the Std script and is intrinsically dataset-specific: one Std table per independent structure, including the top level.

* Every table except the top level has an additional column `parent`, allowing to link back to the parent table: the parent row's business key values, cast to text and joined with the ASCII unit separator (`chr(31)`).
* A flattened table's business key is `parent` plus its own key columns.
* A non-tabular format DuckDB can't read (e.g. HTML) is first converted by Python to a readable, still nested or tabular, Parquet file in Raw (case 2 above); the Std script flattens it.

#### Duplication

Std duplicates Raw. This is accepted: Parquet is compressed (for NPD, Std takes about 35% of the Raw CSV size), and Std is a rebuildable cache, never a source of truth. Std keeps its full history, since the Lake's full load replays every Std file.

## DuckDB Server scripts

We need a script that attaches all DuckLake objects and starts listening the quack protocol to create a "DuckDB server".

This script must be stored in this project at `sql/ddl`.

Implementation (`sql/ddl/init_server.sql`, run as `duckdb -init init_server.sql` in container `hydroc-duckdb`). At every start it:

1. loads the `httpfs`, `postgres`, `ducklake` and `quack` extensions;
2. reads `/opt/duckdb/secrets.sql` (rendered by Ansible, never committed): S3 secrets scoped per bucket (including `hydroc-raw` and `hydroc-std`) and one DuckLake secret per layer;
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
* The init file runs with `.bail off`: views over empty Raw or Std prefixes fail harmlessly until data exists. The app recreates them before each step.

### Lake layer

This layer stores incremental changes from the raw data sources.

Every Lake table is loaded from one Std table, through its std view, always in SQL on the DuckDB server. There is one Lake table per row of `datasets.csv` that has keys: `lake.<source>.<dataset>` for a tabular dataset, `lake.<source>.<dataset>_<sub_table>` for a flattened table.

We will have one schema per data source.

Example: For npd, we will have a dedicated schema `npd`.

This is an immutable layer: changes are always appended.

Also, we store only changes detected to the same datasource:
    - new rows
    - modified rows
    - deleted rows

Each table must contain the following metadata columns:

- ___Lake_md5: the result of MD5() on the concat of non-key columns.
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

It will contain 3 schemas:

* *Metadata* - objects created to support Hook methodology
* *Raw_Views* - views mapping the files of the "Raw" layer as received (read by the Std scripts)
* *Std_Views* - views mapping the Parquet files of the "Std" layer (read by the Lake loads)

#### Metadata schema

Metadata schema will contain tables supporting Hook methodology:

- *Sources* - a SCD2-like table describing existing data sources.
- *Datasets* - a table describing each dataset extracted from each source.
- *Business_Concepts* - a table listing all identified business concepts.
- *Hooks* - a table carrying the definition of each defined hook.

At init time, these files must be copied to the S3 bucket `hydroc-raw/metadata/<filename>/<filename>.csv`.

##### Sources

This table stores information about existing data sources.
Its content is static. It should be updated everytime a new dataset is implemented. It must be stored in this project at
`/data/static/sources.csv`.

This file must contain the following columns:

+==============+=========================+===========================================+
| Column name  | Description             | Example                                   |
+==============+=========================+===========================================+
| id           | Surrogate key           | 1                                         |
+--------------+-------------------------+-------------------------------------------+
| code         | Natural key             | jodi                                      |
+--------------+-------------------------+-------------------------------------------+
| name         | Name of the data source | Jodi - Joint Organizations Data Initiative|
+--------------+-------------------------+-------------------------------------------+
| scope        | Public or Private       | Private                                   |
+--------------+-------------------------+-------------------------------------------+
| url          | Link to the website     | https://www.jodidata.org/                 |
+--------------+-------------------------+-------------------------------------------+

##### Datasets

This table stores information about each extracted dataset.
Its content is static. It should be updated everytime a new dataset is implemented.
It must be stored at `/data/static/datasets.csv`.

There is one row per Std/Lake table:

* a tabular dataset has one row, with its `keys` and an empty `parent_code`;
* a non-tabular dataset has one row for the downloaded dataset (empty `keys`: it has no Std/Lake table of its own) and one row per flattened table (`code` = `<source>_<dataset>_<sub_table>`, its own `keys`, starting with `parent` where it applies). `parent_code` is the code of the row it derives from: the downloaded dataset for the top level, the parent table for a nested one. The app follows `parent_code` to find every table a download feeds.

This file must contain the following columns:

+==============+=========================+===========================================+
| Column name  | Description             | Example                                   |
+==============+=========================+===========================================+
| id           | Surrogate key           | 1                                         |
+--------------+-------------------------+-------------------------------------------+
| code         | Natural key             | jodi_iol                                  |
+--------------+-------------------------+-------------------------------------------+
| name         | Name of the dataset     | JODI Oil                                  |
+--------------+-------------------------+-------------------------------------------+
| source_id    | Source surrogate key    | 1                                         |
+--------------+-------------------------+-------------------------------------------+
| copyright    | Yes or no               | No                                        |
+--------------+-------------------------+-------------------------------------------+
| type         | Source type             | FILE, API, TABLE                          |
+--------------+-------------------------+-------------------------------------------+
| format       | File format             | CSV                                       |
+--------------+-------------------------+-------------------------------------------+
| parent_code  | Row it derives from     | jodi_oil_doc (empty if none)              |
+--------------+-------------------------+-------------------------------------------+
| granularity  | Level of detail         | country                                   |
+--------------+-------------------------+-------------------------------------------+
| periodicity  | Level of time detail    | monthly                                   |
+--------------+-------------------------+-------------------------------------------+
| keys         | List of keys            | field, period                             |
+--------------+-------------------------+-------------------------------------------+
| url          | Link to the website     | https://www.jodidata.org/oil/             |
+--------------+-------------------------+-------------------------------------------+

##### Business_Concepts

This table stores information about business concepts, defined manually.
Its content is static. It should be updated everytime a new dataset is implemented.
It must be stored at `/data/static/business_concepts.csv`.

This file must contain the following columns:

+==============+=========================+==============================================+
| Column name  | Description             | Example                                      |
+==============+=========================+==============================================+
| id           | Surrogate key           | 1                                            |
+--------------+-------------------------+----------------------------------------------+
| code         | Natural key             | Field                                        |
+--------------+-------------------------+----------------------------------------------+
| name         | Business concept name   | Field                                        |
+--------------+-------------------------+----------------------------------------------+
| description  | Free text               | Geographical area of provenance of a product |
+--------------+-------------------------+----------------------------------------------+

##### Hooks

This table stores information about hooks, defined manually.
Its content is static. It should be updated everytime a new hook is implemented.
It must be stored at `/data/static/hooks.csv`.

This file must contain the following columns:

+==============+=========================+==============================================+
| Column name  | Description             | Example                                      |
+==============+=========================+==============================================+
| id           | Surrogate key           | 1                                            |
+--------------+-------------------------+----------------------------------------------+
| code         | Natural key             | field                                        |
+--------------+-------------------------+----------------------------------------------+
| name         | Hook name               | Field                                        |
+--------------+-------------------------+----------------------------------------------+
| description  | Free text               | Geographical area of provenance of a product |
+--------------+-------------------------+----------------------------------------------+

# Application changes

## Discovery mode

Discovery was removed from the application in v2 (static metadata in `data/static/` replaces it). This section is kept for reference only.

### known_sources.json (deprecated)

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

To keep the digest unambiguous, columns are concatenated in a fixed order (`id, name, url, format, granularity, periodicity, scope, countries`), separated by the ASCII unit separator (`\x1f`); `null` becomes an empty string and lists are joined with `,`.

### watermark.json

This must be converted to a table in hook layer, metadata schema.

`hook.metadata.watermark` is append-only (one row per successful load) with columns `source, dataset, load_mode, last_period_fetched, status, raw_file, updated_at`. The view `hook.metadata.watermark_latest` returns the latest row per `(source, dataset)`.

Watermarks are kept per downloaded dataset, and `raw_file` is the key of the Raw file the Std script reads (the Parquet conversion in case 2). Std/Lake tables have no watermark of their own: their incremental load reads the Std file that shares the `year_month` and timestamp suffix of the watermark's Raw file.

Each step of a load appends a row with its `status`: `raw` (stored in Raw), `std` (converted to Std), `lake` (loaded into the Lake). An incremental run first finishes a file left at `raw` or `std`, so a failed step is retried on the next run. A full run converts every Raw file that has no Std file yet (every Raw file with `--rebuild-std`, e.g. after a Std script change), then reloads the Lake by replaying every Std file. Even when each file is a complete snapshot (e.g. NPD), the replay is kept: the Lake's history of changes between downloads only exists by comparing consecutive files.

