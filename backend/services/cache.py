"""File-based cache for Elexon BMRS API data.

Caches raw API DataFrames to disk (data/cache) with a 24-hour TTL
to avoid hitting Elexon repeatedly during exploratory analysis.
"""

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import pandas as pd

logger = logging.getLogger(__name__)


def get_candidate_cache_dirs() -> List[Path]:
    """Return ordered list of cache search paths."""
    candidates = []
    env_cache = os.environ.get("CACHE_DIR")
    if env_cache:
        candidates.append(Path(env_cache))

    # 1. Local backend data/cache directory (bundled in isolated backend deployment)
    candidates.append(Path(__file__).resolve().parent.parent / "data" / "cache")

    # 2. Project root data/cache directory
    candidates.append(Path(__file__).resolve().parent.parent.parent / "data" / "cache")

    # 3. Serverless writable /tmp cache directory
    candidates.append(Path("/tmp/reint_cache"))

    # Return unique paths maintaining order
    unique_candidates = []
    for p in candidates:
        if p not in unique_candidates:
            unique_candidates.append(p)
    return unique_candidates


DEFAULT_CACHE_DIR = get_candidate_cache_dirs()[0]
DEFAULT_TTL = timedelta(hours=24)


class FileCache:
    """Manages file-based JSON caching with a specified Time-To-Live (TTL) and memory fallback."""

    def __init__(self, cache_dir: Optional[Union[str, Path]] = None, ttl: timedelta = DEFAULT_TTL):
        self.ttl = ttl
        self._memory_cache: Dict[str, pd.DataFrame] = {}
        self.candidate_dirs = get_candidate_cache_dirs()

        if cache_dir:
            self.cache_dir = Path(cache_dir)
            if self.cache_dir not in self.candidate_dirs:
                self.candidate_dirs.insert(0, self.cache_dir)
        else:
            self.cache_dir = self.candidate_dirs[0]

        self._ensure_cache_dir()

    def _ensure_cache_dir(self):
        """Create cache directory if writable; otherwise fall back to /tmp/reint_cache."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create cache dir {self.cache_dir}: {e}. Falling back to /tmp/reint_cache.")
            fallback = Path("/tmp/reint_cache")
            try:
                fallback.mkdir(parents=True, exist_ok=True)
                self.cache_dir = fallback
            except Exception:
                pass

    def _get_cache_path(self, key: str, base_dir: Optional[Path] = None) -> Path:
        target_dir = base_dir or self.cache_dir
        safe_key = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in key)
        return target_dir / f"{safe_key}.json"

    def get(self, key: str) -> Optional[pd.DataFrame]:
        """Retrieve cached DataFrame if valid across candidate directories or memory."""
        # Check in-memory cache first
        if key in self._memory_cache:
            return self._memory_cache[key].copy()

        # Check candidate directories
        for directory in self.candidate_dirs:
            path = self._get_cache_path(key, base_dir=directory)
            if not path.exists():
                continue

            try:
                with open(path, "r", encoding="utf-8") as f:
                    payload = json.load(f)

                # Reference historical datasets (January 2026) are final and permanent
                is_historical = "202601" in key or "202512" in key
                expires_at_str = payload.get("expires_at")

                if expires_at_str and not is_historical:
                    expires_at = datetime.fromisoformat(expires_at_str)
                    if datetime.now(timezone.utc) >= expires_at:
                        logger.info(f"Cache expired for key '{key}' in {directory}")
                        continue

                records = payload.get("data", [])
                if not records:
                    return pd.DataFrame()

                df = pd.DataFrame(records)
                # Restore UTC timestamps if timestamp columns exist
                for col in ("startTime", "publishTime"):
                    if col in df.columns:
                        df[col] = pd.to_datetime(df[col], utc=True)

                self._memory_cache[key] = df.copy()
                return df
            except Exception as e:
                logger.warning(f"Error reading cache file {path}: {e}")

        return None

    def set(self, key: str, df: pd.DataFrame):
        """Save DataFrame to cache with TTL; fall back gracefully on read-only environments."""
        self._memory_cache[key] = df.copy()

        target_dirs = [self.cache_dir, Path("/tmp/reint_cache")]
        for target_dir in target_dirs:
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                path = self._get_cache_path(key, base_dir=target_dir)
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
                return
            except Exception as e:
                logger.warning(f"Failed to write cache to {target_dir}: {e}")
