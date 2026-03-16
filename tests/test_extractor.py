from datetime import date
from pathlib import Path

from clieno_extractor.config import Settings
from clieno_extractor.extractor import FileEntry, read_source_entries, run_cycle, run_scheduler


def _read_output_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").strip().splitlines()


def test_read_source_entries_returns_empty_list_for_placeholder(tmp_path: Path) -> None:
    entries = read_source_entries()

    assert entries == []


def test_run_cycle_writes_full_snapshot_and_returns_count(
    tmp_path: Path, monkeypatch
) -> None:
    output_csv = tmp_path / "ivoris_extract.csv"
    settings = Settings(
        interval_seconds=86400,
        source_csv=tmp_path / "source.csv",
        output_csv=output_csv,
        run_once=True,
    )

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
    monkeypatch.setattr("clieno_extractor.extractor.read_source_entries", lambda _: entries)

    extracted_count = run_cycle(settings)

    assert extracted_count == 2
    assert _read_output_lines(output_csv) == [
        "entry_date,patient_id,insurance_state,file_entry,services",
        "2026-03-14,PAT-001,Member,Routine checkup,CHK001",
        "2026-03-15,PAT-002,Private,Follow-up,FUP050",
    ]


def test_run_cycle_overwrites_existing_snapshot(tmp_path: Path, monkeypatch) -> None:
    output_csv = tmp_path / "ivoris_extract.csv"
    settings = Settings(
        interval_seconds=86400,
        source_csv=tmp_path / "source.csv",
        output_csv=output_csv,
        run_once=True,
    )

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

    monkeypatch.setattr("clieno_extractor.extractor.read_source_entries", lambda _: first_entries)
    run_cycle(settings)

    monkeypatch.setattr("clieno_extractor.extractor.read_source_entries", lambda _: second_entries)
    run_cycle(settings)

    assert _read_output_lines(output_csv) == [
        "entry_date,patient_id,insurance_state,file_entry,services",
        "2026-03-15,PAT-999,Retired,Replacement,SVC-B",
    ]


def test_run_scheduler_stops_after_one_cycle(monkeypatch, tmp_path: Path) -> None:
    settings = Settings(
        interval_seconds=86400,
        source_csv=tmp_path / "source.csv",
        output_csv=tmp_path / "ivoris_extract.csv",
        run_once=True,
    )

    calls = {"count": 0}

    def fake_run_cycle(_settings: Settings) -> int:
        calls["count"] += 1
        return 0

    monkeypatch.setattr("clieno_extractor.extractor.run_cycle", fake_run_cycle)

    run_scheduler(settings)

    assert calls["count"] == 1
