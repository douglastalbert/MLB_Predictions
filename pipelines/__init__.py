"""
Pipelines package for scraping and normalizing MLB boxscore data from Baseball-Reference.

Modules:
- schedule: fetch and parse season schedules to obtain boxscore URLs.
- fetch: HTTP helpers with retry/backoff and optional HTML caching.
- parse_boxscore: extract tidy tables from a boxscore HTML document.
- scrape_boxscores: CLI entrypoint orchestrating schedule fetch, download, parse, and write.
"""

__all__ = ["schedule", "fetch", "parse_boxscore"]
