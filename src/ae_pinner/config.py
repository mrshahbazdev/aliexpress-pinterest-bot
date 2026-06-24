"""Configuration loader from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    """Application configuration loaded from .env file."""

    # Pinterest
    pinterest_access_token: str = ""
    pinterest_board_id: str = ""

    # AI (choose one or both)
    openai_api_key: str = ""
    gemini_api_key: str = ""

    # AliExpress
    ae_cookie_xman_us_t: str = ""
    ae_cookie_xman_us_f: str = ""
    ae_tracking_id: str = "default"

    # Pin settings
    pin_language: str = "en"
    pin_ship_to: str = "US"
    pin_currency: str = "USD"

    # Database
    db_host: str = ""
    db_port: int = 3306
    db_name: str = ""
    db_user: str = ""
    db_password: str = ""

    @classmethod
    def load(cls, env_path: str | Path | None = None) -> "Config":
        """Load configuration from .env file and environment variables."""
        if env_path:
            load_dotenv(env_path)
        else:
            load_dotenv()

        return cls(
            pinterest_access_token=os.getenv("PINTEREST_ACCESS_TOKEN", ""),
            pinterest_board_id=os.getenv("PINTEREST_BOARD_ID", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            ae_cookie_xman_us_t=os.getenv("AE_COOKIE_XMAN_US_T", ""),
            ae_cookie_xman_us_f=os.getenv("AE_COOKIE_XMAN_US_F", ""),
            ae_tracking_id=os.getenv("AE_TRACKING_ID", "default"),
            pin_language=os.getenv("PIN_LANGUAGE", "en"),
            pin_ship_to=os.getenv("PIN_SHIP_TO", "US"),
            pin_currency=os.getenv("PIN_CURRENCY", "USD"),
            db_host=os.getenv("DB_HOST", ""),
            db_port=int(os.getenv("DB_PORT", "3306")),
            db_name=os.getenv("DB_NAME", ""),
            db_user=os.getenv("DB_USER", ""),
            db_password=os.getenv("DB_PASSWORD", ""),
        )

    def validate(self) -> list[str]:
        """Return list of missing required config fields."""
        missing = []
        if not self.pinterest_access_token:
            missing.append("PINTEREST_ACCESS_TOKEN")
        if not self.pinterest_board_id:
            missing.append("PINTEREST_BOARD_ID")
        if not self.openai_api_key and not self.gemini_api_key:
            missing.append("OPENAI_API_KEY or GEMINI_API_KEY (at least one required)")
        if not self.ae_cookie_xman_us_t:
            missing.append("AE_COOKIE_XMAN_US_T")
        return missing
