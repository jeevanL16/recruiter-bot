"""Job repository containing all job-related hand-written SQL."""

from collections import defaultdict
from typing import Any

from mysql.connector.connection import MySQLConnection
from mysql.connector.pooling import PooledMySQLConnection

from app.models import JobProfile

# ==========================================
# SQL Statements (Module-level constants)
# ==========================================

SQL_JOB_EXISTS = """
SELECT 1 FROM jobs WHERE id = %s LIMIT 1;
"""

SQL_SELECT_JOB_BY_ID = """
SELECT id, title, min_experience_years, tagline, created_at, updated_at
FROM jobs
WHERE id = %s;
"""

SQL_SELECT_JOBS_PAGINATED = """
SELECT id, title, min_experience_years, tagline, created_at, updated_at
FROM jobs
ORDER BY id ASC
LIMIT %s OFFSET %s;
"""

SQL_SELECT_ALL_JOBS = """
SELECT id, title, min_experience_years, tagline
FROM jobs;
"""

SQL_SELECT_JOB_PROFILE_BY_ID = """
SELECT id, title, min_experience_years, tagline
FROM jobs
WHERE id = %s;
"""

SQL_SELECT_JOB_SKILLS_FOR_PROFILE = """
SELECT jrs.job_id, s.name AS skill_name
FROM job_required_skills jrs
JOIN skills s ON s.id = jrs.skill_id;
"""

SQL_SELECT_JOB_SKILLS_BY_JOB_ID = """
SELECT jrs.job_id, s.name AS skill_name
FROM job_required_skills jrs
JOIN skills s ON s.id = jrs.skill_id
WHERE jrs.job_id = %s;
"""

SQL_SELECT_JOB_CULTURE_FOR_PROFILE = """
SELECT jck.job_id, t.name AS trait_name
FROM job_culture_keywords jck
JOIN traits t ON t.id = jck.trait_id;
"""

SQL_SELECT_JOB_CULTURE_BY_JOB_ID = """
SELECT jck.job_id, t.name AS trait_name
FROM job_culture_keywords jck
JOIN traits t ON t.id = jck.trait_id
WHERE jck.job_id = %s;
"""

SQL_UPSERT_JOB = """
INSERT INTO jobs (title, min_experience_years, tagline)
VALUES (%s, %s, %s)
ON DUPLICATE KEY UPDATE
    min_experience_years = VALUES(min_experience_years),
    tagline              = VALUES(tagline);
"""

SQL_GET_JOB_ID_BY_TITLE = """
SELECT id FROM jobs WHERE title = %s;
"""

SQL_INSERT_JOB_REQUIRED_SKILL = """
INSERT IGNORE INTO job_required_skills (job_id, skill_id)
VALUES (%s, %s);
"""

SQL_INSERT_JOB_CULTURE_KEYWORD = """
INSERT IGNORE INTO job_culture_keywords (job_id, trait_id)
VALUES (%s, %s);
"""

SQL_DELETE_JOB_SKILLS_EXCEPT = """
DELETE FROM job_required_skills
WHERE job_id = %s AND skill_id NOT IN ({placeholders});
"""

SQL_DELETE_ALL_JOB_SKILLS = """
DELETE FROM job_required_skills
WHERE job_id = %s;
"""

SQL_DELETE_JOB_CULTURE_EXCEPT = """
DELETE FROM job_culture_keywords
WHERE job_id = %s AND trait_id NOT IN ({placeholders});
"""

SQL_DELETE_ALL_JOB_CULTURE = """
DELETE FROM job_culture_keywords
WHERE job_id = %s;
"""


# ==========================================
# Repository Functions
# ==========================================


def job_exists(conn: MySQLConnection | PooledMySQLConnection, job_id: int) -> bool:
    """Check if a job exists by id."""
    cursor: Any = conn.cursor(dictionary=True)
    cursor.execute(SQL_JOB_EXISTS, (job_id,))
    row = cursor.fetchone()
    cursor.close()
    return row is not None


def upsert_job(
    conn: MySQLConnection | PooledMySQLConnection,
    title: str,
    min_experience_years: float,
    tagline: str | None,
) -> int:
    """Insert or update a job record and return job id."""
    cursor: Any = conn.cursor(dictionary=True)
    cursor.execute(SQL_UPSERT_JOB, (title, min_experience_years, tagline))
    cursor.execute(SQL_GET_JOB_ID_BY_TITLE, (title,))
    row = cursor.fetchone()
    cursor.close()
    if not row:
        raise RuntimeError(f"Could not retrieve id for job {title}")
    return int(row["id"])


def set_job_required_skills(
    conn: MySQLConnection | PooledMySQLConnection,
    job_id: int,
    skill_ids: list[int],
) -> None:
    """Synchronize required skills for a job."""
    cursor: Any = conn.cursor()
    if not skill_ids:
        cursor.execute(SQL_DELETE_ALL_JOB_SKILLS, (job_id,))
    else:
        placeholders = ", ".join(["%s"] * len(skill_ids))
        delete_query = SQL_DELETE_JOB_SKILLS_EXCEPT.format(placeholders=placeholders)
        cursor.execute(delete_query, (job_id, *skill_ids))

        insert_params = [(job_id, s_id) for s_id in skill_ids]
        cursor.executemany(SQL_INSERT_JOB_REQUIRED_SKILL, insert_params)
    cursor.close()


