"""Application configuration management using pydantic-settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.models import Weights


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    db_host: str = Field(default="127.0.0.1", alias="DB_HOST")
    db_port: int = Field(default=3306, alias="DB_PORT")
    db_user: str = Field(default="root", alias="DB_USER")
    db_password: str = Field(default="", alias="DB_PASSWORD")
    db_name: str = Field(default="recruiter_bot", alias="DB_NAME")
    db_pool_size: int = Field(default=5, alias="DB_POOL_SIZE")

    # Application Defaults
    min_score_default: float = Field(default=20.0, alias="MIN_SCORE_DEFAULT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Scoring Weights
    weight_skills: float = Field(default=0.55, alias="WEIGHT_SKILLS")
    weight_experience: float = Field(default=0.20, alias="WEIGHT_EXPERIENCE")
    weight_culture: float = Field(default=0.10, alias="WEIGHT_CULTURE")
    weight_availability: float = Field(default=0.15, alias="WEIGHT_AVAILABILITY")

    def get_weights(self) -> Weights:
        return Weights(
            skills=self.weight_skills,
            experience=self.weight_experience,
            culture=self.weight_culture,
            availability=self.weight_availability,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
