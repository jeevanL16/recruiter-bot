"""Tests for ingestion service and transaction guarantees."""

import contextlib
from collections.abc import Generator

import pytest
from mysql.connector.pooling import PooledMySQLConnection

from app.db import get_conn
from app.repositories import candidates as cand_repo
from app.services.ingestion import ingest_data, load_seed_file


@pytest.fixture
def db_conn() -> Generator[PooledMySQLConnection, None, None]:
    conn_gen = get_conn()
    conn = next(conn_gen)
    try:
        yield conn
    finally:
        with contextlib.suppress(StopIteration):
            next(conn_gen)



def test_seed_json_structure() -> None:
    """Validate structure of data/seed.json."""
    data = load_seed_file()
    assert "candidates" in data
    assert "jobs" in data
    assert len(data["candidates"]) == 15
    assert len(data["jobs"]) == 6

    for cand in data["candidates"]:
        assert "full_name" in cand
        assert "experience_years" in cand
        assert "availability" in cand
        assert "skills" in cand
        assert len(cand["skills"]) > 0

    for job in data["jobs"]:
        assert "title" in job
        assert "min_experience_years" in job
        assert "required_skills" in job
        assert len(job["required_skills"]) > 0


def test_ingestion_idempotence(db_conn: PooledMySQLConnection) -> None:
    """Ingesting the same data multiple times yields consistent row counts."""
    data = load_seed_file()
    res1 = ingest_data(db_conn, data["candidates"], data["jobs"], recompute=True)
    res2 = ingest_data(db_conn, data["candidates"], data["jobs"], recompute=True)

    assert res1["candidates"] == res2["candidates"] == 15
    assert res1["jobs"] == res2["jobs"] == 6
    assert res1["matches"] == res2["matches"]


def test_ingestion_transaction_rollback(db_conn: PooledMySQLConnection) -> None:
    """If an error occurs during ingestion, all changes in that batch must roll back."""
    initial_candidates = cand_repo.list_candidates(db_conn, limit=100)
    initial_count = len(initial_candidates)

    malformed_candidates = [
        {
            "full_name": "Rollback Test Candidate",
            "experience_years": 5.0,
            "availability": "invalid_availability_enum_value",  # will fail ENUM validation
            "skills": ["python"],
        }
    ]

    with pytest.raises(ValueError):
        ingest_data(db_conn, malformed_candidates, [], recompute=False)

    after_candidates = cand_repo.list_candidates(db_conn, limit=100)
    assert len(after_candidates) == initial_count
    assert not any(c["full_name"] == "Rollback Test Candidate" for c in after_candidates)
