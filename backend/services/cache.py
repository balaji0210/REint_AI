"""File-based cache for Elexon BMRS API data.

Caches raw API DataFrames to disk (data/cache) with a 24-hour TTL
to avoid hitting Elexon repeatedly during exploratory analysis.
"""

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple, Union

import pandas as pd

logger = logging.getLogger(__name__)

# Cache directory at project root (or overridden via CACHE_DIR env var)
DEFAULT_CACHE_DIR = Path(
    os.environ.get("CACHE_DIR", str(Path(__file__).resolve().parent.parent.parent / "data" / "cache"))
)
DEFAULT_TTL = timedelta(hours=24)


class FileCache:
    """Manages file-based JSON caching with a specified Time-To-Live (TTL)."""

    def __init__(self, cache_dir: Union[str, Path] = DEFAULT_CACHE_DIR, ttl: timedelta = DEFAULT_TTL):
        self.cache_dir = Path(cache_dir)
        self.ttl = ttl
        self._ensure_cache_dir()

    def _ensure_cache_dir(self):
        """Create cache directory if it does not already exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, key: str) -> Path:
        safe_key = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in key)
        return self.cache_dir / f"{safe_key}.json"

    def get(self, key: str) -> Optional[pd.DataFrame]:
        """Retrieve cached DataFrame if valid and not expired."""
        path = self._get_cache_path(key)
        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)

            expires_at_str = payload.get("expires_at")
            if not expires_at_str:
                return None

            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now(timezone.utc) >= expires_at:
                logger.info(f"Cache expired for key '{key}'")
                return None

            records = payload.get("data", [])
            if not records:
                return pd.DataFrame()

            df = pd.DataFrame(records)
            # Restore UTC timestamps if timestamp columns exist
            for col in ("startTime", "publishTime"):
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], utc=True)
            return df
        except Exception as e:
            logger.warning(f"Error reading cache file {path}: {e}")
            return None

    def set(self, key: str, df: pd.DataFrame):
        """Save DataFrame to cache file with TTL expiration."""
        path = self._get_cache_path(key)
        try:
            now = datetime.now(timezone.utc)
            expires_at = now + self.ttl

            # Convert timestamps to ISO 8601 strings for clean JSON serialization
            df_to_save = df.copy()
            for col in ("startTime", "publishTime"):
                if col in df_to_save.columns and pd.api.types.is_datetime64_any_dtype(df_to_save[col]):
                    df_to_save[col] = df_to_save[col].dt.strftime("%Y-%m-%dT%H:%M:%SZ")

            # Replace NaNs with None for JSON compliance
            records = df_to_save.replace({float("nan"): None}).to_dict(orient="records")

            payload = {
                "key": key,
                "cached_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "ttl_seconds": self.ttl.total_seconds(),
                "record_count": len(records),
                "data": records,
            }

            temp_path = path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            temp_path.replace(path)
            logger.info(f"Cached {len(records)} records for key '{key}' until {expires_at.isoformat()}")
        except Exception as e:
            logger.error(f"Failed to write cache for key '{key}': {e}")
