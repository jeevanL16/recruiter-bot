"""Jobs endpoints for CRUD operations."""

from fastapi import APIRouter, Depends, Query, status
from mysql.connector.pooling import PooledMySQLConnection

from app.db import get_conn, transaction
from app.errors import NotFoundError
from app.repositories import candidates as cand_repo
from app.repositories import jobs as job_repo
from app.schemas import JobCreate, JobResponse
from app.services import matching
from app.services.ingestion import normalize_string_list

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("", response_model=list[JobResponse])
def list_jobs(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    conn: PooledMySQLConnection = Depends(get_conn),
) -> list[JobResponse]:
    """List jobs paginated."""
    rows = job_repo.list_jobs(conn, limit=limit, offset=offset)
    return [JobResponse(**r) for r in rows]


@router.get("/{id}", response_model=JobResponse)
def get_job(
    id: int,
    conn: PooledMySQLConnection = Depends(get_conn),
) -> JobResponse:
    """Get single job by ID."""
    job = job_repo.get_job_by_id(conn, id)
    if not job:
        raise NotFoundError(f"Job {id} not found")
    return JobResponse(**job)


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobCreate,
    conn: PooledMySQLConnection = Depends(get_conn),
) -> JobResponse:
    """Create a new job, normalize skills/culture keywords, and auto-score matches."""
    norm_skills = normalize_string_list(payload.required_skills)
    norm_culture = normalize_string_list(payload.culture_keywords)

    with transaction(conn):
        skill_map = cand_repo.ensure_skills(conn, norm_skills)
        trait_map = cand_repo.ensure_traits(conn, norm_culture)

        job_id = job_repo.upsert_job(
            conn=conn,
            title=payload.title,
            min_experience_years=payload.min_experience_years,
            tagline=payload.tagline,
        )

        skill_ids = [skill_map[s] for s in norm_skills if s in skill_map]
        trait_ids = [trait_map[t] for t in norm_culture if t in trait_map]

        job_repo.set_job_required_skills(conn, job_id, skill_ids)
        job_repo.set_job_culture_keywords(conn, job_id, trait_ids)

    # Recompute matches for this job
    matching.recompute_for_job(conn, job_id)

    job = job_repo.get_job_by_id(conn, job_id)
    if not job:
        raise NotFoundError(f"Job {job_id} not found after creation")
    return JobResponse(**job)
