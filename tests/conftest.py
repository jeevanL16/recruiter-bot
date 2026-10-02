"""Pytest fixtures and configuration."""

import json
from pathlib import Path
from typing import Any, cast

import pytest

from app.models import Availability, CandidateProfile, JobProfile

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture
def seed_data() -> dict[str, Any]:
    seed_file = DATA_DIR / "seed.json"
    with open(seed_file, encoding="utf-8") as f:
        return cast(dict[str, Any], json.load(f))



@pytest.fixture
def candidate_sherlock() -> CandidateProfile:
    return CandidateProfile(
        id=1,
        full_name="Sherlock H.",
        experience_years=8.0,
        availability=Availability.IMMEDIATE,
        skills=frozenset({"deduction", "pattern-recognition", "forensics"}),
        traits=frozenset({"analytical", "blunt"}),
    )


@pytest.fixture
def job_backend_detective() -> JobProfile:
    return JobProfile(
        id=1,
        title="Backend Detective",
        min_experience_years=3.0,
        required_skills=frozenset({"deduction", "pattern-recognition", "forensics"}),
        culture_keywords=frozenset({"analytical", "autonomous"}),
    )
