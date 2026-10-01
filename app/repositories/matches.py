"""Match repository containing all match-related hand-written SQL."""

import json
from typing import Any

from mysql.connector.connection import MySQLConnection
from mysql.connector.pooling import PooledMySQLConnection

# ==========================================
# SQL Statements (Module-level constants)
# ==========================================

SQL_INSERT_OR_UPDATE_MATCH = """
INSERT INTO matches (
    job_id, candidate_id, score, skill_score, experience_score,
    culture_score, availability_score, matched_skills, missing_skills,
    reason, scoring_version
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    score               = VALUES(score),
    skill_score         = VALUES(skill_score),
    experience_score    = VALUES(experience_score),
    culture_score       = VALUES(culture_score),
    availability_score  = VALUES(availability_score),
    matched_skills      = VALUES(matched_skills),
    missing_skills      = VALUES(missing_skills),
    reason              = VALUES(reason),
    scoring_version     = VALUES(scoring_version),
    computed_at         = CURRENT_TIMESTAMP;
"""

SQL_DELETE_ALL_MATCHES = """
DELETE FROM matches;
"""

SQL_DELETE_MATCHES_FOR_JOB = """
DELETE FROM matches WHERE job_id = %s;
"""

SQL_DELETE_MATCHES_FOR_CANDIDATE = """
DELETE FROM matches WHERE candidate_id = %s;
"""

SQL_SELECT_JOB_MATCHES_BASE = """
SELECT c.id AS candidate_id, c.full_name, c.experience_years, c.availability,
       m.score, m.skill_score, m.experience_score, m.culture_score, m.availability_score,
       m.matched_skills, m.missing_skills, m.reason
FROM matches m
JOIN candidates c ON c.id = m.candidate_id
WHERE m.job_id = %s AND m.score >= %s
"""

SQL_ORDER_JOB_MATCHES = """
ORDER BY m.score DESC, m.skill_score DESC, m.availability_score DESC, c.id ASC
LIMIT %s OFFSET %s;
"""

SQL_COUNT_JOB_MATCHES_BASE = """
SELECT COUNT(*) AS total
FROM matches m
JOIN candidates c ON c.id = m.candidate_id
WHERE m.job_id = %s AND m.score >= %s
"""

SQL_SELECT_CANDIDATE_MATCHES = """
SELECT j.id AS job_id, j.title, j.min_experience_years,
       m.score, m.skill_score, m.experience_score, m.culture_score, m.availability_score,
       m.matched_skills, m.missing_skills, m.reason
FROM matches m
JOIN jobs j ON j.id = m.job_id
WHERE m.candidate_id = %s AND m.score >= %s
ORDER BY m.score DESC, m.skill_score DESC, m.availability_score DESC, j.id ASC
LIMIT %s OFFSET %s;
"""

SQL_COUNT_CANDIDATE_MATCHES = """
SELECT COUNT(*) AS total
FROM matches m
WHERE m.candidate_id = %s AND m.score >= %s;
"""


# ==========================================
# Repository Functions
# ==========================================


def delete_all_matches(conn: MySQLConnection | PooledMySQLConnection) -> None:
    """Clear the entire matches table."""
    cursor: Any = conn.cursor()
    cursor.execute(SQL_DELETE_ALL_MATCHES)
    cursor.close()


def delete_matches_for_job(conn: MySQLConnection | PooledMySQLConnection, job_id: int) -> None:
    """Clear all matches associated with a specific job."""
    cursor: Any = conn.cursor()
    cursor.execute(SQL_DELETE_MATCHES_FOR_JOB, (job_id,))
    cursor.close()


def delete_matches_for_candidate(
    conn: MySQLConnection | PooledMySQLConnection, candidate_id: int
) -> None:
    """Clear all matches associated with a specific candidate."""
    cursor: Any = conn.cursor()
    cursor.execute(SQL_DELETE_MATCHES_FOR_CANDIDATE, (candidate_id,))
    cursor.close()


