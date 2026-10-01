"""MySQL connection pooling and transaction management."""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from mysql.connector import Error as MySQLError
from mysql.connector.connection import MySQLConnection
from mysql.connector.pooling import MySQLConnectionPool, PooledMySQLConnection

from app.config import Settings, get_settings
from app.errors import DatabaseError

logger = logging.getLogger(__name__)

_pool: MySQLConnectionPool | None = None


def init_pool(settings: Settings | None = None) -> MySQLConnectionPool:
    """Initialize the global MySQL connection pool."""
    global _pool
    if _pool is not None:
        return _pool

    cfg = settings or get_settings()
    logger.info(
        "Initializing MySQL connection pool (host=%s, port=%d, db=%s, size=%d)",
        cfg.db_host,
        cfg.db_port,
        cfg.db_name,
        cfg.db_pool_size,
    )
    try:
        _pool = MySQLConnectionPool(
            pool_name="recruiter_bot_pool",
            pool_size=cfg.db_pool_size,
            pool_reset_session=True,
            host=cfg.db_host,
            port=cfg.db_port,
            user=cfg.db_user,
            password=cfg.db_password,
            database=cfg.db_name,
            charset="utf8mb4",
            autocommit=False,
        )
        return _pool
    except MySQLError as err:
        logger.error("Failed to initialize database pool: %s", err)
        raise DatabaseError(f"Database connection error: {err}") from err


def get_pool() -> MySQLConnectionPool:
    """Get the active MySQL connection pool, initializing if needed."""
    global _pool
    if _pool is None:
        return init_pool()
    return _pool


def close_pool() -> None:
    """Clear the connection pool reference on shutdown."""
    global _pool
    _pool = None
    logger.info("MySQL connection pool closed")


def get_conn() -> Generator[PooledMySQLConnection, None, None]:
    """FastAPI dependency: checks out a connection from the pool and closes on exit."""
    pool = get_pool()
    conn: PooledMySQLConnection | None = None
    try:
        raw_conn = pool.get_connection()
        conn = raw_conn
        yield conn
    except MySQLError as err:
        logger.error("Failed to obtain database connection from pool: %s", err)
        raise DatabaseError(f"Database pool exhausted or connection error: {err}") from err
    finally:
        if conn is not None and conn.is_connected():
            try:
                conn.close()  # returns connection to pool
            except Exception as ex:
                logger.warning("Error returning connection to pool: %s", ex)


@contextmanager
def transaction(conn: MySQLConnection | PooledMySQLConnection) -> Generator[None, None, None]:
    """Context manager to run operations within a single database transaction."""
    if not conn.in_transaction:
        conn.start_transaction()
    try:
        yield
        conn.commit()
    except Exception as err:
        logger.exception("Transaction rolled back due to error: %s", err)
        conn.rollback()
        raise


def ping_db(conn: MySQLConnection | PooledMySQLConnection) -> bool:
    """Ping database to check liveness."""
    try:
        cursor: Any = conn.cursor()
        cursor.execute("SELECT 1 AS ping;")
        result = cursor.fetchone()
        cursor.close()
        return bool(result and (result[0] == 1 or result.get("ping") == 1))
    except Exception as ex:
        logger.error("Database ping failed: %s", ex)
        return False
