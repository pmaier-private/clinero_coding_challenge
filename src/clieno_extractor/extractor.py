import csv
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .config import Settings


@dataclass(frozen=True)
class FileEntry:
    entry_date: date
    patient_id: str
    insurance_state: str
    file_entry: str
    service: str


def _normalize_entry_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def read_source_entries(settings: Settings) -> list[FileEntry]:

    import pyodbc

    connection_string = (
        f"DRIVER={{{settings.db_driver}}};"
        f"SERVER={settings.db_server};"
        f"DATABASE={settings.db_name};"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )
    # Note that the query is specific to MS SQL Server (e.g. "CONVERT(date,
    # l.DATUM)", "nvarchar(max)") and may need adjustments for other databases.
    query = f"""
        WITH services_by_day AS (
            SELECT
                l.PATIENTID,
                CONVERT(date, l.DATUM) AS DATUM,
                STRING_AGG(CAST(l.LEISTUNG AS nvarchar(max)), ' ') AS SERVICES
            FROM {settings.db_schema}.LEISTUNG AS l
            GROUP BY l.PATIENTID, CONVERT(date, l.DATUM)
        ),
        latest_entries AS (
            SELECT
                k.DATUM,
                k.PATNR,
                p.STATUS,
                k.BEMERKUNG,
                COALESCE(s.SERVICES, '') AS SERVICE,
                ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(k.FOLLOWERID, k.ID)
                    ORDER BY k.ID DESC
                ) AS rn
            FROM {settings.db_schema}.KARTEI AS k
            LEFT JOIN {settings.db_schema}.PATKASSE AS p
                ON p.PATNR = k.PATNR
            LEFT JOIN services_by_day AS s
                ON s.PATIENTID = k.PATNR
                AND s.DATUM = CONVERT(date, k.DATUM)
        )
        SELECT DATUM, PATNR, STATUS, BEMERKUNG, SERVICE
        FROM latest_entries
        WHERE rn = 1
        ORDER BY DATUM, PATNR
    """

    entries: list[FileEntry] = []
    with pyodbc.connect(connection_string) as connection:
        cursor = connection.cursor()
        cursor.execute(query)

        for (
            raw_entry_date,
            raw_patient_id,
            raw_insurance_state,
            raw_file_entry,
            raw_service,
        ) in cursor.fetchall():
            entry_date = _normalize_entry_date(raw_entry_date)
            if entry_date is None:
                continue

            entries.append(
                FileEntry(
                    entry_date=entry_date,
                    patient_id=str(raw_patient_id or ""),
                    insurance_state=str(raw_insurance_state or ""),
                    file_entry=str(raw_file_entry or ""),
                    service=str(raw_service or ""),
                )
            )

    return entries


def _write_full_output(output_csv: Path, entries: list[FileEntry]) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "entry_date",
                "patient_id",
                "insurance_state",
                "file_entry",
                "service",
            ],
        )
        writer.writeheader()

        for entry in entries:
            writer.writerow(
                {
                    "entry_date": entry.entry_date.isoformat(),
                    "patient_id": entry.patient_id,
                    "insurance_state": entry.insurance_state,
                    "file_entry": entry.file_entry,
                    "service": entry.service,
                }
            )


def run_cycle(settings: Settings) -> int:
    source_entries = read_source_entries(settings)
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
