from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from .config import ScrapeConfig, default_headers


def _build_session(cfg: ScrapeConfig) -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=7,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(default_headers() if cfg.headers is None else cfg.headers)
    return session


class Fetcher:
    def __init__(self, cfg: ScrapeConfig) -> None:
        self.cfg = cfg
        self.session = _build_session(cfg)

    def fetch(self, url: str, cache_path: Optional[Path] = None) -> str:
        if cache_path and cache_path.exists() and self.cfg.cache_html and self.cfg.resume:
            return cache_path.read_text(encoding="utf-8")

        resp = self.session.get(url, timeout=self.cfg.request_timeout)
        resp.raise_for_status()
        if cache_path and self.cfg.cache_html:
            cache_path.write_text(resp.text, encoding="utf-8")
        # polite delay
        time.sleep(self.cfg.delay_seconds)
        return resp.text

    @staticmethod
    def checksum(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
