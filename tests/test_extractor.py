import csv
import sys
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from clieno_extractor import extractor as extractor_mod
from clieno_extractor.config import Settings
from clieno_extractor.extractor import FileEntry


def _read_output_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _read_output_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _build_settings(tmp_path: Path) -> Settings:
    return Settings(
        interval_seconds=86400,
        source_csv=tmp_path / "source.csv",
        output_csv=tmp_path / "ivoris_extract.csv",
        run_once=True,
        db_server="db-host",
        db_name="DentalDB",
        db_schema="ck",
        db_driver="ODBC Driver 18 for SQL Server",
    )


def test_file_entry_includes_kartei_id() -> None:
    entry = FileEntry(
        kartei_id=123,
        entry_date=date(2026, 3, 14),
        patient_id="PAT-001",
        insurance_state="Member",
        file_entry="Routine checkup",
        service="CHK001",
    )

    assert entry.kartei_id == 123


def test_read_source_entries_captures_kartei_id(monkeypatch, tmp_path: Path) -> None:
    captured = {"connection_string": "", "query": ""}

    rows = [
        (
            101,
            datetime(2026, 3, 14, 8, 30, 0),
            "PAT-001",
            "Member",
            "Routine checkup",
            "CHK001 XRAY010",
        ),
        (102, date(2026, 3, 15), "PAT-002", "Private", "Follow-up", "FUP050"),
        (
            103,
            "bad-date",
            "PAT-003",
            "Retired",
            "Ignored because date is invalid",
            "IGNORED",
        ),
    ]

    class FakeCursor:
        def execute(self, query: str, *params: object) -> None:
            captured["query"] = query

        def fetchall(self):
            return rows

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    def fake_connect(connection_string: str) -> FakeConnection:
        captured["connection_string"] = connection_string
        return FakeConnection()

    monkeypatch.setitem(sys.modules, "pyodbc", SimpleNamespace(connect=fake_connect))

    entries = extractor_mod.read_source_entries(_build_settings(tmp_path))

    assert entries == [
        FileEntry(
            kartei_id=101,
            entry_date=date(2026, 3, 14),
            patient_id="PAT-001",
            insurance_state="Member",
            file_entry="Routine checkup",
            service="CHK001 XRAY010",
        ),
        FileEntry(
            kartei_id=102,
            entry_date=date(2026, 3, 15),
            patient_id="PAT-002",
            insurance_state="Private",
            file_entry="Follow-up",
            service="FUP050",
        ),
    ]
    assert "Trusted_Connection=yes;" in captured["connection_string"]
    assert "DATABASE=DentalDB;" in captured["connection_string"]
    assert "FROM ck.KARTEI AS k" in captured["query"]
    assert "LEFT JOIN ck.PATKASSE AS p" in captured["query"]
    assert "WITH services_by_day AS" in captured["query"]
    assert "FROM ck.LEISTUNG AS l" in captured["query"]
    assert "STRING_AGG" in captured["query"]


def test_read_source_entries_query_deduplicates_by_chain(monkeypatch, tmp_path: Path) -> None:
    captured = {"query": ""}

    class FakeCursor:
        def execute(self, query: str, *params: object) -> None:
            captured["query"] = query

        def fetchall(self):
            return []

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    monkeypatch.setitem(
        sys.modules,
        "pyodbc",
        SimpleNamespace(connect=lambda _cs: FakeConnection()),
    )

    extractor_mod.read_source_entries(_build_settings(tmp_path))

    q = captured["query"]
    assert "ROW_NUMBER()" in q
    assert "PARTITION BY" in q
    assert "COALESCE(k.FOLLOWERID, k.ID)" in q
    assert "ORDER BY k.ID DESC" in q
    assert "WHERE rn = 1" in q
    assert "LEFT JOIN services_by_day AS s" in q
    assert "s.PATIENTID = k.PATNR" in q
    assert "s.DATUM = CONVERT(date, k.DATUM)" in q


