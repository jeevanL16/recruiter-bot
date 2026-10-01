"""Matching orchestration service for computing and reading matches."""

from __future__ import annotations

import json
import logging
from typing import Any

from mysql.connector.connection import MySQLConnection
from mysql.connector.pooling import PooledMySQLConnection

from app.config import get_settings
from app.db import transaction
from app.errors import NotFoundError
from app.models import CandidateProfile, JobProfile, Weights
from app.repositories import candidates as cand_repo
from app.repositories import jobs as job_repo
from app.repositories import matches as match_repo
from app.services.scoring import score_pair

logger = logging.getLogger(__name__)


def _prepare_match_tuple(job_id: int, candidate_id: int, score_res: Any) -> tuple[Any, ...]:
    """Convert a ScoreResult into a parameter tuple for SQL insert."""
    return (
        job_id,
        candidate_id,
        score_res.score,
        score_res.breakdown.skills,
        score_res.breakdown.experience,
        score_res.breakdown.culture,
        score_res.breakdown.availability,
        json.dumps(list(score_res.matched_skills)),
        json.dumps(list(score_res.missing_skills)),
        score_res.reason,
        score_res.scoring_version,
    )


def recompute_all(
    conn: MySQLConnection | PooledMySQLConnection,
    weights: Weights | None = None,
) -> int:
    """Recompute all match scores across the full cross product of candidates and jobs."""
    cfg = get_settings()
    scoring_weights = weights or cfg.get_weights()

    logger.info("Starting full match recompute...")
    candidates: list[CandidateProfile] = cand_repo.get_candidate_profiles(conn)
    jobs: list[JobProfile] = job_repo.get_job_profiles(conn)

    matches_to_insert: list[tuple[Any, ...]] = []

    for job in jobs:
        for candidate in candidates:
            res = score_pair(candidate, job, weights=scoring_weights)
            if res is not None:
                matches_to_insert.append(_prepare_match_tuple(job.id, candidate.id, res))

    with transaction(conn):
        match_repo.delete_all_matches(conn)
        match_repo.bulk_upsert_matches(conn, matches_to_insert)

    logger.info(
        "Full recompute completed: %d matches created from %d candidates and %d jobs",
        len(matches_to_insert),
        len(candidates),
        len(jobs),
    )
    return len(matches_to_insert)


def recompute_for_job(
    conn: MySQLConnection | PooledMySQLConnection,
    job_id: int,
    weights: Weights | None = None,
) -> int:
    """Recompute matches for a specific job."""
    cfg = get_settings()
    scoring_weights = weights or cfg.get_weights()

    job_profiles = job_repo.get_job_profiles(conn, job_id=job_id)
    if not job_profiles:
        return 0
    job = job_profiles[0]

    candidates = cand_repo.get_candidate_profiles(conn)
    matches_to_insert: list[tuple[Any, ...]] = []

    for candidate in candidates:
        res = score_pair(candidate, job, weights=scoring_weights)
        if res is not None:
            matches_to_insert.append(_prepare_match_tuple(job.id, candidate.id, res))

    with transaction(conn):
        match_repo.delete_matches_for_job(conn, job_id)
        match_repo.bulk_upsert_matches(conn, matches_to_insert)

    return len(matches_to_insert)


def recompute_for_candidate(
    conn: MySQLConnection | PooledMySQLConnection,
    candidate_id: int,
    weights: Weights | None = None,
) -> int:
    """Recompute matches for a specific candidate."""
    cfg = get_settings()
    scoring_weights = weights or cfg.get_weights()

    cand_profiles = cand_repo.get_candidate_profiles(conn, candidate_id=candidate_id)
    if not cand_profiles:
        return 0
    candidate = cand_profiles[0]

    jobs = job_repo.get_job_profiles(conn)
    matches_to_insert: list[tuple[Any, ...]] = []

    for job in jobs:
        res = score_pair(candidate, job, weights=scoring_weights)
        if res is not None:
            matches_to_insert.append(_prepare_match_tuple(job.id, candidate.id, res))

    with transaction(conn):
        match_repo.delete_matches_for_candidate(conn, candidate_id)
        match_repo.bulk_upsert_matches(conn, matches_to_insert)

    return len(matches_to_insert)


def get_job_matches(
    conn: MySQLConnection | PooledMySQLConnection,
    job_id: int,
    min_score: float = 0.0,
    availability: str | None = None,
    limit: int = 10,
    offset: int = 0,
) -> dict[str, Any]:
    """Retrieve ranked candidate matches for a job, raising 404 if job does not exist."""
    job = job_repo.get_job_by_id(conn, job_id)
    if not job:
        raise NotFoundError(f"Job {job_id} not found")

    total, matches = match_repo.get_job_matches(
        conn=conn,
        job_id=job_id,
        min_score=min_score,
        availability=availability,
        limit=limit,
        offset=offset,
    )

    return {
        "job": {
            "id": job["id"],
            "title": job["title"],
            "min_experience_years": float(job["min_experience_years"]),
        },
        "total": total,
        "limit": limit,
        "offset": offset,
        "matches": matches,
    }


def get_candidate_matches(
    conn: MySQLConnection | PooledMySQLConnection,
    candidate_id: int,
    min_score: float = 0.0,
    limit: int = 10,
    offset: int = 0,
) -> dict[str, Any]:
    """Retrieve ranked job matches for a candidate, raising 404 if candidate does not exist."""
    cand = cand_repo.get_candidate_by_id(conn, candidate_id)
    if not cand:
        raise NotFoundError(f"Candidate {candidate_id} not found")

    total, matches = match_repo.get_candidate_matches(
        conn=conn,
        candidate_id=candidate_id,
        min_score=min_score,
        limit=limit,
        offset=offset,
    )

    return {
        "candidate": {
            "id": cand["id"],
            "full_name": cand["full_name"],
            "experience_years": float(cand["experience_years"]),
            "availability": cand["availability"],
        },
        "total": total,
        "limit": limit,
        "offset": offset,
        "matches": matches,
    }
