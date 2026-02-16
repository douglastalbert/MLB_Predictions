# MLB_Predictions

Goal: Build an end-to-end system that outputs pre-game win probabilities for MLB matchups using only information that was available before first pitch.

Initial modeling vision (v0)
- Inputs per game (all computed as-of the game start, no future leakage):
  - Home team cumulative season-to-date pitching stats (through previous game).
  - Away team cumulative season-to-date pitching stats.
  - Home starting lineup: batting order preserved, each hitter’s season-to-date stats and career stats.
  - Away starting lineup: batting order preserved, each hitter’s season-to-date stats and career stats.
  - Home starting pitcher: season-to-date stats and career stats.
  - Away starting pitcher: season-to-date stats and career stats.
- Output: a single win-probability for home/away.
- Feature engineering: minimal—use raw season/career aggregates; defer matchup/weather/market/umpire features to later iterations if accuracy is insufficient.

Guiding principles
- Reproducible pipelines: code-first (versioned), deterministic data builds, environment pinning.
- Honest evaluation: out-of-sample splits by date, leakage checks, baseline comparisons.
- Modularity: separable layers for scrape → clean → feature store → model → serve.
- Observability: log/monitor scraping, data freshness, model drift, and calibration.

Roadmap
0) Foundations (repo hygiene)
   - Add `.python-version`/`requirements.txt` or `uv`/`poetry` lock; pre-commit with isort/black/ruff; `.env.example` with API keys and rate limits.
   - Set up `data/` layout: `raw/`, `staged/`, `features/`, `models/`, `reports/` (git-ignored except small samples).

1) Data acquisition
   - Sources (v0): Baseball-Reference box scores and play-by-play for historical games; roster/lineup data to capture starting hitters and pitchers with batting order; season-to-date and career aggregates per player and team pitching.
   - Scrapers as idempotent CLI jobs (no notebooks): retry w/ backoff, polite rate limiting, caching (requests-cache), checksum-based dedup; store raw HTML/JSON snapshots for audit.
   - Normalize output to columnar files (Parquet) stored per table/date/season partition.

2) Data modeling & storage
   - Core tables needed for v0: `games` (metadata, start time), `lineups` (ordered hitters with positions), `team_pitch_season` (cumulative to date), `player_bat_season`, `player_bat_career`, `player_pitch_season`, `player_pitch_career`.
   - Use DuckDB for local analytics; optional Postgres for multi-user; catalog schemas with dbt/SQLMesh for transforms.
   - Build a daily ingestion DAG (Airflow/Prefect/cron) that appends new games and recomputes season-to-date aggregates only up to each game’s timestamp.

3) Feature engineering
   - Minimal transforms: ensure all aggregates are as-of (exclude current game), standardize rate stats (PA/IP denominators), and encode batting order.
   - Materialize features into a feature store keyed by game_id/team_id/player_id with as-of timestamps to avoid leakage.

4) Modeling
   - Start simple: logistic regression / gradient-boosted trees on the as-of aggregates; compare to coin-flip and home-field priors.
   - Use time-based CV (e.g., walk-forward) and monitor calibration (reliability curves, Brier/log-loss).

5) Evaluation & backtesting
   - Time-split backtests; walk-forward validation; ensure no future info leakage via as-of joins.
   - Metrics: log-loss/Brier, ROC/AUC (diagnostic), calibration curves, profit vs. closing line, CLV (closing line value), over/under RMSE.
   - Reporting: auto-generate Markdown/HTML reports with plots; store in `reports/` per run.

6) Serving & automation
   - CLI to score upcoming games (ingests today’s data, outputs probabilities/edges); optionally deploy a FastAPI service.
   - Scheduling: nightly data refresh and morning model score job; alert on scrape failures, missing odds, stale features, or drift.
   - Model registry: save artifacts (models, calibrators, config) with signatures; reproducible runs via MLflow/Weights & Biases (or lightweight YAML + hashes if staying local).

7) Governance & safety
   - Track data licenses/robots.txt; respect rate limits; document provenance.
   - Include unit tests for parsers, schema validation (pydantic/great_expectations), and regression tests on feature outputs.

Current notebook output (scraping.ipynb) — viability & improvements
- What it produces: lists of per-game dictionaries (`game`, team box totals, pitcher/hitter rows) saved via pickle (`game_data_2015.pkl`, `game_data_2016.pkl`). Useful for ad-hoc analysis but fragile for production.
- Issues: pickle is Python-only and unsafe/unversioned; schema not enforced; strings for dates/numbers; nested dicts hinder querying; no incremental/partitioned storage; scrape logic intermingled with notebook state; lineup order not explicit; career vs. season aggregates not separated; later seasons missing.
- Improvements (short term): refactor scraper into a module/CLI (`python -m pipelines.scrape_boxscores --season 2015 --out data/raw/boxscores/season=2015/part-*.parquet`); normalize to tables required for v0 (games, lineups with batting order, player season/career batting and pitching, team season pitching) with typed columns; write Parquet + schema metadata; add retry/backoff and request headers; persist raw HTML for audit.
- Improvements (next): build as-of aggregate transforms in dbt/duckdb; add validations (row counts per season, null checks, unique game_id); log scrape run metadata (started/ended, failures, skipped); add guardrails that forbid using stats dated after the game start; expand to newer seasons; keep future features (weather, market odds, context) as optional add-ons once v0 accuracy plateaus.

Next step to tackle: convert the notebook scraping code into a reproducible CLI that outputs partitioned Parquet tables for 2015–present, then build validation checks and a small exploratory backtest baseline.
