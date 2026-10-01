"""Unit tests for the pure scoring algorithm."""

import pytest

from app.models import Availability, CandidateProfile, JobProfile, Weights
from app.services.scoring import (
    compute_availability_score,
    compute_culture_score,
    compute_experience_score,
    compute_skill_score,
    score_pair,
)


def test_weights_sum_validation() -> None:
    """Weights must sum to 1.0."""
    with pytest.raises(ValueError, match="Weights must sum to 1.0"):
        Weights(skills=0.6, experience=0.2, culture=0.2, availability=0.2)


def test_skill_coverage_scoring() -> None:
    """Test full, partial, and zero skill coverage."""
    required = frozenset({"python", "sql", "docker"})

    # Full
    cand_full = frozenset({"python", "sql", "docker", "aws"})
    score, matched, missing = compute_skill_score(cand_full, required)
    assert score == 1.0
    assert matched == ("docker", "python", "sql")
    assert missing == ()

    # Partial
    cand_partial = frozenset({"python", "docker"})
    score, matched, missing = compute_skill_score(cand_partial, required)
    assert round(score, 4) == round(2 / 3, 4)
    assert matched == ("docker", "python")
    assert missing == ("sql",)

    # Zero
    cand_zero = frozenset({"rust", "go"})
    score, matched, missing = compute_skill_score(cand_zero, required)
    assert score == 0.0
    assert matched == ()
    assert missing == ("docker", "python", "sql")


def test_experience_scoring_zones() -> None:
    """Test under-qualified, sweet spot, decay, floor, and min_exp=0."""
    # min_exp = 3.0 -> upper_bound = max(6.0, 8.0) = 8.0
    min_exp = 3.0

    # Under-qualified
    assert compute_experience_score(1.5, min_exp) == 0.5
    assert compute_experience_score(0.0, min_exp) == 0.0

    # Sweet spot: [3.0, 8.0]
    assert compute_experience_score(3.0, min_exp) == 1.0
    assert compute_experience_score(5.0, min_exp) == 1.0
    assert compute_experience_score(8.0, min_exp) == 1.0

    # Over-qualified decay: 10 yrs -> 2 yrs over -> 0.04 decay -> 0.96
    assert compute_experience_score(10.0, min_exp) == 0.96

    # Decay floor at 0.70 (30 yrs over ceiling)
    assert compute_experience_score(50.0, min_exp) == 0.70

    # min_exp = 0
    assert compute_experience_score(0.0, 0.0) == 1.0
    assert compute_experience_score(5.0, 0.0) == 1.0


def test_availability_scoring() -> None:
    """Test availability mapping."""
    assert compute_availability_score(Availability.IMMEDIATE) == 1.0
    assert compute_availability_score(Availability.TWO_WEEKS) == 0.7
    assert compute_availability_score(Availability.NOT_LOOKING) == 0.0


def test_culture_scoring_with_aliases() -> None:
    """Test culture scoring with exact matches and aliases."""
    keywords = frozenset({"analytical", "calm-under-pressure"})

    # Exact match
    traits_exact = frozenset({"analytical", "calm-under-pressure"})
    score, matched = compute_culture_score(traits_exact, keywords)
    assert score == 1.0
    assert matched == ("analytical", "calm-under-pressure")

    # Alias match ('calm' maps to 'calm-under-pressure')
    traits_alias = frozenset({"analytical", "calm"})
    score, matched = compute_culture_score(traits_alias, keywords)
    assert score == 1.0
    assert "calm-under-pressure" in matched

    # Partial match
    traits_partial = frozenset({"analytical", "stubborn"})
    score, matched = compute_culture_score(traits_partial, keywords)
    assert score == 0.5
    assert matched == ("analytical",)


def test_eligibility_gate_zero_skills() -> None:
    """Zero skill overlap returns None."""
    cand = CandidateProfile(
        id=1,
        full_name="No Match",
        experience_years=10.0,
        availability=Availability.IMMEDIATE,
        skills=frozenset({"gardening"}),
        traits=frozenset({"analytical"}),
    )
    job = JobProfile(
        id=1,
        title="Dev",
        min_experience_years=3.0,
        required_skills=frozenset({"python", "sql"}),
        culture_keywords=frozenset({"analytical"}),
    )
    assert score_pair(cand, job) is None


def test_min_score_filter() -> None:
    """Scores below min_score return None."""
    cand = CandidateProfile(
        id=1,
        full_name="Low Score",
        experience_years=1.0,
        availability=Availability.NOT_LOOKING,
        skills=frozenset({"python"}),
        traits=frozenset(),
    )
    job = JobProfile(
        id=1,
        title="Senior Lead",
        min_experience_years=10.0,
        required_skills=frozenset({"python", "systems-design", "k8s", "aws"}),
        culture_keywords=frozenset({"innovative"}),
    )
    # 1/4 skills = 0.25 * 0.55 = 0.1375; exp = 0.1 * 0.2 = 0.02; total ~ 15.75
    assert score_pair(cand, job, min_score=20.0) is None


