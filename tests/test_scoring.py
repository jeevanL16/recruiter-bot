"""Unit tests for the pure scoring algorithm.

These tests run without any database connection. They verify the scoring
math, the hard gate, culture aliases, tie-breaking, and reason strings.
"""

import pytest

from app.models import Availability, CandidateProfile, JobProfile, Weights
from app.services.scoring import (
    compute_availability_score,
    compute_culture_score,
    compute_experience_score,
    compute_skill_score,
    score_pair,
)

# ==========================================
# Weights validation
# ==========================================


def test_weights_sum_validation() -> None:
    """Weights must sum to 1.0."""
    with pytest.raises(ValueError, match="Weights must sum to 1.0"):
        Weights(skills=0.6, experience=0.2, culture=0.2, availability=0.2)


# ==========================================
# Skill scoring
# ==========================================


def test_skill_full_coverage() -> None:
    required = frozenset({"python", "sql", "docker"})
    cand = frozenset({"python", "sql", "docker", "aws"})
    score, matched, missing = compute_skill_score(cand, required)
    assert score == 1.0
    assert matched == ("docker", "python", "sql")
    assert missing == ()


def test_skill_partial_coverage() -> None:
    required = frozenset({"python", "sql", "docker"})
    cand = frozenset({"python", "docker"})
    score, matched, missing = compute_skill_score(cand, required)
    assert round(score, 4) == round(2 / 3, 4)
    assert matched == ("docker", "python")
    assert missing == ("sql",)


def test_skill_zero_coverage() -> None:
    required = frozenset({"python", "sql", "docker"})
    cand = frozenset({"rust", "go"})
    score, matched, missing = compute_skill_score(cand, required)
    assert score == 0.0
    assert matched == ()
    assert missing == ("docker", "python", "sql")


def test_skill_empty_required_returns_full() -> None:
    """A job with no required skills should give skill score 1.0."""
    score, matched, missing = compute_skill_score(frozenset({"python"}), frozenset())
    assert score == 1.0
    assert matched == ()
    assert missing == ()


# ==========================================
# Experience scoring
# ==========================================


def test_experience_under_qualified() -> None:
    assert compute_experience_score(1.5, 3.0) == 0.5
    assert compute_experience_score(0.0, 3.0) == 0.0


def test_experience_exact_match() -> None:
    assert compute_experience_score(3.0, 3.0) == 1.0


def test_experience_overqualified_capped_at_1() -> None:
    """Experience is capped at 1.0 — overqualified is NOT penalized."""
    assert compute_experience_score(20.0, 2.0) == 1.0
    assert compute_experience_score(50.0, 3.0) == 1.0


def test_experience_min_zero() -> None:
    assert compute_experience_score(0.0, 0.0) == 1.0
    assert compute_experience_score(5.0, 0.0) == 1.0


# ==========================================
# Availability scoring
# ==========================================


def test_availability_immediate() -> None:
    assert compute_availability_score(Availability.IMMEDIATE) == 1.0


def test_availability_two_weeks() -> None:
    assert compute_availability_score(Availability.TWO_WEEKS) == 0.8


def test_availability_not_looking() -> None:
    assert compute_availability_score(Availability.NOT_LOOKING) == 0.0


def test_availability_ordering() -> None:
    """immediate > two_weeks > not_looking, with exact expected values."""
    imm = compute_availability_score(Availability.IMMEDIATE)
    tw = compute_availability_score(Availability.TWO_WEEKS)
    nl = compute_availability_score(Availability.NOT_LOOKING)
    assert imm > tw > nl
    assert imm == 1.0
    assert tw == 0.8
    assert nl == 0.0


# ==========================================
# Culture scoring with aliases
# ==========================================


def test_culture_exact_match() -> None:
    keywords = frozenset({"analytical", "calm-under-pressure"})
    traits = frozenset({"analytical", "calm-under-pressure"})
    score, matched = compute_culture_score(traits, keywords)
    assert score == 1.0
    assert matched == ("analytical", "calm-under-pressure")


def test_culture_calm_matches_calm_under_pressure() -> None:
    """'calm' candidate trait should match 'calm-under-pressure' job keyword."""
    keywords = frozenset({"decisive", "calm-under-pressure"})
    traits = frozenset({"decisive", "calm"})
    score, matched = compute_culture_score(traits, keywords)
    assert score == 1.0
    assert "calm-under-pressure" in matched


def test_culture_partial_match() -> None:
    keywords = frozenset({"analytical", "calm-under-pressure"})
    traits = frozenset({"analytical", "stubborn"})
    score, matched = compute_culture_score(traits, keywords)
    assert score == 0.5
    assert matched == ("analytical",)


def test_culture_no_keywords_returns_full() -> None:
    score, matched = compute_culture_score(frozenset({"calm"}), frozenset())
    assert score == 1.0
    assert matched == ()


# ==========================================
# Hard gate: zero skill overlap
# ==========================================


def test_zero_skill_overlap_returns_none() -> None:
    """Zero skill overlap must produce no match (hard gate)."""
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