def test_read_source_entries_with_min_kartei_id_filters(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {"query": "", "params": ()}

    class FakeCursor:
        def execute(self, query: str, *params: object) -> None:
            captured["query"] = query
            captured["params"] = params

        def fetchall(self):
            return []

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    monkeypatch.setitem(
        sys.modules,
        "pyodbc",
        SimpleNamespace(connect=lambda _cs: FakeConnection()),
    )

    extractor_mod.read_source_entries(_build_settings(tmp_path), min_kartei_id=100)

    assert "AND ID > ?" in str(captured["query"])
    assert captured["params"] == (100,)


def test_read_source_entries_min_kartei_id_none_no_filter(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {"query": "", "params": ()}

    class FakeCursor:
        def execute(self, query: str, *params: object) -> None:
            captured["query"] = query
            captured["params"] = params

        def fetchall(self):
            return []

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    monkeypatch.setitem(
        sys.modules,
        "pyodbc",
        SimpleNamespace(connect=lambda _cs: FakeConnection()),
    )

    extractor_mod.read_source_entries(_build_settings(tmp_path), min_kartei_id=None)

    assert "AND ID > ?" not in str(captured["query"])
    assert captured["params"] == ()


def test_read_previous_max_kartei_id_nonexistent_csv(tmp_path: Path) -> None:
    assert extractor_mod._read_previous_max_kartei_id(tmp_path / "missing.csv") is None


def test_read_previous_max_kartei_id_exists(tmp_path: Path) -> None:
    output_csv = tmp_path / "ivoris_extract.csv"
    output_csv.write_text(
        "entry_date,patient_id,insurance_state,file_entry,service,t_kartei_id\n"
        "2026-03-14,PAT-001,Member,Initial,SVC-A,100\n"
        "2026-03-15,PAT-002,Private,Next,SVC-B,150\n"
        "2026-03-16,PAT-003,Private,Newest,SVC-C,120\n",
        encoding="utf-8",
    )

    assert extractor_mod._read_previous_max_kartei_id(output_csv) == 150


def test_read_previous_max_kartei_id_empty_csv(tmp_path: Path) -> None:
    output_csv = tmp_path / "ivoris_extract.csv"
    output_csv.write_text(
        "entry_date,patient_id,insurance_state,file_entry,service,t_kartei_id\n",
        encoding="utf-8",
    )

    assert extractor_mod._read_previous_max_kartei_id(output_csv) is None


def test_write_full_output_includes_t_kartei_id_column(tmp_path: Path) -> None:
    output_csv = tmp_path / "ivoris_extract.csv"
    entries = [
        FileEntry(
            kartei_id=100,
            entry_date=date(2026, 3, 14),
            patient_id="PAT-001",
            insurance_state="Member",
            file_entry="Routine checkup",
            service="CHK001",
        )
    ]

    extractor_mod._write_full_output(output_csv, entries, existing_kartei_ids=set())

    lines = _read_output_lines(output_csv)
    assert lines[0] == "entry_date,patient_id,insurance_state,file_entry,service,t_kartei_id"
    assert lines[1].endswith(",100")


def test_write_output_writes_header_on_first_run(tmp_path: Path) -> None:
    output_csv = tmp_path / "ivoris_extract.csv"
    entries = [
        FileEntry(
            kartei_id=100,
            entry_date=date(2026, 3, 14),
            patient_id="PAT-001",
            insurance_state="Member",
            file_entry="Routine checkup",
            service="CHK001",
        ),
        FileEntry(
            kartei_id=101,
            entry_date=date(2026, 3, 15),
            patient_id="PAT-002",
            insurance_state="Private",
            file_entry="Follow-up",
            service="FUP050",
        ),
    ]

    extractor_mod._write_full_output(output_csv, entries, existing_kartei_ids=set())

    assert _read_output_lines(output_csv) == [
        "entry_date,patient_id,insurance_state,file_entry,service,t_kartei_id",
        "2026-03-14,PAT-001,Member,Routine checkup,CHK001,100",
        "2026-03-15,PAT-002,Private,Follow-up,FUP050,101",
    ]


def test_write_output_appends_rows_to_existing_csv(tmp_path: Path) -> None:
    output_csv = tmp_path / "ivoris_extract.csv"
    output_csv.write_text(
        "entry_date,patient_id,insurance_state,file_entry,service,t_kartei_id\n"
        "2026-03-14,PAT-001,Member,Initial,SVC-A,100\n",
        encoding="utf-8",
    )

    new_entries = [
        FileEntry(
            kartei_id=101,
            entry_date=date(2026, 3, 15),
            patient_id="PAT-002",
            insurance_state="Private",
            file_entry="Follow-up",
            service="SVC-B",
        ),
        FileEntry(
            kartei_id=102,
            entry_date=date(2026, 3, 16),
            patient_id="PAT-003",
            insurance_state="Member",
            file_entry="Check",
            service="SVC-C",
        ),
    ]

    extractor_mod._write_full_output(output_csv, new_entries, existing_kartei_ids={100})

    rows = _read_output_rows(output_csv)
    assert len(rows) == 3
    assert [row["t_kartei_id"] for row in rows] == ["100", "101", "102"]


def test_write_output_no_duplicate_header_on_append(tmp_path: Path) -> None:
    output_csv = tmp_path / "ivoris_extract.csv"
    output_csv.write_text(
        "entry_date,patient_id,insurance_state,file_entry,service,t_kartei_id\n"
        "2026-03-14,PAT-001,Member,Initial,SVC-A,100\n",
        encoding="utf-8",
    )

    extractor_mod._write_full_output(
        output_csv,
        [
            FileEntry(
                kartei_id=101,
                entry_date=date(2026, 3, 15),
                patient_id="PAT-002",
                insurance_state="Private",
                file_entry="Follow-up",
                service="SVC-B",
            )
        ],
        existing_kartei_ids={100},
    )

    content = output_csv.read_text(encoding="utf-8")
    assert content.count("entry_date") == 1


def test_read_existing_kartei_ids_nonexistent(tmp_path: Path) -> None:
    assert extractor_mod._read_existing_kartei_ids(tmp_path / "missing.csv") == set()


def test_read_existing_kartei_ids_extracts_all_ids(tmp_path: Path) -> None:
    output_csv = tmp_path / "ivoris_extract.csv"
    output_csv.write_text(
        "entry_date,patient_id,insurance_state,file_entry,service,t_kartei_id\n"
        "2026-03-14,PAT-001,Member,Initial,SVC-A,100\n"
        "2026-03-15,PAT-002,Private,Next,SVC-B,150\n"
        "2026-03-16,PAT-003,Private,Newest,SVC-C,120\n",
        encoding="utf-8",
    )

    assert extractor_mod._read_existing_kartei_ids(output_csv) == {100, 120, 150}


def test_write_output_skips_entries_with_existing_kartei_id(tmp_path: Path) -> None:
    output_csv = tmp_path / "ivoris_extract.csv"
    output_csv.write_text(
        "entry_date,patient_id,insurance_state,file_entry,service,t_kartei_id\n"
        "2026-03-14,PAT-001,Member,Initial,SVC-A,100\n",
        encoding="utf-8",
    )

    extractor_mod._write_full_output(
        output_csv,
        [
            FileEntry(
                kartei_id=100,
                entry_date=date(2026, 3, 15),
                patient_id="PAT-002",
                insurance_state="Private",
                file_entry="Duplicate",
                service="SVC-B",
            ),
            FileEntry(
                kartei_id=101,
                entry_date=date(2026, 3, 16),
                patient_id="PAT-003",
                insurance_state="Member",
                file_entry="New",
                service="SVC-C",
            ),
        ],
        existing_kartei_ids={100},
    )

    rows = _read_output_rows(output_csv)
    assert [row["t_kartei_id"] for row in rows] == ["100", "101"]


def test_run_cycle_bootstraps_checkpoint_on_first_run(tmp_path: Path, monkeypatch) -> None:
    output_csv = tmp_path / "ivoris_extract.csv"
    settings = Settings(**{**_build_settings(tmp_path).__dict__, "output_csv": output_csv})

    seen: dict[str, object] = {}
    bootstrap_entries = [
        FileEntry(
            kartei_id=100,
            entry_date=date(2026, 3, 14),
            patient_id="PAT-001",
            insurance_state="Member",
            file_entry="Initial",
            service="SVC-A",
        ),
        FileEntry(
            kartei_id=101,
            entry_date=date(2026, 3, 15),
            patient_id="PAT-002",
            insurance_state="Private",
            file_entry="Second",
            service="SVC-B",
        ),
    ]

    def fake_read_source_entries(
        _settings: Settings, min_kartei_id: int | None = None
    ) -> list[FileEntry]:
        seen["min_kartei_id"] = min_kartei_id
        return bootstrap_entries

    monkeypatch.setattr(extractor_mod, "read_source_entries", fake_read_source_entries)

    extracted_count = extractor_mod.run_cycle(settings)

    assert extracted_count == 2
    assert seen["min_kartei_id"] is None
    assert _read_output_lines(output_csv) == [
        "entry_date,patient_id,insurance_state,file_entry,service,t_kartei_id",
        "2026-03-14,PAT-001,Member,Initial,SVC-A,100",
        "2026-03-15,PAT-002,Private,Second,SVC-B,101",
    ]


def test_run_cycle_passes_existing_ids_to_writer(tmp_path: Path, monkeypatch) -> None:
    output_csv = tmp_path / "ivoris_extract.csv"
    output_csv.write_text(
        "entry_date,patient_id,insurance_state,file_entry,service,t_kartei_id\n"
        "2026-03-14,PAT-001,Member,Initial,SVC-A,42\n",
        encoding="utf-8",
    )
    settings = Settings(**{**_build_settings(tmp_path).__dict__, "output_csv": output_csv})

    new_entries = [
        FileEntry(
            kartei_id=50,
            entry_date=date(2026, 3, 14),
            patient_id="PAT-001",
            insurance_state="Member",
            file_entry="New",
            service="SVC-B",
        )
    ]

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        extractor_mod,
        "read_source_entries",
        lambda _settings, min_kartei_id=None: new_entries,
    )

    def fake_write_full_output(
        _output_csv: Path, entries: list[FileEntry], existing_kartei_ids: set[int]
    ) -> None:
        captured["entries"] = entries
        captured["existing_kartei_ids"] = existing_kartei_ids

    monkeypatch.setattr(extractor_mod, "_write_full_output", fake_write_full_output)

    extractor_mod.run_cycle(settings)

    assert captured["entries"] == new_entries
    assert captured["existing_kartei_ids"] == {42}


def test_run_scheduler_stops_after_one_cycle(monkeypatch, tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)

    calls = {"count": 0}

    def fake_run_cycle(_settings: Settings) -> int:
        calls["count"] += 1
        return 0

    monkeypatch.setattr(extractor_mod, "run_cycle", fake_run_cycle)

    extractor_mod.run_scheduler(settings)

    assert calls["count"] == 1
