"""Lightweight SQL migration runner."""

import logging
from pathlib import Path
from typing import Any

from mysql.connector.connection import MySQLConnection
from mysql.connector.pooling import PooledMySQLConnection

from app.db import get_conn, transaction

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"


def ensure_migration_table(conn: MySQLConnection | PooledMySQLConnection) -> None:
    """Ensure the schema_migrations tracking table exists."""
    cursor: Any = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     VARCHAR(50) PRIMARY KEY,
            applied_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
    )
    cursor.close()
    conn.commit()


def get_applied_migrations(conn: MySQLConnection | PooledMySQLConnection) -> set[str]:
    """Fetch all migration versions that have already been applied."""
    cursor: Any = conn.cursor()
    cursor.execute("SELECT version FROM schema_migrations;")
    rows = cursor.fetchall()
    cursor.close()
    return {row[0] if isinstance(row, tuple) else row["version"] for row in rows}


def split_statements(sql_content: str) -> list[str]:
    """Split raw SQL content into distinct executable statements."""
    statements: list[str] = []
    current_statement: list[str] = []

    for line in sql_content.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("--"):
            continue
        current_statement.append(line)
        if trimmed.endswith(";"):
            stmt = "\n".join(current_statement).strip()
            if stmt:
                statements.append(stmt)
            current_statement = []

    if current_statement:
        stmt = "\n".join(current_statement).strip()
        if stmt:
            statements.append(stmt)

    return statements


def run_migrations(conn: MySQLConnection | PooledMySQLConnection) -> list[str]:
    """Apply any pending migrations in lexicographical order."""
    ensure_migration_table(conn)
    applied = get_applied_migrations(conn)

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    newly_applied: list[str] = []

    for mig_file in migration_files:
        version = mig_file.name
        if version in applied:
            continue

        logger.info("Applying migration %s...", version)
        sql_content = mig_file.read_text(encoding="utf-8")
        statements = split_statements(sql_content)

        with transaction(conn):
            cursor: Any = conn.cursor()
            for stmt in statements:
                cursor.execute(stmt)
            cursor.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s);",
                (version,),
            )
            cursor.close()

        logger.info("Migration %s applied successfully.", version)
        newly_applied.append(version)

    return newly_applied


def main() -> None:
    """CLI runner for migrations."""
    logging.basicConfig(level=logging.INFO)
    for conn in get_conn():
        applied = run_migrations(conn)
        if applied:
            print(f"Applied migrations: {', '.join(applied)}")
        else:
            print("Database is up to date.")
        break


if __name__ == "__main__":
    main()
