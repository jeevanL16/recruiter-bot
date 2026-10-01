"""CLI command to seed the database with candidates and jobs."""

import logging
import sys

from app.db import get_conn
from app.logging_config import setup_logging
from app.migrate import run_migrations
from app.services.ingestion import run_seed

logger = logging.getLogger("app.seed")


def main() -> None:
    setup_logging(log_level="INFO")
    logger.info("Running migrations and seeding database...")

    for conn in get_conn():
        try:
            # 1. Ensure migrations are up to date
            run_migrations(conn)

            # 2. Ingest seed data and recompute matches
            result = run_seed(conn)
            logger.info("Seed finished successfully: %s", result)
            print(f"Successfully seeded database: {result}")
        except Exception as e:
            logger.exception("Error while seeding database: %s", e)
            sys.exit(1)
        break


if __name__ == "__main__":
    main()
