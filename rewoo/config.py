"""Configuration management for ReWoo using pydantic-settings.

Supports multi-environment deployment (dev/staging/prod) with
sensible production defaults. All settings can be overridden
via environment variables or .env files.
"""

from pathlib import Path
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from rewoo.constants import (
    APPROVAL_MODE_AUTO,
    DEFAULT_AUDIT_PATH,
    DEFAULT_MODEL,
    SANDBOX_ENABLED_DEFAULT,
)


class Settings(BaseSettings):
    """ReWoo configuration loaded from environment variables and .env files.

    All settings use the REWOO_ prefix and can be overridden via:
    1. Environment variables (highest priority)
    2. .env file
    3. Default values
    """

    model_config = SettingsConfigDict(
        env_prefix="REWOO_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application ----
    app_name: str = Field(default="ReWoo", description="Application name")
    environment: Literal["development", "staging", "production"] = Field(
        default="development", description="Deployment environment"
    )
    debug: bool = Field(default=False, description="Enable debug mode")
    enable_docs: bool = Field(default=True, description="Enable OpenAPI docs endpoint")

    # ---- LLM Provider ----
    model: str = Field(default=DEFAULT_MODEL, description="Model identifier (e.g. claude-sonnet-4-6, openai/gpt-4o)")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY", description="Anthropic API key")
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY", description="OpenAI API key")
    openrouter_api_key: Optional[str] = Field(default=None, alias="OPENROUTER_API_KEY", description="OpenRouter API key")

    # ---- Execution ----
    approval_mode: Literal["auto", "cli", "none"] = Field(
        default=APPROVAL_MODE_AUTO,
        description="Approval mode: auto (approve LOW/MEDIUM), cli (always ask), none (approve all)",
    )
    sandbox_enabled: bool = Field(default=SANDBOX_ENABLED_DEFAULT, description="Enable sandboxed execution for destructive tools")
    audit_path: Path = Field(default=DEFAULT_AUDIT_PATH, description="Path to the immutable audit log")

    # ---- Limits ----
    max_plan_steps: int = Field(default=20, description="Maximum number of steps in an execution plan")
    max_retries: int = Field(default=3, description="Maximum retries for failed step execution")
    timeout_seconds: int = Field(default=300, description="Default timeout for step execution in seconds")

    # ---- Web tools ----
    web_domain_allowlist: list[str] = Field(default_factory=list, description="Allowed domains for web requests (empty = all)")
    file_allowed_paths: list[str] = Field(default_factory=lambda: ["."], description="Allowed path prefixes for file operations")

    # ---- Memory ----
    skills_dir: Optional[Path] = Field(default=None, description="Directory for learned skills (default: ~/.rewoo/skills)")

    # ---- Database ----
    database_url: str = Field(
        default="postgresql+asyncpg://rewoo:rewoo@localhost:5432/rewoo",
        description="PostgreSQL connection URL (async)",
    )
    db_pool_size: int = Field(default=20, description="Database connection pool size (0 = NullPool)")
    db_max_overflow: int = Field(default=10, description="Max overflow connections beyond pool_size")
    db_echo: bool = Field(default=False, description="Echo SQL statements (debug only)")

    # ---- Redis ----
    redis_url: Optional[str] = Field(default=None, description="Redis connection URL")
    redis_pool_size: int = Field(default=20, description="Redis connection pool size")

    # ---- Celery ----
    celery_broker_url: str = Field(default="redis://localhost:6379/1", description="Celery broker URL")
    celery_result_backend: str = Field(default="redis://localhost:6379/2", description="Celery result backend URL")
    celery_concurrency: int = Field(default=4, description="Number of concurrent Celery workers")
    celery_task_timeout: int = Field(default=600, description="Celery task timeout in seconds")

    # ---- Auth ----
    auth_enabled: bool = Field(default=True, description="Enable authentication")
    jwt_secret: str = Field(default="dev-secret-change-me", description="JWT signing secret")
    jwt_expire_hours: int = Field(default=24, description="JWT token expiration in hours")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm (HS256 or RS256)")
    service_token: Optional[str] = Field(default=None, description="Service token for inter-service auth")

    # ---- CORS ----
    cors_origins: list[str] = Field(
        default_factory=lambda: ["*"],
        description="Allowed CORS origins",
    )

    # ---- Logging ----
    log_level: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)")
    json_logs: bool = Field(default=False, description="Use JSON structured logging (production)")
    sentry_dsn: Optional[str] = Field(default=None, description="Sentry DSN for error tracking")

    # ---- API Server ----
    port: int = Field(default=8000, description="API server port")

    # ---- OpenTelemetry ----
    otel_enabled: bool = Field(default=False, description="Enable OpenTelemetry distributed tracing")
    otel_endpoint: Optional[str] = Field(default=None, description="OTLP endpoint URL")
    otel_headers: dict[str, str] = Field(default_factory=dict, description="Headers sent with each OTLP export request")

    # ---- Rate Limiting ----
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")

    def get_provider(self) -> str:
        """Determine the LLM provider from the model string."""
        if self.model.startswith("openai/") or self.model.startswith("gpt-"):
            return "openai"
        if self.model.startswith("openrouter/"):
            return "openrouter"
        return "anthropic"

    def get_model_name(self) -> str:
        """Extract the model name without provider prefix."""
        for prefix in ("openai/", "openrouter/"):
            if self.model.startswith(prefix):
                return self.model[len(prefix):]
        return self.model

    def ensure_dirs(self) -> None:
        """Create necessary directories if they don't exist."""
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        skills = self.skills_dir or (self.audit_path.parent / "skills")
        skills.mkdir(parents=True, exist_ok=True)

    @property
    def is_production(self) -> bool:
        """Whether this is a production environment."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Whether this is a development environment."""
        return self.environment == "development"
