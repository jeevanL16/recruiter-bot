"""Domain models and value objects for matching and profile representation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class Availability(StrEnum):
    IMMEDIATE = "immediate"
    TWO_WEEKS = "two_weeks"
    NOT_LOOKING = "not_looking"

    @classmethod
    def from_str(cls, val: str) -> Availability:
        normalized = val.strip().lower().replace(" ", "_").replace("-", "_")
        mapping = {
            "immediate": cls.IMMEDIATE,
            "two_weeks": cls.TWO_WEEKS,
            "2_weeks": cls.TWO_WEEKS,
            "not_looking": cls.NOT_LOOKING,
            "notlooking": cls.NOT_LOOKING,
        }
        if normalized in mapping:
            return mapping[normalized]
        for member in cls:
            if member.value == normalized:
                return member
        raise ValueError(f"Unknown availability: {val}")


@dataclass(frozen=True, slots=True)
class Weights:
    skills: float = 0.55
    experience: float = 0.20
    culture: float = 0.10
    availability: float = 0.15

    def __post_init__(self) -> None:
        total = self.skills + self.experience + self.culture + self.availability
        if not math.isclose(total, 1.0, rel_tol=1e-3, abs_tol=1e-3):
            raise ValueError(f"Weights must sum to 1.0, got {total:.4f}")


DEFAULT_WEIGHTS = Weights()


@dataclass(frozen=True, slots=True)
class CandidateProfile:
    id: int
    full_name: str
    experience_years: float
    availability: Availability
    skills: frozenset[str]
    traits: frozenset[str]
    quirk: str | None = None


@dataclass(frozen=True, slots=True)
class JobProfile:
    id: int
    title: str
    min_experience_years: float
    required_skills: frozenset[str]
    culture_keywords: frozenset[str]
    tagline: str | None = None


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    skills: float
    experience: float
    culture: float
    availability: float


@dataclass(frozen=True, slots=True)
class ScoreResult:
    score: float
    breakdown: ScoreBreakdown
    matched_skills: tuple[str, ...]
    missing_skills: tuple[str, ...]
    reason: str
    scoring_version: str = "v1"
