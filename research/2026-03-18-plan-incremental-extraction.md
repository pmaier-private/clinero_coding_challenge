# Incremental Extraction with KARTEI.ID Checkpoint

Modify the extractor to emit only new entries by tracking the highest `KARTEI.ID` from the previous extraction cycle and filtering the SQL query to exclude already-exported rows. All state is stored directly in the output CSV via the technical column `t_kartei_id`. On the first run (no existing output CSV), all current deduplicated entries are exported to bootstrap the checkpoint. Each subsequent run appends only rows with a `KARTEI.ID` higher than the stored maximum.

---

## Phases

1. [Phase 1 — Add technical column `t_kartei_id` to data model and CSV output](#phase-1--add-technical-column-t_kartei_id-to-data-model-and-csv-output)
2. [Phase 2 — Implement checkpoint management](#phase-2--implement-checkpoint-management)
3. [Phase 3 — Transition to incremental append writes](#phase-3--transition-to-incremental-append-writes)
4. [Phase 4 — Add deduplication safeguard](#phase-4--add-deduplication-safeguard)

---

## Phase 1 — Add technical column `t_kartei_id` to data model and CSV output

**Objective:** Extend `FileEntry` to capture the source KARTEI.ID and write it to the output CSV as `t_kartei_id`. This is the foundation all later phases build on.

### Implementation steps

1. **Extend `FileEntry` dataclass** (`extractor.py`): add a `kartei_id: int` field to store the source KARTEI.ID for each row.

2. **Update SQL `SELECT` clause** (`read_source_entries` in `extractor.py`): add `k.ID` to the columns returned by the CTE's outer SELECT.  
   The outer SELECT becomes:
   ```sql
   SELECT k.ID, DATUM, PATNR, STATUS, BEMERKUNG
   FROM latest_entries
   WHERE rn = 1
   ORDER BY DATUM, PATNR
   ```

3. **Update cursor tuple unpacking** (`read_source_entries`): unpack the additional `k.ID` value from each row and pass it as `kartei_id` when constructing `FileEntry`.

4. **Update CSV writer** (`_write_full_output`): add `t_kartei_id` to the `fieldnames` list and populate it from `entry.kartei_id` in the row dict. The column must be prefixed `t_` as the technical column convention.

### Unit tests

- `test_file_entry_includes_kartei_id` — instantiate `FileEntry` with `kartei_id` and verify the dataclass stores and returns it correctly.
- `test_read_source_entries_captures_kartei_id` — use a fake cursor returning rows that include a KARTEI.ID value; assert the resulting `FileEntry` instances contain it in the `kartei_id` field.
- `test_write_full_output_includes_t_kartei_id_column` — call `_write_full_output` with entries that have `kartei_id` set; assert the CSV header contains `t_kartei_id` and each data row has the correct value.

---

## Phase 2 — Implement checkpoint management

**Objective:** Read the previous maximum KARTEI.ID from the output CSV and pass it to `read_source_entries` so the SQL query filters to only new rows. On the first run (no output CSV), pass `None` to export everything.

### Implementation steps

1. **Add helper `_read_previous_max_kartei_id(output_csv: Path) -> int | None`** (`extractor.py`):
   - Return `None` if `output_csv` does not exist.
   - Open the CSV, read all rows, and return `max(int(row["t_kartei_id"]) for row in rows)`.
   - Return `None` if the file exists but has no data rows (header-only).

2. **Extend `read_source_entries` signature** to accept `min_kartei_id: int | None = None`.

3. **Update SQL WHERE clause** to filter by `min_kartei_id` when it is not `None`. Use a parameterized query to avoid SQL injection:
   - When `min_kartei_id` is not `None`, append `AND k.ID > ?` to the outer `WHERE rn = 1` and bind the value via pyodbc's parameter substitution.
   - When `min_kartei_id` is `None` (first run), emit no extra filter clause.

4. **Update `run_cycle`** to:
   - Call `_read_previous_max_kartei_id(settings.output_csv)` before extraction.
   - Pass the result as `min_kartei_id` to `read_source_entries`.
   - Call `_write_full_output` (append behavior added in Phase 3) with the result.

### Unit tests

- `test_read_previous_max_kartei_id_nonexistent_csv` — output CSV does not exist; assert returns `None`.
- `test_read_previous_max_kartei_id_exists` — output CSV contains multiple rows with different `t_kartei_id` values; assert returns the maximum.
- `test_read_previous_max_kartei_id_empty_csv` — output CSV exists but contains only the header line; assert returns `None`.
- `test_read_source_entries_with_min_kartei_id_filters` — monkeypatch pyodbc; call `read_source_entries` with `min_kartei_id=100`; assert the captured query contains the parameterized filter for `k.ID > ?` and the bound value is `100`.
- `test_read_source_entries_min_kartei_id_none_no_filter` — call with `min_kartei_id=None`; assert the captured query does not include an additional `k.ID` filter clause.
- `test_run_cycle_bootstraps_checkpoint_on_first_run` — output CSV does not exist; monkeypatch `read_source_entries` to return a fixed list with known `kartei_id` values; assert `run_cycle` passes `min_kartei_id=None` and the output CSV contains all entries.

---

## Phase 3 — Transition to incremental append writes

**Objective:** Change `_write_full_output` from overwrite mode to append mode, so each extraction cycle accumulates new rows in the CSV instead of replacing it.


### Implementation steps

1. **Refactor `_write_full_output`** (`extractor.py`):
   - Check whether `output_csv` already exists and is non-empty.
   - **First write** (file absent or empty): open in write mode (`"w"`), write header, write data rows.
   - **Subsequent writes** (file exists with content): open in append mode (`"a"`), skip writing the header, write data rows only.

2. No changes to `run_cycle` — it already calls `_write_full_output` with the incremental entry list from Phase 2.

### Unit tests

- `test_write_output_writes_header_on_first_run` — output CSV does not exist; call `_write_full_output`; assert the resulting file has exactly one header line followed by all entry rows.
- `test_write_output_appends_rows_to_existing_csv` — create an output CSV with one data row; call `_write_full_output` with two new entries; assert the file now contains the original row plus the two new rows (three data rows total, single header).
- `test_write_output_no_duplicate_header_on_append` — output CSV exists with header and one row; call `_write_full_output` with new entries; assert the word `entry_date` (or any header field) appears exactly once in the file content.

---

## Phase 4 — Add deduplication safeguard

**Objective:** Prevent re-appending entries whose `t_kartei_id` is already present in the output CSV. This guards against edge cases where the checkpoint might be stale or incorrect.

*Depends on Phase 3.*

### Implementation steps

1. **Add helper `_read_existing_kartei_ids(output_csv: Path) -> set[int]`** (`extractor.py`):
   - Open the CSV and collect all values from the `t_kartei_id` column into a `set[int]`.
   - Return an empty set if the file does not exist or is empty.

2. **Extend `_write_full_output`** to accept `existing_kartei_ids: set[int]`:
   - Filter `entries` list, excluding any entry whose `kartei_id` is already in `existing_kartei_ids`.
   - Print a message (or use `logging`) if any entries are skipped (e.g., `f"Skipped {n} duplicate entries."`).

3. **Update `run_cycle`** to:
   - Call `_read_existing_kartei_ids(settings.output_csv)` before writing.
   - Pass the result to `_write_full_output`.

### Unit tests

- `test_read_existing_kartei_ids_nonexistent` — output CSV does not exist; assert returns empty set.
- `test_read_existing_kartei_ids_extracts_all_ids` — output CSV with multiple rows; assert the returned set contains every `t_kartei_id` value from the file.
- `test_write_output_skips_entries_with_existing_kartei_id` — call `_write_full_output` passing `existing_kartei_ids={100}`; include an entry with `kartei_id=100` and others with new IDs; assert only the new entries appear in the output file.
- `test_run_cycle_passes_existing_ids_to_writer` — monkeypatch `_write_full_output` to capture `existing_kartei_ids`; seed the output CSV with one row (id=42); call `run_cycle`; assert `existing_kartei_ids` passed to the writer contains `42`.
