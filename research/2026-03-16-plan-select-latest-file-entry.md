# Plan: KARTEI History Deduplication

The `KARTEI` table stores a full edit history for each file entry. To avoid processing stale data, the extractor must be updated to return only the most recent version of each entry. This is achieved with a new query that partitions the rows by `FOLLOWERID`, ordered desc by ID, then picking the latest (smallest ID) from that partition. 

## Context

KARTEI is a historized table. When a file entry is edited, a new row is inserted.

- Original row: `FOLLOWERID = NULL`
- All subsequent versions: `FOLLOWERID` = `ID` of the original row (flat grouping key)
- Latest version = row with the highest `ID` within the chain (chain root = `COALESCE(k.FOLLOWERID, k.ID)`)
- Deduplication lives entirely in SQL (no Python logic).

---

## Phase 1 — Deduplicate history chains with a SQL window function

**Goal:** Replace the existing flat query in `read_source_entries` with a CTE that uses `ROW_NUMBER()` to rank rows within each history chain and filters to `rn = 1`, keeping only the latest version. 

### Changes

- `extractor.py` → `read_source_entries`: replace the existing SQL query with the CTE query below. No other Python changes required.

**SQL (embed in `read_source_entries`):**

```sql
WITH latest_entries AS (
    SELECT
        k.DATUM,
        k.PATNR,
        p.STATUS,
        k.BEMERKUNG,
        ROW_NUMBER() OVER (
            PARTITION BY COALESCE(k.FOLLOWERID, k.ID)
            ORDER BY k.ID DESC
        ) AS rn
    FROM {schema}.KARTEI AS k
    LEFT JOIN {schema}.PATKASSE AS p
        ON p.PATNR = k.PATNR
)
SELECT DATUM, PATNR, STATUS, BEMERKUNG
FROM latest_entries
WHERE rn = 1
ORDER BY DATUM, PATNR
```

### Unit tests (add to `test_extractor.py`)

- `test_read_source_entries_query_deduplicates_by_chain` — assert the captured query contains all of: `ROW_NUMBER()`, `PARTITION BY`, `COALESCE(k.FOLLOWERID, k.ID)`, `ORDER BY k.ID DESC`, `WHERE rn = 1`
- `test_read_source_entries_chain_returns_single_latest` — fake cursor returns a single row (simulating the DB result after dedup for a multi-version chain); assert exactly 1 `FileEntry` is returned with the expected field values
- `test_read_source_entries_original_only_chain` — fake cursor returns a single row with no followers (original-only chain); assert it is returned as a valid `FileEntry`

---

## Relevant files

- `src/clieno_extractor/extractor.py` — `FileEntry`, `read_source_entries` (SQL), `_write_full_output`
- `tests/test_extractor.py` — all existing and new tests

## Verification

1. Run `.venv/bin/python -m pytest -q` — all existing tests plus all new tests pass
2. Manually review the captured SQL string in test output to confirm all window function fragments are present

## Scope

- **Included:** SQL deduplication, unit tests
- **Excluded:** `FileEntry` model changes, CSV output columns, scheduler logic, config changes
