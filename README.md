Clinero Coding Challenge - Ivoris Extractor

The idea is to build a PoC of an extraction data pipeline for Ivoris, for data 

* date
* patient id
* insurance state
* file entry
* services


# Requirements

* Update / Data transfer should happen daily
* data shall be stored as csv
* data shall be retrievable through a REST API endpoint /ivorisextract/kartei
* the update / transfer interval shall be configurable
* The insurance status (Member, Family insured, Retired, or Private) should be captured in one column
* The date is the date of the file entry


**Note:** Current implementation is ML0: direct CSV storage, no REST API yet.


# Nice-to-have

* incremental extract: only extract new data

# Quick start

0. Install prerequisites:
* Ivoris
* [Python 3.11+](https://www.python.org/downloads/)
* [uv](https://docs.astral.sh/uv/getting-started/installation/)

1. Create the environment and install the project:

	```bash
	uv sync
	```

**Note:** Under Windows you may have to replace `uv` with `py -m uv` in the above and following commands.

2. Run one extraction cycle (recommended for local checks):

	```bash
	IVORIS_RUN_ONCE=true uv run ivoris-extractor
	```

3. Inspect output:

	* `data/output/ivoris_extract.csv`

## Tests

```bash
uv run --dev python -m pytest
```

## Configuration

Environment variables (see `.env.example`):

* `IVORIS_INTERVAL_SECONDS` (default `86400`)
* `IVORIS_OUTPUT_CSV` (default `data/output/ivoris_extract.csv`)
* `IVORIS_RUN_ONCE` (`true`/`false`)
* `IVORIS_DB_SERVER` (default `localhost`)
* `IVORIS_DB_NAME` (default `DentalDB`)
* `IVORIS_DB_SCHEMA` (default `ck`)
* `IVORIS_DB_DRIVER` (default `ODBC Driver 17 for SQL Server`)


# design

We have two components:

* An extractor that checks the ivoris MS SQLServer database for changes regularily (default: once per day). If there were new file entries, those entries are extracted and send to an API for storage.
* A storage and retrieval service that offers two endpoints: one for storing the data, and one for retrieving it.

## ML0

Just the extractor, which stores the data directly to csv! No service for data retrieval.

## decisions

1. Data access through REST API: This allows for a more flexible and scalable architecture, as the data can be accessed by multiple clients and services without direct access to storage. For example, the service could be put onto a different machine / node, or in the cloud.

2. Configuration through environment variables: Wide support for defining different configurations in different technical environments, e.g. in cloud services. The trade-off is less readability and flexibility, e.g. compared to a yaml file.

3. uv as project manager: uv is modern, relatively simple and fast. However, for multi-lingual projects, e.g. including a TS+React frontend, we could use pants, which is more complex but also more powerful and flexible. 




 