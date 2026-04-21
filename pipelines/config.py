from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class ScrapeConfig:
    season: int
    out_dir: Path
    cache_html: bool = True
    resume: bool = True
    force: bool = False
    base_url: str = "https://www.baseball-reference.com"
    request_timeout: float = 30.0
    backoff_initial: float = 1.0
    backoff_max: float = 30.0
    delay_seconds: float = 3.2  # polite default
    max_games: int | None = None  # debug only; leave None for full season
    headers: dict | None = None

    def ensure_dirs(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        if self.cache_html:
            (self.out_dir / "html").mkdir(parents=True, exist_ok=True)


def default_headers() -> dict:
    # Allow user override via env for easier rotation
    ua = os.getenv("SCRAPER_USER_AGENT", DEFAULT_USER_AGENT)
    return {
        "User-Agent": ua,
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "close",
    }