def bulk_upsert_matches(
    conn: MySQLConnection | PooledMySQLConnection,
    matches_data: list[tuple[Any, ...]],
) -> int:
    """Bulk insert or update matches using executemany."""
    if not matches_data:
        return 0

    cursor: Any = conn.cursor()
    cursor.executemany(SQL_INSERT_OR_UPDATE_MATCH, matches_data)
    row_count = cursor.rowcount
    cursor.close()
    return int(row_count)


def _parse_json_field(val: Any) -> list[str]:
    """Ensure JSON column is parsed to a Python list."""
    if isinstance(val, list):
        return [str(x) for x in val]
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return [str(x) for x in parsed] if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def get_job_matches(
    conn: MySQLConnection | PooledMySQLConnection,
    job_id: int,
    min_score: float = 0.0,
    availability: str | None = None,
    limit: int = 10,
    offset: int = 0,
) -> tuple[int, list[dict[str, Any]]]:
    """Retrieve ranked candidate matches for a given job, with total count."""
    cursor: Any = conn.cursor(dictionary=True)

    params: list[Any] = [job_id, min_score]
    where_clause = ""
    if availability:
        where_clause = " AND c.availability = %s"
        params.append(availability)

    # 1. Total count
    count_query = SQL_COUNT_JOB_MATCHES_BASE + where_clause + ";"
    cursor.execute(count_query, tuple(params))
    count_row = cursor.fetchone()
    total = int(count_row["total"]) if count_row else 0

    if total == 0:
        cursor.close()
        return 0, []

    # 2. Paginated rows
    query = SQL_SELECT_JOB_MATCHES_BASE + where_clause + " " + SQL_ORDER_JOB_MATCHES
    query_params = [*params, limit, offset]
    cursor.execute(query, tuple(query_params))
    rows = cursor.fetchall()
    cursor.close()

    results: list[dict[str, Any]] = []
    for idx, r in enumerate(rows, start=offset + 1):
        matched = _parse_json_field(r["matched_skills"])
        missing = _parse_json_field(r["missing_skills"])
        results.append(
            {
                "rank": idx,
                "candidate": {
                    "id": r["candidate_id"],
                    "full_name": r["full_name"],
                    "experience_years": float(r["experience_years"]),
                    "availability": r["availability"],
                },
                "score": float(r["score"]),
                "breakdown": {
                    "skills": float(r["skill_score"]),
                    "experience": float(r["experience_score"]),
                    "culture": float(r["culture_score"]),
                    "availability": float(r["availability_score"]),
                },
                "matched_skills": matched,
                "missing_skills": missing,
                "reason": r["reason"],
            }
        )

    return total, results


def get_candidate_matches(
    conn: MySQLConnection | PooledMySQLConnection,
    candidate_id: int,
    min_score: float = 0.0,
    limit: int = 10,
    offset: int = 0,
) -> tuple[int, list[dict[str, Any]]]:
    """Retrieve ranked job matches for a given candidate, with total count."""
    cursor: Any = conn.cursor(dictionary=True)

    # 1. Total count
    cursor.execute(SQL_COUNT_CANDIDATE_MATCHES, (candidate_id, min_score))
    count_row = cursor.fetchone()
    total = int(count_row["total"]) if count_row else 0

    if total == 0:
        cursor.close()
        return 0, []

    # 2. Paginated rows
    cursor.execute(SQL_SELECT_CANDIDATE_MATCHES, (candidate_id, min_score, limit, offset))
    rows = cursor.fetchall()
    cursor.close()

    results: list[dict[str, Any]] = []
    for idx, r in enumerate(rows, start=offset + 1):
        matched = _parse_json_field(r["matched_skills"])
        missing = _parse_json_field(r["missing_skills"])
        results.append(
            {
                "rank": idx,
                "job": {
                    "id": r["job_id"],
                    "title": r["title"],
                    "min_experience_years": float(r["min_experience_years"]),
                },
                "score": float(r["score"]),
                "breakdown": {
                    "skills": float(r["skill_score"]),
                    "experience": float(r["experience_score"]),
                    "culture": float(r["culture_score"]),
                    "availability": float(r["availability_score"]),
                },
                "matched_skills": matched,
                "missing_skills": missing,
                "reason": r["reason"],
            }
        )

    return total, results
