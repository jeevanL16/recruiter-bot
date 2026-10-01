"""Ingestion endpoint router."""

from fastapi import APIRouter, Depends
from mysql.connector.pooling import PooledMySQLConnection

from app.db import get_conn
from app.schemas import IngestPayload, IngestResponse
from app.services.ingestion import ingest_data, load_seed_file

router = APIRouter(tags=["Ingestion"])


@router.post("/ingest", response_model=IngestResponse)
def ingest_candidates_and_jobs(
    payload: IngestPayload | None = None,
    conn: PooledMySQLConnection = Depends(get_conn),
) -> IngestResponse:
    """Ingest candidates and jobs into the system.

    If request body is empty, loads default `data/seed.json`.
    Automatically recomputes matches.
    """
    if payload is not None and (payload.candidates or payload.jobs):
        candidates_data = [c.model_dump() for c in payload.candidates]
        jobs_data = [j.model_dump() for j in payload.jobs]
    else:
        seed = load_seed_file()
        candidates_data = seed.get("candidates", [])
        jobs_data = seed.get("jobs", [])

    counts = ingest_data(conn, candidates_data, jobs_data, recompute=True)
    return IngestResponse(
        candidates=counts["candidates"],
        jobs=counts["jobs"],
        matches=counts["matches"],
    )