def set_job_culture_keywords(
    conn: MySQLConnection | PooledMySQLConnection,
    job_id: int,
    trait_ids: list[int],
) -> None:
    """Synchronize culture keywords for a job."""
    cursor: Any = conn.cursor()
    if not trait_ids:
        cursor.execute(SQL_DELETE_ALL_JOB_CULTURE, (job_id,))
    else:
        placeholders = ", ".join(["%s"] * len(trait_ids))
        delete_query = SQL_DELETE_JOB_CULTURE_EXCEPT.format(placeholders=placeholders)
        cursor.execute(delete_query, (job_id, *trait_ids))

        insert_params = [(job_id, t_id) for t_id in trait_ids]
        cursor.executemany(SQL_INSERT_JOB_CULTURE_KEYWORD, insert_params)
    cursor.close()


def get_job_by_id(
    conn: MySQLConnection | PooledMySQLConnection, job_id: int
) -> dict[str, Any] | None:
    """Retrieve job with required skills and culture keywords by ID."""
    cursor: Any = conn.cursor(dictionary=True)
    cursor.execute(SQL_SELECT_JOB_BY_ID, (job_id,))
    job = cursor.fetchone()
    if not job:
        cursor.close()
        return None

    cursor.execute(SQL_SELECT_JOB_SKILLS_BY_JOB_ID, (job_id,))
    skill_rows = cursor.fetchall()

    cursor.execute(SQL_SELECT_JOB_CULTURE_BY_JOB_ID, (job_id,))
    culture_rows = cursor.fetchall()
    cursor.close()

    job["required_skills"] = [row["skill_name"] for row in skill_rows]
    job["culture_keywords"] = [row["trait_name"] for row in culture_rows]
    result: dict[str, Any] = dict(job)
    return result


def list_jobs(
    conn: MySQLConnection | PooledMySQLConnection, limit: int = 50, offset: int = 0
) -> list[dict[str, Any]]:
    """Retrieve a paginated list of jobs with required skills and culture keywords."""
    cursor: Any = conn.cursor(dictionary=True)
    cursor.execute(SQL_SELECT_JOBS_PAGINATED, (limit, offset))
    jobs = cursor.fetchall()
    if not jobs:
        cursor.close()
        return []

    job_ids = [j["id"] for j in jobs]
    placeholders = ", ".join(["%s"] * len(job_ids))

    query_skills = f"""
    SELECT jrs.job_id, s.name AS skill_name
    FROM job_required_skills jrs
    JOIN skills s ON s.id = jrs.skill_id
    WHERE jrs.job_id IN ({placeholders});
    """
    cursor.execute(query_skills, tuple(job_ids))
    skill_rows = cursor.fetchall()

    query_culture = f"""
    SELECT jck.job_id, t.name AS trait_name
    FROM job_culture_keywords jck
    JOIN traits t ON t.id = jck.trait_id
    WHERE jck.job_id IN ({placeholders});
    """
    cursor.execute(query_culture, tuple(job_ids))
    culture_rows = cursor.fetchall()
    cursor.close()

    skills_map: dict[int, list[str]] = defaultdict(list)
    for r in skill_rows:
        skills_map[r["job_id"]].append(r["skill_name"])

    culture_map: dict[int, list[str]] = defaultdict(list)
    for r in culture_rows:
        culture_map[r["job_id"]].append(r["trait_name"])

    result_list: list[dict[str, Any]] = []
    for j in jobs:
        j["required_skills"] = skills_map[j["id"]]
        j["culture_keywords"] = culture_map[j["id"]]
        result_list.append(dict(j))

    return result_list


def get_job_profiles(
    conn: MySQLConnection | PooledMySQLConnection,
    job_id: int | None = None,
) -> list[JobProfile]:
    """Fetch job profiles in 3 queries total (avoids N+1 query problem)."""
    cursor: Any = conn.cursor(dictionary=True)

    if job_id is not None:
        cursor.execute(SQL_SELECT_JOB_PROFILE_BY_ID, (job_id,))
        job_rows = cursor.fetchall()
        cursor.execute(SQL_SELECT_JOB_SKILLS_BY_JOB_ID, (job_id,))
        skill_rows = cursor.fetchall()
        cursor.execute(SQL_SELECT_JOB_CULTURE_BY_JOB_ID, (job_id,))
        culture_rows = cursor.fetchall()
    else:
        cursor.execute(SQL_SELECT_ALL_JOBS)
        job_rows = cursor.fetchall()
        cursor.execute(SQL_SELECT_JOB_SKILLS_FOR_PROFILE)
        skill_rows = cursor.fetchall()
        cursor.execute(SQL_SELECT_JOB_CULTURE_FOR_PROFILE)
        culture_rows = cursor.fetchall()

    cursor.close()

    skills_by_job: dict[int, set[str]] = defaultdict(set)
    for row in skill_rows:
        skills_by_job[row["job_id"]].add(row["skill_name"])

    culture_by_job: dict[int, set[str]] = defaultdict(set)
    for row in culture_rows:
        culture_by_job[row["job_id"]].add(row["trait_name"])

    profiles: list[JobProfile] = []
    for row in job_rows:
        jid = int(row["id"])
        profiles.append(
            JobProfile(
                id=jid,
                title=row["title"],
                min_experience_years=float(row["min_experience_years"]),
                required_skills=frozenset(skills_by_job[jid]),
                culture_keywords=frozenset(culture_by_job[jid]),
                tagline=row.get("tagline"),
            )
        )

    return profiles
