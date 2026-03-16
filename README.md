The coding challenge for Clinero

The idea is to build a PoC of an extraction data pipeline for ivoris, for data 

* date
* patient id
* insurance state
* file entry
* services


# Requirements

* Update / Data transfer should happen daily, but only if there are changes in the file entries
* data shall be stored as csv
* data shall be retrievable through a REST API endpoint /ivorisextract/kartei
* the update / transfer interval shall be configurable
* The insurance status (Member, Family insured, Retired, or Private) should be captured in one column
* The date is the date of the file entry

# Nice-to-have

* incremental extract: only extract new data


# design

We have two components:

* An extractor that checks the ivoris MS SQL database for changes regularily (default: once per day). If there were new file entries, those entries are extracted and send to an API for storage.
* A storage and retrieval service that offers two endpoints: one for storing the data, and one for retrieving it.


# ML0

Just the extractor, which stores the data directly to csv! No service for data retrieval.


## Quick start

1. Create the environment and install the project:

	```bash
	uv sync
	```

2. Run one extraction cycle (recommended for local checks):

	```bash
	IVORIS_RUN_ONCE=true uv run ivoris-extractor
	```

3. Inspect output:

	* `data/output/ivoris_extract.csv`


## Configuration

Environment variables (see `.env.example`):

* `IVORIS_INTERVAL_SECONDS` (default `86400`)
* `IVORIS_SOURCE_CSV` (default `data/input/ivoris_file_entries.csv`, currently unused placeholder)
* `IVORIS_OUTPUT_CSV` (default `data/output/ivoris_extract.csv`)
* `IVORIS_RUN_ONCE` (`true`/`false`)


## Notes

* Current implementation is ML0 only (direct CSV storage, no REST API yet).
* Source reading is currently mocked and returns an empty set of entries.
* The extractor writes a full CSV snapshot every run (no incremental state/checkpoint).
* `extractor.py` is the integration point for the upcoming MS SQL implementation.

 