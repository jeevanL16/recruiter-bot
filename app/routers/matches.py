"""Matches endpoints for ranked match retrieval and recomputation."""

from fastapi import APIRouter, Depends, Query
from mysql.connector.pooling import PooledMySQLConnection

from app.db import get_conn
from app.schemas import (
    CandidateMatchesResponse,
    JobMatchesResponse,
    RecomputeResponse,
)
from app.services import matching

router = APIRouter(tags=["Matches"])


@router.post("/matches/recompute", response_model=RecomputeResponse)
def recompute_all_matches(
    conn: PooledMySQLConnection = Depends(get_conn),
) -> RecomputeResponse:
    """Trigger a full recompute of match scores across all candidates and jobs."""
    count = matching.recompute_all(conn)
    return RecomputeResponse(
        recomputed=count,
        message=f"Successfully recomputed {count} matches.",
    )


@router.get("/jobs/{id}/matches", response_model=JobMatchesResponse)
def get_matches_for_job(
    id: int,
    limit: int = Query(default=10, ge=1, le=100, description="Page limit (1-100)"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    min_score: float = Query(default=0.0, ge=0.0, le=100.0, description="Minimum score threshold"),
    availability: str | None = Query(
        default=None,
        pattern="^(immediate|two_weeks|not_looking)$",
        description="Filter by candidate availability",
    ),
    conn: PooledMySQLConnection = Depends(get_conn),
) -> JobMatchesResponse:
    """Retrieve ranked candidate matches for a job."""
    result = matching.get_job_matches(
        conn=conn,
        job_id=id,
        min_score=min_score,
        availability=availability,
        limit=limit,
        offset=offset,
    )
    return JobMatchesResponse(**result)


@router.get("/candidates/{id}/matches", response_model=CandidateMatchesResponse)
def get_matches_for_candidate(
    id: int,
    limit: int = Query(default=10, ge=1, le=100, description="Page limit (1-100)"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    min_score: float = Query(default=0.0, ge=0.0, le=100.0, description="Minimum score threshold"),
    conn: PooledMySQLConnection = Depends(get_conn),
) -> CandidateMatchesResponse:
    """Retrieve ranked job matches for a candidate."""
    result = matching.get_candidate_matches(
        conn=conn,
        candidate_id=id,
        min_score=min_score,
        limit=limit,
        offset=offset,
    )
    return CandidateMatchesResponse(**result)
