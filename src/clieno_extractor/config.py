from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    interval_seconds: int
    source_csv: Path
    output_csv: Path
    run_once: bool
    db_server: str
    db_name: str
    db_schema: str
    db_driver: str


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    return Settings(
        interval_seconds=int(os.getenv("IVORIS_INTERVAL_SECONDS", "86400")),
        source_csv=Path(os.getenv("IVORIS_SOURCE_CSV", "data/input/ivoris_file_entries.csv")),
        output_csv=Path(os.getenv("IVORIS_OUTPUT_CSV", "data/output/ivoris_extract.csv")),
        run_once=_parse_bool(os.getenv("IVORIS_RUN_ONCE"), default=False),
        db_server=os.getenv("IVORIS_DB_SERVER", "localhost"),
        db_name=os.getenv("IVORIS_DB_NAME", "DentalDB"),
        db_schema=os.getenv("IVORIS_DB_SCHEMA", "ck"),
        db_driver=os.getenv("IVORIS_DB_DRIVER", "ODBC Driver 18 for SQL Server"),
    )
