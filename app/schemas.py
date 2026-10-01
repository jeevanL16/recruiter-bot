"""Pydantic schemas for API request validation and response serialization."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ==========================================
# Error Schemas
# ==========================================


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ==========================================
# Health Schema
# ==========================================


class HealthResponse(BaseModel):
    status: str
    database: str
    version: str = "0.1.0"


# ==========================================
# Candidate Schemas
# ==========================================


class CandidateCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: str = Field(..., min_length=1, max_length=100)
    experience_years: float = Field(..., ge=0, le=100)
    availability: str = Field(..., description="immediate, two_weeks, or not_looking")
    skills: list[str] = Field(..., min_length=1)
    traits: list[str] = Field(default_factory=list)
    quirk: str | None = Field(default=None, max_length=500)


class CandidateShort(BaseModel):
    id: int
    full_name: str
    experience_years: float
    availability: str


class CandidateResponse(BaseModel):
    id: int
    full_name: str
    experience_years: float
    availability: str
    skills: list[str]
    traits: list[str]
    quirk: str | None = None


# ==========================================
# Job Schemas
# ==========================================


class JobCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=1, max_length=150)
    min_experience_years: float = Field(..., ge=0, le=100)
    required_skills: list[str] = Field(..., min_length=1)
    culture_keywords: list[str] = Field(default_factory=list)
    tagline: str | None = Field(default=None, max_length=500)


class JobShort(BaseModel):
    id: int
    title: str
    min_experience_years: float


class JobResponse(BaseModel):
    id: int
    title: str
    min_experience_years: float
    required_skills: list[str]
    culture_keywords: list[str]
    tagline: str | None = None


# ==========================================
# Match Schemas
# ==========================================


class ScoreBreakdownSchema(BaseModel):
    skills: float
    experience: float
    culture: float
    availability: float


class CandidateMatchItem(BaseModel):
    rank: int
    candidate: CandidateShort
    score: float
    breakdown: ScoreBreakdownSchema
    matched_skills: list[str]
    missing_skills: list[str]
    reason: str


class JobMatchesResponse(BaseModel):
    job: JobShort
    total: int
    limit: int
    offset: int
    matches: list[CandidateMatchItem]


class JobMatchItem(BaseModel):
    rank: int
    job: JobShort
    score: float
    breakdown: ScoreBreakdownSchema
    matched_skills: list[str]
    missing_skills: list[str]
    reason: str


class CandidateMatchesResponse(BaseModel):
    candidate: CandidateShort
    total: int
    limit: int
    offset: int
    matches: list[JobMatchItem]


# ==========================================
# Ingestion & Admin Schemas
# ==========================================


class IngestPayload(BaseModel):
    candidates: list[CandidateCreate]
    jobs: list[JobCreate]


class IngestResponse(BaseModel):
    candidates: int
    jobs: int
    matches: int


class RecomputeResponse(BaseModel):
    recomputed: int
    message: str
