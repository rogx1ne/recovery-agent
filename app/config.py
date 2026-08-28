"""
config.py — Application configuration via environment variables.
Loads settings from .env (via python-dotenv) and exposes a typed Settings object.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Razorpay credentials (test mode)
    razorpay_key_id: str = "rzp_test_placeholder"
    razorpay_key_secret: str = "placeholder_secret"
    # Webhook secret (from Razorpay Dashboard > Webhooks). Leave blank for local dev.
    razorpay_webhook_secret: str = ""

    # Groq API (free tier: 14,400 req/day — https://console.groq.com/keys)
    # Leave blank to use rules-based classifier instead.
    groq_api_key: str = ""

    # Legacy Gemini API key fallback (optional)
    gemini_api_key: str = ""

    # Set to false to force rules-based classification (useful for testing)
    use_llm_classifier: bool = True

    # Database
    database_url: str = "sqlite:///./recovery_agent.db"

    # App environment
    app_env: str = "development"

    # Recovery policy timing (seconds)
    card_declined_retry_delay_seconds: int = 5
    gateway_error_retry_delay_seconds: int = 2

    # Payment link settings
    payment_link_expire_minutes: int = 60
    callback_url: str = "http://localhost:8000/api/v1/transactions/callback"


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()
