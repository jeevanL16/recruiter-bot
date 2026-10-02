"""Pure matching and scoring algorithm for Recruiter Bot.

This module has zero I/O and zero database dependencies.
All calculations are pure, deterministic, and easily tested.
"""

from __future__ import annotations

from app.models import (
    DEFAULT_WEIGHTS,
    Availability,
    CandidateProfile,
    JobProfile,
    ScoreBreakdown,
    ScoreResult,
    Weights,
)

SCORING_VERSION = "v1"

# ---------------------------------------------------------------------------
# Culture keyword alias map
# ---------------------------------------------------------------------------
# Some job culture keywords are compound phrases that should match simpler
# candidate traits. For example, a job that wants "calm-under-pressure"
# should accept a candidate whose trait is "calm".
#
# This map is intentionally small and explicit. Each key is a culture keyword
# that may appear on a job; the value is the set of candidate-trait strings
# that should count as a match for that keyword (in addition to the keyword
# itself, which is always checked via exact match first).
#
# To add a new alias: add ONE entry here. Both directions are NOT required
# because the lookup is always job-keyword -> candidate-trait.
# ---------------------------------------------------------------------------
CULTURE_ALIASES: dict[str, set[str]] = {
    "calm-under-pressure": {"calm"},
}


def normalize_token(token: str) -> str:
    """Normalize skill or trait string to lowercase trimmed kebab-case."""
    return token.strip().lower().replace("_", "-").replace(" ", "-")


def compute_skill_score(
    candidate_skills: frozenset[str], required_skills: frozenset[str]
) -> tuple[float, tuple[str, ...], tuple[str, ...]]:
    """Compute skill overlap score (recall-based) and matched/missing skill lists.

    Returns (score, matched_skills_tuple, missing_skills_tuple).
    If the job has no required skills, returns (1.0, (), ()).
    """
    if not required_skills:
        return 1.0, (), ()

    matched = tuple(sorted(candidate_skills & required_skills))
    missing = tuple(sorted(required_skills - candidate_skills))
    score = len(matched) / len(required_skills)
    return score, matched, missing


def compute_experience_score(candidate_exp: float, min_exp: float) -> float:
    """Compute experience fit score.

    - If job requires 0 years: 1.0
    - Under-qualified: proportional (candidate / min)
    - At or above minimum: capped at 1.0 (overqualified is NOT penalized)
    """
    if min_exp <= 0:
        return 1.0
    return min(1.0, candidate_exp / min_exp)


def compute_culture_score(
    candidate_traits: frozenset[str], culture_keywords: frozenset[str]
) -> tuple[float, tuple[str, ...]]:
    """Compute culture fit score using exact and alias-based matching.

    For each job culture keyword we check:
      1. Does the candidate have the keyword itself as a trait? (exact match)
      2. Does the candidate have any trait listed in CULTURE_ALIASES for that keyword?
    """
    if not culture_keywords:
        return 1.0, ()

    matched_keywords: set[str] = set()

    for keyword in culture_keywords:
        # Exact match first
        if keyword in candidate_traits:
            matched_keywords.add(keyword)
            continue
        # Alias match
        aliases = CULTURE_ALIASES.get(keyword, set())
        if aliases & candidate_traits:
            matched_keywords.add(keyword)

    score = len(matched_keywords) / len(culture_keywords)
    return score, tuple(sorted(matched_keywords))


def compute_availability_score(availability: Availability) -> float:
    """Map candidate availability to score:

    - immediate: 1.0
    - two_weeks: 0.8
    - not_looking: 0.0
    """
    match availability:
        case Availability.IMMEDIATE:
            return 1.0
        case Availability.TWO_WEEKS:
            return 0.8
        case Availability.NOT_LOOKING:
            return 0.0


def build_reason_string(
    matched_skills: tuple[str, ...],
    missing_skills: tuple[str, ...],
    total_required_skills: int,
    candidate_exp: float,
    min_exp: float,
    matched_culture: tuple[str, ...],
    total_culture: int,
    availability: Availability,
) -> str:
    """Build a concise, human-readable reason string explaining the score."""
    parts: list[str] = []

    # 1. Skills summary
    parts.append(f"Matches {len(matched_skills)}/{total_required_skills} required skills")
    if missing_skills:
        parts.append(f"missing {', '.join(missing_skills)}")

    # 2. Experience summary
    exp_c = f"{candidate_exp:g}"
    exp_m = f"{min_exp:g}"
    parts.append(f"{exp_c}y vs {exp_m}y minimum")

    # 3. Availability summary
    match availability:
        case Availability.IMMEDIATE:
            parts.append("available immediately")
        case Availability.TWO_WEEKS:
            parts.append("available in 2 weeks")
        case Availability.NOT_LOOKING:
            parts.append("not currently looking")

    # 4. Culture summary
    parts.append(f"culture {len(matched_culture)}/{total_culture}")

    return "; ".join(parts) + "."


def score_pair(
    candidate: CandidateProfile,
    job: JobProfile,
    weights: Weights = DEFAULT_WEIGHTS,
    min_score: float = 0.0,
) -> ScoreResult | None:
    """Calculate the match score between a candidate and a job.

    Returns None if:
    - Candidate has ZERO overlap with the job's required skills (hard gate).
    - Final calculated score < min_score.
    """
    skill_score, matched_skills, missing_skills = compute_skill_score(
        candidate.skills, job.required_skills
    )

    # Hard gate: if zero required skills overlap, never create a match
    if skill_score == 0.0 and job.required_skills:
        return None

    experience_score = compute_experience_score(
        candidate.experience_years, job.min_experience_years
    )
    culture_score, matched_culture = compute_culture_score(candidate.traits, job.culture_keywords)
    availability_score = compute_availability_score(candidate.availability)

    raw_score = (
        (weights.skills * skill_score)
        + (weights.experience * experience_score)
        + (weights.culture * culture_score)
        + (weights.availability * availability_score)
    )

    final_score = round(raw_score * 100, 2)

    if final_score < min_score:
        return None

    breakdown = ScoreBreakdown(
        skills=round(skill_score, 3),
        experience=round(experience_score, 3),
        culture=round(culture_score, 3),
        availability=round(availability_score, 3),
    )

    reason = build_reason_string(
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        total_required_skills=len(job.required_skills),
        candidate_exp=candidate.experience_years,
        min_exp=job.min_experience_years,
        matched_culture=matched_culture,
        total_culture=len(job.culture_keywords),
        availability=candidate.availability,
    )

    return ScoreResult(
        score=final_score,
        breakdown=breakdown,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        reason=reason,
        scoring_version=SCORING_VERSION,
    )
