"""Configuration loader with local JSON config file support.

Loads DB credentials from a local ``config.json`` file so the app works
as a standalone exe without needing a ``.env`` file.  Falls back to
environment variables / ``.env`` for backward compatibility.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv

# Portable config directory that works for both dev and exe
_APP_NAME = "ae-pinner"


def get_config_dir() -> Path:
    """Return the platform-specific config directory for the app."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / _APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_config_path() -> Path:
    """Return the path to the local config.json file."""
    return get_config_dir() / "config.json"


@dataclass
class Config:
    """Application configuration."""

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
    def load(cls, env_path: str | Path | None = None) -> Config:
        """Load config from local JSON first, then .env / env vars as fallback."""
        cfg = cls()

        # 1. Try local config.json
        config_file = get_config_path()
        if config_file.exists():
            try:
                data = json.loads(config_file.read_text(encoding="utf-8"))
                for k, v in data.items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
            except (json.JSONDecodeError, OSError):
                pass

        # 2. Overlay with .env / env vars (these win if set)
        if env_path:
            load_dotenv(env_path)
        else:
            load_dotenv()

        _env_overlay = {
            "pinterest_access_token": os.getenv("PINTEREST_ACCESS_TOKEN"),
            "pinterest_board_id": os.getenv("PINTEREST_BOARD_ID"),
            "openai_api_key": os.getenv("OPENAI_API_KEY"),
            "gemini_api_key": os.getenv("GEMINI_API_KEY"),
            "ae_cookie_xman_us_t": os.getenv("AE_COOKIE_XMAN_US_T"),
            "ae_cookie_xman_us_f": os.getenv("AE_COOKIE_XMAN_US_F"),
            "ae_tracking_id": os.getenv("AE_TRACKING_ID"),
            "pin_language": os.getenv("PIN_LANGUAGE"),
            "pin_ship_to": os.getenv("PIN_SHIP_TO"),
            "pin_currency": os.getenv("PIN_CURRENCY"),
            "db_host": os.getenv("DB_HOST"),
            "db_port": os.getenv("DB_PORT"),
            "db_name": os.getenv("DB_NAME"),
            "db_user": os.getenv("DB_USER"),
            "db_password": os.getenv("DB_PASSWORD"),
        }
        for k, v in _env_overlay.items():
            if v is not None:
                if k == "db_port":
                    setattr(cfg, k, int(v))
                else:
                    setattr(cfg, k, v)

        return cfg

    def save(self) -> Path:
        """Persist current config to the local config.json file."""
        config_file = get_config_path()
        config_file.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return config_file

    def save_db_only(self) -> Path:
        """Save only DB credentials to config.json (merge with existing)."""
        config_file = get_config_path()
        data: dict = {}
        if config_file.exists():
            try:
                data = json.loads(config_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        data["db_host"] = self.db_host
        data["db_port"] = self.db_port
        data["db_name"] = self.db_name
        data["db_user"] = self.db_user
        data["db_password"] = self.db_password

        config_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return config_file

    @property
    def db_configured(self) -> bool:
        return bool(self.db_host and self.db_name and self.db_user)

    def validate(self) -> list[str]:
        """Return list of missing required config fields."""
        missing = []
        if not self.pinterest_access_token:
            missing.append("PINTEREST_ACCESS_TOKEN")
        if not self.pinterest_board_id:
            missing.append("PINTEREST_BOARD_ID")
        if not self.openai_api_key and not self.gemini_api_key:
            missing.append("OPENAI_API_KEY or GEMINI_API_KEY")
        if not self.ae_cookie_xman_us_t:
            missing.append("AE_COOKIE_XMAN_US_T")
        return missing
