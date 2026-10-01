"""Candidates endpoints for CRUD operations."""

from fastapi import APIRouter, Depends, Query, status
from mysql.connector.pooling import PooledMySQLConnection

from app.db import get_conn, transaction
from app.errors import NotFoundError
from app.models import Availability
from app.repositories import candidates as cand_repo
from app.schemas import CandidateCreate, CandidateResponse
from app.services import matching
from app.services.ingestion import normalize_string_list

router = APIRouter(prefix="/candidates", tags=["Candidates"])


@router.get("", response_model=list[CandidateResponse])
def list_candidates(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    conn: PooledMySQLConnection = Depends(get_conn),
) -> list[CandidateResponse]:
    """List candidates paginated."""
    rows = cand_repo.list_candidates(conn, limit=limit, offset=offset)
    return [CandidateResponse(**r) for r in rows]


@router.get("/{id}", response_model=CandidateResponse)
def get_candidate(
    id: int,
    conn: PooledMySQLConnection = Depends(get_conn),
) -> CandidateResponse:
    """Get single candidate by ID."""
    candidate = cand_repo.get_candidate_by_id(conn, id)
    if not candidate:
        raise NotFoundError(f"Candidate {id} not found")
    return CandidateResponse(**candidate)


@router.post("", response_model=CandidateResponse, status_code=status.HTTP_201_CREATED)
def create_candidate(
    payload: CandidateCreate,
    conn: PooledMySQLConnection = Depends(get_conn),
) -> CandidateResponse:
    """Create a new candidate, normalize skills/traits, and auto-score matches."""
    avail_val = Availability.from_str(payload.availability).value
    norm_skills = normalize_string_list(payload.skills)
    norm_traits = normalize_string_list(payload.traits)

    with transaction(conn):
        skill_map = cand_repo.ensure_skills(conn, norm_skills)
        trait_map = cand_repo.ensure_traits(conn, norm_traits)

        candidate_id = cand_repo.upsert_candidate(
            conn=conn,
            full_name=payload.full_name,
            experience_years=payload.experience_years,
            availability=avail_val,
            quirk=payload.quirk,
        )

        skill_ids = [skill_map[s] for s in norm_skills if s in skill_map]
        trait_ids = [trait_map[t] for t in norm_traits if t in trait_map]

        cand_repo.set_candidate_skills(conn, candidate_id, skill_ids)
        cand_repo.set_candidate_traits(conn, candidate_id, trait_ids)

    # Recompute matches for this candidate
    matching.recompute_for_candidate(conn, candidate_id)

    candidate = cand_repo.get_candidate_by_id(conn, candidate_id)
    if not candidate:
        raise NotFoundError(f"Candidate {candidate_id} not found after creation")
    return CandidateResponse(**candidate)
