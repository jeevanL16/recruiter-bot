"""Integration tests for the Recruiter Bot HTTP API."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint(client: TestClient) -> None:
    """GET /health returns 200 and ok status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"


def test_ingest_endpoint(client: TestClient) -> None:
    """POST /ingest loads default seed data idempotently."""
    response = client.post("/ingest")
    assert response.status_code == 200
    data = response.json()
    assert data["candidates"] == 15
    assert data["jobs"] == 6
    assert data["matches"] > 0


def test_job_matches_ranking_and_reason(client: TestClient) -> None:
    """GET /jobs/1/matches returns Sherlock H. at the top with expected score and reason."""
    response = client.get("/jobs/1/matches")
    assert response.status_code == 200
    data = response.json()
    assert data["job"]["id"] == 1
    assert data["job"]["title"] == "Backend Detective"
    assert len(data["matches"]) >= 1

    top_match = data["matches"][0]
    assert top_match["rank"] == 1
    assert top_match["candidate"]["full_name"] == "Sherlock H."
    assert top_match["score"] == 95.0
    assert "deduction" in top_match["matched_skills"]
    assert "Matches" in top_match["reason"]


def test_job_matches_ordering_rapid_prototyping(client: TestClient) -> None:
    """Rapid Prototyping Engineer: Rick S. > MacGyver > Tony S."""
    response = client.get("/jobs/2/matches")
    assert response.status_code == 200
    data = response.json()
    names = [m["candidate"]["full_name"] for m in data["matches"]]

    assert "Rick S." in names
    assert "MacGyver" in names
    assert "Tony S." in names

    rick_idx = names.index("Rick S.")
    mac_idx = names.index("MacGyver")
    tony_idx = names.index("Tony S.")

    assert rick_idx < mac_idx < tony_idx


def test_job_matches_availability_and_min_score_filter(client: TestClient) -> None:
    """Filter by availability and min_score."""
    response = client.get("/jobs/2/matches?availability=immediate")
    assert response.status_code == 200
    data = response.json()
    for m in data["matches"]:
        assert m["candidate"]["availability"] == "immediate"

    response_high = client.get("/jobs/2/matches?min_score=80")
    assert response_high.status_code == 200
    data_high = response_high.json()
    for m in data_high["matches"]:
        assert m["score"] >= 80


def test_total_matches_is_full_count(client: TestClient) -> None:
    """total in response must be the real total count, not capped by limit."""
    response = client.get("/jobs/2/matches?limit=1")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["matches"]) == 1
    # total should reflect all matches, not just this page
    response_all = client.get("/jobs/2/matches?limit=100")
    data_all = response_all.json()
    assert data["total"] == data_all["total"]


def test_candidate_matches_mirror(client: TestClient) -> None:
    """GET /candidates/{id}/matches mirrors the score for the job."""
    response = client.get("/candidates/1/matches")
    assert response.status_code == 200
    data = response.json()
    assert data["candidate"]["full_name"] == "Sherlock H."

    job_ids = [m["job"]["id"] for m in data["matches"]]
    assert 1 in job_ids

    sherlock_match = next(m for m in data["matches"] if m["job"]["id"] == 1)
    assert sherlock_match["score"] == 95.0


def test_not_found_handling(client: TestClient) -> None:
    """404 for unknown job and candidate IDs."""
    res_job = client.get("/jobs/99999/matches")
    assert res_job.status_code == 404
    err_job = res_job.json()
    assert err_job["error"]["code"] == "not_found"

    res_cand = client.get("/candidates/99999/matches")
    assert res_cand.status_code == 404
    err_cand = res_cand.json()
    assert err_cand["error"]["code"] == "not_found"


def test_validation_error_handling(client: TestClient) -> None:
    """422 for invalid query params."""
    response = client.get("/jobs/1/matches?limit=0")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"

    response_avail = client.get("/jobs/1/matches?availability=invalid_value")
    assert response_avail.status_code == 422
    assert response_avail.json()["error"]["code"] == "validation_error"


def test_create_candidate_auto_scores(client: TestClient) -> None:
    """POST /candidates creates a candidate and automatically scores them for jobs."""
    payload = {
        "full_name": "Ada Lovelace",
        "experience_years": 10.0,
        "availability": "immediate",
        "skills": ["systems-design", "rapid-prototyping", "mathematics"],
        "traits": ["analytical", "innovative"],
        "quirk": "Wrote the first algorithm in history.",
    }
    cand_id = None
    try:
        create_res = client.post("/candidates", json=payload)
        assert create_res.status_code == 201
        cand = create_res.json()
        cand_id = cand["id"]

        matches_res = client.get(f"/candidates/{cand_id}/matches")
        assert matches_res.status_code == 200
        m_data = matches_res.json()
        job_titles = [m["job"]["title"] for m in m_data["matches"]]
        assert "Rapid Prototyping Engineer" in job_titles
    finally:
        if cand_id:
            from app.db import get_pool

            pool = get_pool()
            conn = pool.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM candidates WHERE id = %s", (cand_id,))
                conn.commit()
                cursor.close()
            finally:
                conn.close()


def test_create_job_auto_scores(client: TestClient) -> None:
    """POST /jobs creates a job and automatically scores candidates for it."""
    payload = {
        "title": "Senior Forensic Analyst",
        "min_experience_years": 5.0,
        "required_skills": ["forensics", "deduction"],
        "culture_keywords": ["analytical"],
        "tagline": "Follow the evidence wherever it leads.",
    }
    job_id = None
    try:
        create_res = client.post("/jobs", json=payload)
        assert create_res.status_code == 201
        job = create_res.json()
        job_id = job["id"]

        matches_res = client.get(f"/jobs/{job_id}/matches")
        assert matches_res.status_code == 200
        m_data = matches_res.json()
        cand_names = [m["candidate"]["full_name"] for m in m_data["matches"]]
        assert "Sherlock H." in cand_names
    finally:
        if job_id:
            from app.db import get_pool

            pool = get_pool()
            conn = pool.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM jobs WHERE id = %s", (job_id,))
                conn.commit()
                cursor.close()
            finally:
                conn.close()


