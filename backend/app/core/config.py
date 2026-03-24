from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_LOCAL_FRONTEND_ORIGINS = [
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://127.0.0.1:5501",
    "http://localhost:5501",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AI Math Tutor"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/ksmathtutordb"
    redis_url: str = "redis://localhost:6379"

    # LLM
    groq_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    cerebras_api_key: str = ""
    default_llm_provider: str = "groq"  # "groq" | "anthropic" | "openai" | "gemini" | "cerebras"
    diagnosis_mode: str = "ml_shadow"   # "llm" | "ml_shadow" | "ml_primary"
    diagnosis_model_dir: str = "data/models/diagnosis"
    diagnosis_taxonomy_dir: str = "data/diagnosis_taxonomy"
    diagnosis_ml_primary_min_confidence: float = 0.62
    diagnosis_background_queue_key: str = "diagnosis:bg:queue"
    diagnosis_background_retry_limit: int = 3
    diagnosis_background_stale_after_sec: int = 300
    diagnosis_overlay_auto_promote_threshold: float = 0.9
    diagnosis_overlay_review_threshold: float = 0.75
    tts_provider: str = "polly"         # "polly" | "mock"
    tts_voice_id: str = "Joanna"
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_session_token: str = ""

    # CORS
    frontend_origins: str = ""
    frontend_url: str = ""

    @field_validator("debug", mode="before")
    @classmethod
    def _coerce_debug(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production"}:
                return False
        return value

    @staticmethod
    def _normalize_origin(origin: str) -> str:
        return origin.strip().rstrip("/")

    @property
    def allowed_frontend_origins(self) -> list[str]:
        candidates: list[str]
        if self.frontend_origins.strip():
            candidates = self.frontend_origins.split(",")
        elif self.frontend_url.strip():
            candidates = [self.frontend_url]
        else:
            candidates = DEFAULT_LOCAL_FRONTEND_ORIGINS

        normalized: list[str] = []
        for candidate in candidates:
            origin = self._normalize_origin(candidate)
            if origin and origin not in normalized:
                normalized.append(origin)

        if not normalized:
            return DEFAULT_LOCAL_FRONTEND_ORIGINS.copy()

        return normalized


settings = Settings()
