"""Candidate repository containing all candidate-related hand-written SQL."""

from collections import defaultdict
from typing import Any

from mysql.connector.connection import MySQLConnection
from mysql.connector.pooling import PooledMySQLConnection

from app.models import Availability, CandidateProfile

# ==========================================
# SQL Statements (Module-level constants)
# ==========================================

SQL_CANDIDATE_EXISTS = """
SELECT 1 FROM candidates WHERE id = %s LIMIT 1;
"""

SQL_SELECT_CANDIDATE_BY_ID = """
SELECT id, full_name, experience_years, availability, quirk, created_at, updated_at
FROM candidates
WHERE id = %s;
"""

SQL_SELECT_CANDIDATES_PAGINATED = """
SELECT id, full_name, experience_years, availability, quirk, created_at, updated_at
FROM candidates
ORDER BY id ASC
LIMIT %s OFFSET %s;
"""

SQL_SELECT_ALL_CANDIDATES = """
SELECT id, full_name, experience_years, availability, quirk
FROM candidates;
"""

SQL_SELECT_CANDIDATE_PROFILE_BY_ID = """
SELECT id, full_name, experience_years, availability, quirk
FROM candidates
WHERE id = %s;
"""

SQL_SELECT_CANDIDATE_SKILLS_FOR_PROFILE = """
SELECT cs.candidate_id, s.name AS skill_name
FROM candidate_skills cs
JOIN skills s ON s.id = cs.skill_id;
"""

SQL_SELECT_CANDIDATE_SKILLS_BY_CANDIDATE_ID = """
SELECT cs.candidate_id, s.name AS skill_name
FROM candidate_skills cs
JOIN skills s ON s.id = cs.skill_id
WHERE cs.candidate_id = %s;
"""

SQL_SELECT_CANDIDATE_TRAITS_FOR_PROFILE = """
SELECT ct.candidate_id, t.name AS trait_name
FROM candidate_traits ct
JOIN traits t ON t.id = ct.trait_id;
"""

SQL_SELECT_CANDIDATE_TRAITS_BY_CANDIDATE_ID = """
SELECT ct.candidate_id, t.name AS trait_name
FROM candidate_traits ct
JOIN traits t ON t.id = ct.trait_id
WHERE ct.candidate_id = %s;
"""

SQL_UPSERT_CANDIDATE = """
INSERT INTO candidates (full_name, experience_years, availability, quirk)
VALUES (%s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    experience_years = VALUES(experience_years),
    availability     = VALUES(availability),
    quirk            = VALUES(quirk);
"""

SQL_GET_CANDIDATE_ID_BY_NAME = """
SELECT id FROM candidates WHERE full_name = %s;
"""

SQL_SELECT_SKILLS_BY_NAMES_TEMPLATE = """
SELECT id, name FROM skills WHERE name IN ({placeholders});
"""

SQL_SELECT_TRAITS_BY_NAMES_TEMPLATE = """
SELECT id, name FROM traits WHERE name IN ({placeholders});
"""

SQL_INSERT_SKILL_IGNORE = """
INSERT IGNORE INTO skills (name) VALUES (%s);
"""

SQL_INSERT_TRAIT_IGNORE = """
INSERT IGNORE INTO traits (name) VALUES (%s);
"""

SQL_INSERT_CANDIDATE_SKILL = """
INSERT IGNORE INTO candidate_skills (candidate_id, skill_id)
VALUES (%s, %s);
"""

SQL_INSERT_CANDIDATE_TRAIT = """
INSERT IGNORE INTO candidate_traits (candidate_id, trait_id)
VALUES (%s, %s);
"""

SQL_DELETE_CANDIDATE_SKILLS_EXCEPT = """
DELETE FROM candidate_skills
WHERE candidate_id = %s AND skill_id NOT IN ({placeholders});
"""

SQL_DELETE_ALL_CANDIDATE_SKILLS = """
DELETE FROM candidate_skills
WHERE candidate_id = %s;
"""

SQL_DELETE_CANDIDATE_TRAITS_EXCEPT = """
DELETE FROM candidate_traits
WHERE candidate_id = %s AND trait_id NOT IN ({placeholders});
"""

SQL_DELETE_ALL_CANDIDATE_TRAITS = """
DELETE FROM candidate_traits
WHERE candidate_id = %s;
"""


# ==========================================
# Repository Functions
# ==========================================


def candidate_exists(conn: MySQLConnection | PooledMySQLConnection, candidate_id: int) -> bool:
    """Check if a candidate exists by id."""
    cursor: Any = conn.cursor(dictionary=True)
    cursor.execute(SQL_CANDIDATE_EXISTS, (candidate_id,))
    row = cursor.fetchone()
    cursor.close()
    return row is not None


