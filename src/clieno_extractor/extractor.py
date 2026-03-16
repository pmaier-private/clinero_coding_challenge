import csv
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .config import Settings


@dataclass(frozen=True)
class FileEntry:
    entry_date: date
    patient_id: str
    insurance_state: str
    file_entry: str
    services: str


def read_source_entries() -> list[FileEntry]:
    # ML0 placeholder for direct DB integration: return no entries until DB access is implemented.
    _ = path
    return []


def _write_full_output(output_csv: Path, entries: list[FileEntry]) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["entry_date", "patient_id", "insurance_state", "file_entry", "services"],
        )
        writer.writeheader()

        for entry in entries:
            writer.writerow(
                {
                    "entry_date": entry.entry_date.isoformat(),
                    "patient_id": entry.patient_id,
                    "insurance_state": entry.insurance_state,
                    "file_entry": entry.file_entry,
                    "services": entry.services,
                }
            )


def run_cycle(settings: Settings) -> int:
    source_entries = read_source_entries(settings.source_csv)
    _write_full_output(settings.output_csv, source_entries)
    return len(source_entries)


def run_scheduler(settings: Settings) -> None:
    while True:
        extracted_count = run_cycle(settings)
        print(f"Cycle finished. Extracted rows: {extracted_count}")

        if settings.run_once:
            return

        # Interval defaults to daily; override via environment variable.
        time.sleep(settings.interval_seconds)
