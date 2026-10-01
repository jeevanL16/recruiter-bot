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

# Culture keyword aliases for semantic trait matching
TRAIT_ALIASES: dict[str, set[str]] = {
    "calm": {"calm-under-pressure", "calm"},
    "calm-under-pressure": {"calm", "calm-under-pressure"},
    "persistent": {"tenacious", "persistent"},
    "tenacious": {"persistent", "tenacious"},
    "analytical": {"analytical", "theoretical-analysis"},
    "organized": {"organized", "detail-oriented"},
    "detail-oriented": {"organized", "detail-oriented"},
}


def normalize_token(token: str) -> str:
    """Normalize skill or trait string to lowercase trimmed kebab-case."""
    return token.strip().lower().replace("_", "-").replace(" ", "-")


def compute_skill_score(
    candidate_skills: frozenset[str], required_skills: frozenset[str]
) -> tuple[float, tuple[str, ...], tuple[str, ...]]:
    """Compute skill overlap score (recall-based) and matched/missing skill lists."""
    if not required_skills:
        return 0.0, (), ()

    matched = tuple(sorted(candidate_skills & required_skills))
    missing = tuple(sorted(required_skills - candidate_skills))
    score = len(matched) / len(required_skills)
    return score, matched, missing


def compute_experience_score(candidate_exp: float, min_exp: float) -> float:
    """Compute experience fit score.

    - Under-qualified: proportional shortfall (exp / min).
    - Sweet spot: [min, max(2 * min, min + 5)] -> 1.0.
    - Over-qualified: decay of 0.02 per year above ceiling, with a 0.70 floor.
    """
    if min_exp <= 0:
        return 1.0

    if candidate_exp < min_exp:
        return max(0.0, candidate_exp / min_exp)

    upper_bound = max(2.0 * min_exp, min_exp + 5.0)
    if candidate_exp <= upper_bound:
        return 1.0

    # Over-qualified decay
    decay = min(0.30, 0.02 * (candidate_exp - upper_bound))
    return round(1.0 - decay, 3)


def compute_culture_score(
    candidate_traits: frozenset[str], culture_keywords: frozenset[str]
) -> tuple[float, tuple[str, ...]]:
    """Compute culture fit score using exact and alias-based matching."""
    if not culture_keywords:
        return 1.0, ()

    matched_keywords: set[str] = set()

    for keyword in culture_keywords:
        aliases = TRAIT_ALIASES.get(keyword, {keyword})
        if any(trait in aliases for trait in candidate_traits):
            matched_keywords.add(keyword)

    score = len(matched_keywords) / len(culture_keywords)
    return score, tuple(sorted(matched_keywords))


def compute_availability_score(availability: Availability) -> float:
    """Map candidate availability to score:

    - immediate: 1.0
    - two_weeks: 0.7
    - not_looking: 0.0
    """
    match availability:
        case Availability.IMMEDIATE:
            return 1.0
        case Availability.TWO_WEEKS:
            return 0.7
        case Availability.NOT_LOOKING:
            return 0.0


def build_reason_string(
    matched_skills: tuple[str, ...],
    missing_skills: tuple[str, ...],
    total_required_skills: int,
    candidate_exp: float,
    min_exp: float,
    matched_culture: tuple[str, ...],
    availability: Availability,
) -> str:
    """Build a concise, human-readable reason string explaining the score."""
    parts: list[str] = []

    # 1. Skills summary
    skills_part = f"Covers {len(matched_skills)}/{total_required_skills} required skills"
    if matched_skills:
        skills_part += f" ({', '.join(matched_skills)})"
    parts.append(skills_part)

    if missing_skills:
        parts.append(f"missing: {', '.join(missing_skills)}")

    # 2. Experience summary
    upper_bound = max(2.0 * min_exp, min_exp + 5.0)
    exp_c_str = f"{candidate_exp:g}"
    exp_m_str = f"{min_exp:g}"
    if candidate_exp < min_exp:
        parts.append(f"short on experience ({exp_c_str} yrs vs {exp_m_str} min)")
    elif candidate_exp > upper_bound:
        parts.append(f"{exp_c_str} yrs vs {exp_m_str} min (over-qualified)")
    else:
        parts.append(f"{exp_c_str} yrs vs {exp_m_str} min")

    # 3. Culture summary
    if matched_culture:
        parts.append(f"culture: {', '.join(matched_culture)}")

    # 4. Availability summary
    match availability:
        case Availability.IMMEDIATE:
            parts.append("available immediately")
        case Availability.TWO_WEEKS:
            parts.append("available in 2 weeks")
        case Availability.NOT_LOOKING:
            parts.append("not currently looking")

    return "; ".join(parts) + "."


def score_pair(
    candidate: CandidateProfile,
    job: JobProfile,
    weights: Weights = DEFAULT_WEIGHTS,
    min_score: float = 0.0,
) -> ScoreResult | None:
    """Calculate the match score between a candidate and a job.

    Returns None if:
    - Candidate has 0 required skills (eligibility gate).
    - Job has 0 required skills.
    - Final calculated score < min_score.
    """
    if not job.required_skills:
        return None

    skill_score, matched_skills, missing_skills = compute_skill_score(
        candidate.skills, job.required_skills
    )

    # Hard eligibility gate: 0 skill overlap is considered noise
    if skill_score == 0.0:
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
