"""Ingestion service for candidates, jobs, and seed loading."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from mysql.connector.connection import MySQLConnection
from mysql.connector.pooling import PooledMySQLConnection

from app.db import transaction
from app.models import Availability
from app.repositories import candidates as cand_repo
from app.repositories import jobs as job_repo
from app.services import matching
from app.services.scoring import normalize_token

logger = logging.getLogger(__name__)

DEFAULT_SEED_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "seed.json"


def normalize_string_list(items: list[str]) -> list[str]:
    """Normalize a list of skill/trait strings into trimmed lowercase kebab-case."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        norm = normalize_token(item)
        if norm and norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


def ingest_data(
    conn: MySQLConnection | PooledMySQLConnection,
    candidates_data: list[dict[str, Any]],
    jobs_data: list[dict[str, Any]],
    recompute: bool = True,
) -> dict[str, int]:
    """Ingest candidates and jobs atomically within a single transaction.

    Idempotently inserts or updates candidates, jobs, skills, traits, and link tables.
    If any error occurs, the entire batch is rolled back.
    """
    logger.info(
        "Starting ingestion of %d candidates and %d jobs...",
        len(candidates_data),
        len(jobs_data),
    )

    with transaction(conn):
        # 1. Collect all distinct skills and traits to ensure they exist
        all_skills: set[str] = set()
        all_traits: set[str] = set()

        for c in candidates_data:
            c_skills = normalize_string_list(c.get("skills", []))
            c_traits = normalize_string_list(c.get("traits", []))
            all_skills.update(c_skills)
            all_traits.update(c_traits)

        for j in jobs_data:
            j_skills = normalize_string_list(j.get("required_skills", []))
            j_culture = normalize_string_list(j.get("culture_keywords", []))
            all_skills.update(j_skills)
            all_traits.update(j_culture)

        skill_map = cand_repo.ensure_skills(conn, list(all_skills))
        trait_map = cand_repo.ensure_traits(conn, list(all_traits))

        # 2. Upsert candidates and synchronize skills/traits
        for c in candidates_data:
            full_name = c["full_name"].strip()
            exp_years = float(c["experience_years"])
            availability = Availability.from_str(c["availability"]).value
            quirk = c.get("quirk")

            cand_id = cand_repo.upsert_candidate(
                conn=conn,
                full_name=full_name,
                experience_years=exp_years,
                availability=availability,
                quirk=quirk,
            )

            c_skills = normalize_string_list(c.get("skills", []))
            c_traits = normalize_string_list(c.get("traits", []))

            skill_ids = [skill_map[s] for s in c_skills if s in skill_map]
            trait_ids = [trait_map[t] for t in c_traits if t in trait_map]

            cand_repo.set_candidate_skills(conn, cand_id, skill_ids)
            cand_repo.set_candidate_traits(conn, cand_id, trait_ids)

        # 3. Upsert jobs and synchronize skills/keywords
        for j in jobs_data:
            title = j["title"].strip()
            min_exp = float(j["min_experience_years"])
            tagline = j.get("tagline")

            job_id = job_repo.upsert_job(
                conn=conn,
                title=title,
                min_experience_years=min_exp,
                tagline=tagline,
            )

            j_skills = normalize_string_list(j.get("required_skills", []))
            j_culture = normalize_string_list(j.get("culture_keywords", []))

            skill_ids = [skill_map[s] for s in j_skills if s in skill_map]
            trait_ids = [trait_map[t] for t in j_culture if t in trait_map]

            job_repo.set_job_required_skills(conn, job_id, skill_ids)
            job_repo.set_job_culture_keywords(conn, job_id, trait_ids)

    # 4. Recompute matches after successful transaction commit
    match_count = 0
    if recompute:
        match_count = matching.recompute_all(conn)

    logger.info(
        "Ingestion completed: %d candidates, %d jobs, %d matches created.",
        len(candidates_data),
        len(jobs_data),
        match_count,
    )

    return {
        "candidates": len(candidates_data),
        "jobs": len(jobs_data),
        "matches": match_count,
    }


def load_seed_file(seed_path: Path | None = None) -> dict[str, Any]:
    """Load and parse JSON seed file."""
    path = seed_path or DEFAULT_SEED_FILE
    if not path.is_file():
        raise FileNotFoundError(f"Seed file not found at {path}")

    with open(path, encoding="utf-8") as f:
        return json.load(f)  # type: ignore[no-any-return]


def run_seed(conn: MySQLConnection | PooledMySQLConnection) -> dict[str, int]:
    """Load default seed dataset into the database."""
    data = load_seed_file()
    candidates = data.get("candidates", [])
    jobs = data.get("jobs", [])
    return ingest_data(conn, candidates_data=candidates, jobs_data=jobs, recompute=True)