def ensure_skills(
    conn: MySQLConnection | PooledMySQLConnection, skill_names: list[str]
) -> dict[str, int]:
    """Ensure skills exist in skills table and return a mapping of name -> id."""
    if not skill_names:
        return {}

    cursor: Any = conn.cursor(dictionary=True)
    # 1. Batch insert ignore
    params = [(name,) for name in skill_names]
    cursor.executemany(SQL_INSERT_SKILL_IGNORE, params)

    # 2. Select IDs using placeholders
    placeholders = ", ".join(["%s"] * len(skill_names))
    query = SQL_SELECT_SKILLS_BY_NAMES_TEMPLATE.format(placeholders=placeholders)
    cursor.execute(query, tuple(skill_names))
    rows = cursor.fetchall()
    cursor.close()

    return {row["name"]: int(row["id"]) for row in rows}


def ensure_traits(
    conn: MySQLConnection | PooledMySQLConnection, trait_names: list[str]
) -> dict[str, int]:
    """Ensure traits exist in traits table and return a mapping of name -> id."""
    if not trait_names:
        return {}

    cursor: Any = conn.cursor(dictionary=True)
    params = [(name,) for name in trait_names]
    cursor.executemany(SQL_INSERT_TRAIT_IGNORE, params)

    placeholders = ", ".join(["%s"] * len(trait_names))
    query = SQL_SELECT_TRAITS_BY_NAMES_TEMPLATE.format(placeholders=placeholders)
    cursor.execute(query, tuple(trait_names))
    rows = cursor.fetchall()
    cursor.close()

    return {row["name"]: int(row["id"]) for row in rows}


def upsert_candidate(
    conn: MySQLConnection | PooledMySQLConnection,
    full_name: str,
    experience_years: float,
    availability: str,
    quirk: str | None,
) -> int:
    """Insert or update a candidate record and return candidate id."""
    cursor: Any = conn.cursor(dictionary=True)
    cursor.execute(
        SQL_UPSERT_CANDIDATE,
        (full_name, experience_years, availability, quirk),
    )
    cursor.execute(SQL_GET_CANDIDATE_ID_BY_NAME, (full_name,))
    row = cursor.fetchone()
    cursor.close()
    if not row:
        raise RuntimeError(f"Could not retrieve id for candidate {full_name}")
    return int(row["id"])


def set_candidate_skills(
    conn: MySQLConnection | PooledMySQLConnection,
    candidate_id: int,
    skill_ids: list[int],
) -> None:
    """Synchronize the skills set for a candidate."""
    cursor: Any = conn.cursor()
    if not skill_ids:
        cursor.execute(SQL_DELETE_ALL_CANDIDATE_SKILLS, (candidate_id,))
    else:
        placeholders = ", ".join(["%s"] * len(skill_ids))
        delete_query = SQL_DELETE_CANDIDATE_SKILLS_EXCEPT.format(placeholders=placeholders)
        cursor.execute(delete_query, (candidate_id, *skill_ids))

        insert_params = [(candidate_id, s_id) for s_id in skill_ids]
        cursor.executemany(SQL_INSERT_CANDIDATE_SKILL, insert_params)
    cursor.close()


def set_candidate_traits(
    conn: MySQLConnection | PooledMySQLConnection,
    candidate_id: int,
    trait_ids: list[int],
) -> None:
    """Synchronize the traits set for a candidate."""
    cursor: Any = conn.cursor()
    if not trait_ids:
        cursor.execute(SQL_DELETE_ALL_CANDIDATE_TRAITS, (candidate_id,))
    else:
        placeholders = ", ".join(["%s"] * len(trait_ids))
        delete_query = SQL_DELETE_CANDIDATE_TRAITS_EXCEPT.format(placeholders=placeholders)
        cursor.execute(delete_query, (candidate_id, *trait_ids))

        insert_params = [(candidate_id, t_id) for t_id in trait_ids]
        cursor.executemany(SQL_INSERT_CANDIDATE_TRAIT, insert_params)
    cursor.close()


