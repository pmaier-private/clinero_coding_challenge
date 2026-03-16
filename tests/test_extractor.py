import sys
from datetime import datetime
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from clieno_extractor.config import Settings
from clieno_extractor.extractor import FileEntry, read_source_entries, run_cycle, run_scheduler


def _read_output_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").strip().splitlines()


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


def test_read_source_entries_fetches_mapped_rows(monkeypatch, tmp_path: Path) -> None:
    captured = {"connection_string": "", "query": ""}

    rows = [
        (datetime(2026, 3, 14, 8, 30, 0), "PAT-001", "Member", "Routine checkup"),
        (date(2026, 3, 15), "PAT-002", "Private", "Follow-up"),
        ("bad-date", "PAT-003", "Retired", "Ignored because date is invalid"),
    ]

    class FakeCursor:
        def execute(self, query: str) -> None:
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

    entries = read_source_entries(_build_settings(tmp_path))

    assert entries == [
        FileEntry(
            entry_date=date(2026, 3, 14),
            patient_id="PAT-001",
            insurance_state="Member",
            file_entry="Routine checkup",
            services="",
        ),
        FileEntry(
            entry_date=date(2026, 3, 15),
            patient_id="PAT-002",
            insurance_state="Private",
            file_entry="Follow-up",
            services="",
        ),
    ]
    assert "Trusted_Connection=yes;" in captured["connection_string"]
    assert "DATABASE=DentalDB;" in captured["connection_string"]
    assert "FROM ck.KARTEI AS k" in captured["query"]
    assert "LEFT JOIN ck.PATKASSE AS p" in captured["query"]


def test_run_cycle_writes_full_snapshot_and_returns_count(
    tmp_path: Path, monkeypatch
) -> None:
    output_csv = tmp_path / "ivoris_extract.csv"
    settings = _build_settings(tmp_path)
    settings = Settings(**{**settings.__dict__, "output_csv": output_csv})

    entries = [
        FileEntry(
            entry_date=date(2026, 3, 14),
            patient_id="PAT-001",
            insurance_state="Member",
            file_entry="Routine checkup",
            services="CHK001",
        ),
        FileEntry(
            entry_date=date(2026, 3, 15),
            patient_id="PAT-002",
            insurance_state="Private",
            file_entry="Follow-up",
            services="FUP050",
        ),
    ]
    monkeypatch.setattr("clieno_extractor.extractor.read_source_entries", lambda _settings: entries)

    extracted_count = run_cycle(settings)

    assert extracted_count == 2
    assert _read_output_lines(output_csv) == [
        "entry_date,patient_id,insurance_state,file_entry,services",
        "2026-03-14,PAT-001,Member,Routine checkup,CHK001",
        "2026-03-15,PAT-002,Private,Follow-up,FUP050",
    ]


def test_run_cycle_overwrites_existing_snapshot(tmp_path: Path, monkeypatch) -> None:
    output_csv = tmp_path / "ivoris_extract.csv"
    settings = _build_settings(tmp_path)
    settings = Settings(**{**settings.__dict__, "output_csv": output_csv})

    first_entries = [
        FileEntry(
            entry_date=date(2026, 3, 14),
            patient_id="PAT-001",
            insurance_state="Member",
            file_entry="Initial",
            services="SVC-A",
        )
    ]
    second_entries = [
        FileEntry(
            entry_date=date(2026, 3, 15),
            patient_id="PAT-999",
            insurance_state="Retired",
            file_entry="Replacement",
            services="SVC-B",
        )
    ]

    monkeypatch.setattr("clieno_extractor.extractor.read_source_entries", lambda _settings: first_entries)
    run_cycle(settings)

    monkeypatch.setattr("clieno_extractor.extractor.read_source_entries", lambda _settings: second_entries)
    run_cycle(settings)

    assert _read_output_lines(output_csv) == [
        "entry_date,patient_id,insurance_state,file_entry,services",
        "2026-03-15,PAT-999,Retired,Replacement,SVC-B",
    ]


def test_run_scheduler_stops_after_one_cycle(monkeypatch, tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)

    calls = {"count": 0}

    def fake_run_cycle(_settings: Settings) -> int:
        calls["count"] += 1
        return 0

    monkeypatch.setattr("clieno_extractor.extractor.run_cycle", fake_run_cycle)

    run_scheduler(settings)

    assert calls["count"] == 1