def test_section_5_5_sanity_rankings() -> None:
    """Verify Section 5.5 sanity rankings from BUILD.md."""
    # 1. Sherlock top for Backend Detective (~95)
    sherlock = CandidateProfile(
        id=1,
        full_name="Sherlock H.",
        experience_years=8.0,
        availability=Availability.IMMEDIATE,
        skills=frozenset({"deduction", "pattern-recognition", "forensics"}),
        traits=frozenset({"analytical", "blunt"}),
    )
    backend_det = JobProfile(
        id=1,
        title="Backend Detective",
        min_experience_years=3.0,
        required_skills=frozenset({"deduction", "pattern-recognition", "forensics"}),
        culture_keywords=frozenset({"analytical", "autonomous"}),
    )
    res_sherlock = score_pair(sherlock, backend_det)
    assert res_sherlock is not None
    assert 94.0 <= res_sherlock.score <= 96.0

    # 2. Rapid Prototyping Engineer: Rick S. > MacGyver > Tony S.
    rapid_job = JobProfile(
        id=2,
        title="Rapid Prototyping Engineer",
        min_experience_years=2.0,
        required_skills=frozenset({"rapid-prototyping", "systems-design"}),
        culture_keywords=frozenset({"innovative", "fast-paced"}),
    )
    rick = CandidateProfile(
        id=6,
        full_name="Rick S.",
        experience_years=20.0,
        availability=Availability.IMMEDIATE,
        skills=frozenset({"systems-design", "rapid-prototyping", "chemistry"}),
        traits=frozenset({"genius", "reckless"}),
    )
    macgyver = CandidateProfile(
        id=8,
        full_name="MacGyver",
        experience_years=10.0,
        availability=Availability.TWO_WEEKS,
        skills=frozenset({"rapid-prototyping", "resourcefulness", "chemistry", "systems-design"}),
        traits=frozenset({"calm", "improviser"}),
    )
    tony = CandidateProfile(
        id=3,
        full_name="Tony S.",
        experience_years=12.0,
        availability=Availability.NOT_LOOKING,
        skills=frozenset({"systems-design", "rapid-prototyping", "leadership"}),
        traits=frozenset({"confident", "innovative"}),
    )

    score_rick = score_pair(rick, rapid_job)
    score_mac = score_pair(macgyver, rapid_job)
    score_tony = score_pair(tony, rapid_job)

    assert score_rick is not None and score_mac is not None and score_tony is not None
    assert score_rick.score > score_mac.score > score_tony.score

    # 3. Incident Commander: Olivia P. (3/3 skills) above Katniss (2/3)
    incident_job = JobProfile(
        id=5,
        title="Incident Commander",
        min_experience_years=4.0,
        required_skills=frozenset({"crisis-management", "strategy", "negotiation"}),
        culture_keywords=frozenset({"decisive", "calm-under-pressure"}),
    )
    olivia = CandidateProfile(
        id=12,
        full_name="Olivia P.",
        experience_years=13.0,
        availability=Availability.TWO_WEEKS,
        skills=frozenset({"crisis-management", "negotiation", "strategy", "leadership"}),
        traits=frozenset({"decisive", "intense"}),
    )
    katniss = CandidateProfile(
        id=10,
        full_name="Katniss E.",
        experience_years=5.0,
        availability=Availability.IMMEDIATE,
        skills=frozenset({"precision", "strategy", "crisis-management"}),
        traits=frozenset({"resilient", "decisive"}),
    )
    score_olivia = score_pair(olivia, incident_job)
    score_katniss = score_pair(katniss, incident_job)
    assert score_olivia is not None and score_katniss is not None
    assert score_olivia.score > score_katniss.score

    # 4. Sales Engineer: Dwight S. (immediate) above Michael S. (not looking)
    sales_job = JobProfile(
        id=6,
        title="Sales Engineer",
        min_experience_years=3.0,
        required_skills=frozenset({"sales", "public-speaking", "negotiation"}),
        culture_keywords=frozenset({"enthusiastic", "persistent"}),
    )
    dwight = CandidateProfile(
        id=15,
        full_name="Dwight S.",
        experience_years=9.0,
        availability=Availability.IMMEDIATE,
        skills=frozenset({"sales", "negotiation", "security", "loyalty"}),
        traits=frozenset({"intense", "loyal"}),
    )
    michael = CandidateProfile(
        id=11,
        full_name="Michael S.",
        experience_years=11.0,
        availability=Availability.NOT_LOOKING,
        skills=frozenset({"sales", "public-speaking", "team-building"}),
        traits=frozenset({"enthusiastic", "chaotic"}),
    )
    score_dwight = score_pair(dwight, sales_job)
    score_michael = score_pair(michael, sales_job)
    assert score_dwight is not None and score_michael is not None
    assert score_dwight.score > score_michael.score