def get_candidate_by_id(
    conn: MySQLConnection | PooledMySQLConnection, candidate_id: int
) -> dict[str, Any] | None:
    """Retrieve candidate with skills and traits by ID."""
    cursor: Any = conn.cursor(dictionary=True)
    cursor.execute(SQL_SELECT_CANDIDATE_BY_ID, (candidate_id,))
    cand = cursor.fetchone()
    if not cand:
        cursor.close()
        return None

    cursor.execute(SQL_SELECT_CANDIDATE_SKILLS_BY_CANDIDATE_ID, (candidate_id,))
    skill_rows = cursor.fetchall()

    cursor.execute(SQL_SELECT_CANDIDATE_TRAITS_BY_CANDIDATE_ID, (candidate_id,))
    trait_rows = cursor.fetchall()
    cursor.close()

    cand["skills"] = [row["skill_name"] for row in skill_rows]
    cand["traits"] = [row["trait_name"] for row in trait_rows]
    result: dict[str, Any] = dict(cand)
    return result


def list_candidates(
    conn: MySQLConnection | PooledMySQLConnection, limit: int = 50, offset: int = 0
) -> list[dict[str, Any]]:
    """Retrieve a paginated list of candidates with skills and traits in 3 round trips."""
    cursor: Any = conn.cursor(dictionary=True)
    cursor.execute(SQL_SELECT_CANDIDATES_PAGINATED, (limit, offset))
    candidates = cursor.fetchall()
    if not candidates:
        cursor.close()
        return []

    candidate_ids = [c["id"] for c in candidates]
    placeholders = ", ".join(["%s"] * len(candidate_ids))

    query_skills = f"""
    SELECT cs.candidate_id, s.name AS skill_name
    FROM candidate_skills cs
    JOIN skills s ON s.id = cs.skill_id
    WHERE cs.candidate_id IN ({placeholders});
    """
    cursor.execute(query_skills, tuple(candidate_ids))
    skill_rows = cursor.fetchall()

    query_traits = f"""
    SELECT ct.candidate_id, t.name AS trait_name
    FROM candidate_traits ct
    JOIN traits t ON t.id = ct.trait_id
    WHERE ct.candidate_id IN ({placeholders});
    """
    cursor.execute(query_traits, tuple(candidate_ids))
    trait_rows = cursor.fetchall()
    cursor.close()

    skills_map: dict[int, list[str]] = defaultdict(list)
    for r in skill_rows:
        skills_map[r["candidate_id"]].append(r["skill_name"])

    traits_map: dict[int, list[str]] = defaultdict(list)
    for r in trait_rows:
        traits_map[r["candidate_id"]].append(r["trait_name"])

    result_list: list[dict[str, Any]] = []
    for c in candidates:
        c["skills"] = skills_map[c["id"]]
        c["traits"] = traits_map[c["id"]]
        result_list.append(dict(c))

    return result_list


def get_candidate_profiles(
    conn: MySQLConnection | PooledMySQLConnection,
    candidate_id: int | None = None,
) -> list[CandidateProfile]:
    """Fetch candidate profiles in 3 queries total (avoids N+1 query problem)."""
    cursor: Any = conn.cursor(dictionary=True)

    if candidate_id is not None:
        cursor.execute(SQL_SELECT_CANDIDATE_PROFILE_BY_ID, (candidate_id,))
        cand_rows = cursor.fetchall()
        cursor.execute(SQL_SELECT_CANDIDATE_SKILLS_BY_CANDIDATE_ID, (candidate_id,))
        skill_rows = cursor.fetchall()
        cursor.execute(SQL_SELECT_CANDIDATE_TRAITS_BY_CANDIDATE_ID, (candidate_id,))
        trait_rows = cursor.fetchall()
    else:
        cursor.execute(SQL_SELECT_ALL_CANDIDATES)
        cand_rows = cursor.fetchall()
        cursor.execute(SQL_SELECT_CANDIDATE_SKILLS_FOR_PROFILE)
        skill_rows = cursor.fetchall()
        cursor.execute(SQL_SELECT_CANDIDATE_TRAITS_FOR_PROFILE)
        trait_rows = cursor.fetchall()

    cursor.close()

    skills_by_candidate: dict[int, set[str]] = defaultdict(set)
    for row in skill_rows:
        skills_by_candidate[row["candidate_id"]].add(row["skill_name"])

    traits_by_candidate: dict[int, set[str]] = defaultdict(set)
    for row in trait_rows:
        traits_by_candidate[row["candidate_id"]].add(row["trait_name"])

    profiles: list[CandidateProfile] = []
    for row in cand_rows:
        cid = int(row["id"])
        profiles.append(
            CandidateProfile(
                id=cid,
                full_name=row["full_name"],
                experience_years=float(row["experience_years"]),
                availability=Availability.from_str(row["availability"]),
                skills=frozenset(skills_by_candidate[cid]),
                traits=frozenset(traits_by_candidate[cid]),
                quirk=row.get("quirk"),
            )
        )

    return profiles