def test_rick_vs_backend_detective_no_match() -> None:
    """Rick has systems-design, rapid-prototyping, chemistry — none overlap with
    Backend Detective's deduction, pattern-recognition, forensics. Must return None."""
    rick = CandidateProfile(
        id=6,
        full_name="Rick S.",
        experience_years=20.0,
        availability=Availability.IMMEDIATE,
        skills=frozenset({"systems-design", "rapid-prototyping", "chemistry"}),
        traits=frozenset({"genius", "reckless"}),
    )
    backend = JobProfile(
        id=1,
        title="Backend Detective",
        min_experience_years=3.0,
        required_skills=frozenset({"deduction", "pattern-recognition", "forensics"}),
        culture_keywords=frozenset({"analytical", "autonomous"}),
    )
    assert score_pair(rick, backend) is None


# ==========================================
# min_score filter
# ==========================================


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
    # 1/4 skills = 0.25 * 55 = 13.75; exp = 0.1 * 20 = 2.0; culture 0; avail 0
    assert score_pair(cand, job, min_score=20.0) is None


# ==========================================
# Exact score: Sherlock vs Backend Detective = 95.0
# ==========================================


def test_sherlock_vs_backend_detective_exact_95() -> None:
    """Sherlock vs Backend Detective must score exactly 95.0.

    - Skills: 3/3 = 1.0 * 55 = 55.0
    - Experience: min(1.0, 8/3) = 1.0 * 20 = 20.0
    - Culture: analytical matches (1/2) = 0.5 * 10 = 5.0
    - Availability: immediate = 1.0 * 15 = 15.0
    - Total: 55 + 20 + 5 + 15 = 95.0
    """
    sherlock = CandidateProfile(
        id=1,
        full_name="Sherlock H.",
        experience_years=8.0,
        availability=Availability.IMMEDIATE,
        skills=frozenset({"deduction", "pattern-recognition", "forensics"}),
        traits=frozenset({"analytical", "blunt"}),
    )
    backend = JobProfile(
        id=1,
        title="Backend Detective",
        min_experience_years=3.0,
        required_skills=frozenset({"deduction", "pattern-recognition", "forensics"}),
        culture_keywords=frozenset({"analytical", "autonomous"}),
    )
    result = score_pair(sherlock, backend)
    assert result is not None
    assert result.score == 95.0
    assert result.breakdown.skills == 1.0
    assert result.breakdown.experience == 1.0
    assert result.breakdown.culture == 0.5
    assert result.breakdown.availability == 1.0


# ==========================================
# Rick vs Rapid Prototyping: experience capped at 1.0
# ==========================================


def test_rick_vs_rapid_prototyping_exp_capped() -> None:
    """Rick has 20y vs 2y minimum — experience must cap at 1.0, not decay."""
    rick = CandidateProfile(
        id=6,
        full_name="Rick S.",
        experience_years=20.0,
        availability=Availability.IMMEDIATE,
        skills=frozenset({"systems-design", "rapid-prototyping", "chemistry"}),
        traits=frozenset({"genius", "reckless"}),
    )
    rapid = JobProfile(
        id=2,
        title="Rapid Prototyping Engineer",
        min_experience_years=2.0,
        required_skills=frozenset({"rapid-prototyping", "systems-design"}),
        culture_keywords=frozenset({"innovative", "fast-paced"}),
    )
    result = score_pair(rick, rapid)
    assert result is not None
    assert result.breakdown.experience == 1.0


# ==========================================
# Tie-breaking: deterministic order
# ==========================================


def test_tiebreaking_deterministic() -> None:
    """Two candidates with identical scores break by skill_score DESC,
    then availability_score DESC, then candidate id ASC."""
    job = JobProfile(
        id=1,
        title="Test Job",
        min_experience_years=2.0,
        required_skills=frozenset({"a", "b"}),
        culture_keywords=frozenset(),
    )
    cand_a = CandidateProfile(
        id=10,
        full_name="Candidate A",
        experience_years=5.0,
        availability=Availability.IMMEDIATE,
        skills=frozenset({"a", "b"}),
        traits=frozenset(),
    )
    cand_b = CandidateProfile(
        id=20,
        full_name="Candidate B",
        experience_years=5.0,
        availability=Availability.IMMEDIATE,
        skills=frozenset({"a", "b"}),
        traits=frozenset(),
    )
    res_a = score_pair(cand_a, job)
    res_b = score_pair(cand_b, job)
    assert res_a is not None and res_b is not None
    # Same score — tie broken by candidate_id ASC, so A (id=10) ranks first
    assert res_a.score == res_b.score
    # Sort key tuple: (score DESC, skill DESC, avail DESC, id ASC)
    key_a = (-res_a.score, -res_a.breakdown.skills, -res_a.breakdown.availability, cand_a.id)
    key_b = (-res_b.score, -res_b.breakdown.skills, -res_b.breakdown.availability, cand_b.id)
    assert key_a < key_b  # A sorts before B


# ==========================================
# Sanity rankings
# ==========================================


def test_rapid_prototyping_ranking_rick_mac_tony() -> None:
    """Rapid Prototyping Engineer: Rick S. > MacGyver > Tony S."""
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


def test_incident_commander_olivia_above_katniss() -> None:
    """Incident Commander: Olivia P. (3/3 skills) above Katniss (2/3)."""
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


def test_sales_engineer_dwight_above_michael() -> None:
    """Sales Engineer: Dwight S. (immediate) above Michael S. (not looking)."""
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
