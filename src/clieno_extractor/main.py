from .config import load_settings
from .extractor import run_scheduler


def main() -> None:
    settings = load_settings()
    run_scheduler(settings)


if __name__ == "__main__":
    main()
