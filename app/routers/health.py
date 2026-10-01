"""Health and readiness probe router."""

from fastapi import APIRouter, Depends
from mysql.connector.pooling import PooledMySQLConnection

from app.db import get_conn, ping_db
from app.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def health_check(conn: PooledMySQLConnection = Depends(get_conn)) -> HealthResponse:
    """Check application and database health."""
    db_alive = ping_db(conn)
    status = "ok" if db_alive else "degraded"
    db_status = "connected" if db_alive else "disconnected"
    return HealthResponse(
        status=status,
        database=db_status,
        version="0.1.0",
    )
