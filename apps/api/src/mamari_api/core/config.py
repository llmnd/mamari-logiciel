import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[5]


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "postgresql+asyncpg://mamari:mamari@localhost:5432/mamari"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    jwt_secret_key: SecretStr = SecretStr("development-only-change-before-production")
    bootstrap_admin_username: str = "mamari"
    bootstrap_admin_password: SecretStr = SecretStr("passer123m")
    public_store_slug: str = "mamari"
    delivery_origin_latitude: float = Field(default=12.1348, ge=-90, le=90)
    delivery_origin_longitude: float = Field(default=15.0557, ge=-180, le=180)
    delivery_free_radius_km: float = Field(default=5, gt=0)
    delivery_standard_radius_km: float = Field(default=15, gt=0)
    delivery_extended_radius_km: float = Field(default=30, gt=0)
    delivery_standard_fee_fcfa: int = Field(default=1000, ge=0)
    delivery_extended_fee_fcfa: int = Field(default=2000, ge=0)
    access_token_minutes: int = Field(default=15, ge=5, le=60)
    upload_directory: Path = PROJECT_ROOT / "storage" / "uploads"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, list):
            return value

        raw_value = value.strip()
        if raw_value.startswith("["):
            try:
                origins = json.loads(raw_value)
            except json.JSONDecodeError as error:
                if not raw_value.endswith("]"):
                    raise ValueError(
                        "CORS_ORIGINS doit être une liste JSON ou séparée par des virgules."
                    ) from error
                raw_value = raw_value[1:-1]
            else:
                if not isinstance(origins, list):
                    raise ValueError("CORS_ORIGINS doit être une liste.")
                return origins

        return [
            origin.strip().strip("\"'")
            for origin in raw_value.strip("[]").split(",")
            if origin.strip().strip("\"'")
        ]

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env == "production":
            secret = self.jwt_secret_key.get_secret_value()
            if len(secret) < 32 or secret == "development-only-change-before-production":
                raise ValueError(
                    "Définir un JWT_SECRET_KEY unique d'au moins 32 caractères en production."
                )
        return self

    @model_validator(mode="after")
    def validate_delivery_ranges(self) -> "Settings":
        if not (
            self.delivery_free_radius_km
            < self.delivery_standard_radius_km
            < self.delivery_extended_radius_km
        ):
            raise ValueError("Les rayons de livraison doivent être strictement croissants.")
        return self

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
