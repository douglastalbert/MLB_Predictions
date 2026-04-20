from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

import pandas as pd

from .config import ScrapeConfig
from .fetch import Fetcher
from .parse_boxscore import parse_boxscore
from .schedule import ScheduledGame, parse_schedule_html


def fetch_schedule(cfg: ScrapeConfig, fetcher: Fetcher) -> List[ScheduledGame]:
    url = f"{cfg.base_url}/leagues/MLB/{cfg.season}-schedule.shtml"
    html = fetcher.fetch(url)
    return parse_schedule_html(html, base_url=cfg.base_url)


def write_parquet(rows: List[dict], path: Path) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_parquet(path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Baseball-Reference boxscores into Parquet tables.")
    parser.add_argument("--season", type=int, required=True, help="Season year, e.g., 2010.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/raw"),
        help="Output base directory (raw tables will be nested by table/season).",
    )
    parser.add_argument("--cache-html", action="store_true", default=True, help="Cache raw HTML to disk.")
    parser.add_argument("--no-cache-html", dest="cache_html", action="store_false")
    parser.add_argument("--resume", action="store_true", default=True, help="Skip already-downloaded games.")
    parser.add_argument("--force", action="store_true", help="Re-download and overwrite cached HTML.")
    args = parser.parse_args()

    cfg = ScrapeConfig(
        season=args.season,
        out_dir=args.out,
        cache_html=args.cache_html,
        resume=args.resume,
        force=args.force,
    )
    cfg.ensure_dirs()
    fetcher = Fetcher(cfg)

    schedule = fetch_schedule(cfg, fetcher)
    print(f"Found {len(schedule)} games in {cfg.season} schedule")

    games_rows = []
    lineup_rows = []
    bat_rows = []
    pitch_rows = []

    for i, game in enumerate(schedule, start=1):
        if cfg.max_games and i > cfg.max_games:
            break
        cache_path = cfg.out_dir / "html" / f"{game.game_id}.html"
        try:
            if cache_path.exists() and cfg.resume and not cfg.force:
                html = cache_path.read_text(encoding="utf-8")
            else:
                html = fetcher.fetch(game.boxscore_url, cache_path=cache_path)
        except Exception as exc:  # noqa: BLE001
            err_dir = cfg.out_dir / "errors"
            err_dir.mkdir(parents=True, exist_ok=True)
            (err_dir / f"{game.game_id}_fetch.txt").write_text(
                f"{game.boxscore_url}\n{type(exc).__name__}: {exc}"
            )
            continue

        try:
            parsed = parse_boxscore(html)
        except Exception as exc:  # noqa: BLE001
            err_dir = cfg.out_dir / "errors"
            err_dir.mkdir(parents=True, exist_ok=True)
            (err_dir / f"{game.game_id}_parse.txt").write_text(str(exc))
            continue

        games_rows.append(parsed.game)
        lineup_rows.extend(parsed.lineups)
        bat_rows.extend(parsed.batting_lines)
        pitch_rows.extend(parsed.pitching_lines)

        if i % 100 == 0:
            print(f"Processed {i} games")

    season_partition = f"season={cfg.season}"
    write_parquet(games_rows, cfg.out_dir / "games" / season_partition / "part-0.parquet")
    write_parquet(lineup_rows, cfg.out_dir / "lineups" / season_partition / "part-0.parquet")
    write_parquet(bat_rows, cfg.out_dir / "player_batting_game" / season_partition / "part-0.parquet")
    write_parquet(pitch_rows, cfg.out_dir / "player_pitching_game" / season_partition / "part-0.parquet")

    summary = {
        "games": len(games_rows),
        "lineups": len(lineup_rows),
        "batting_lines": len(bat_rows),
        "pitching_lines": len(pitch_rows),
    }
    (cfg.out_dir / f"summary_{cfg.season}.json").write_text(json.dumps(summary, indent=2))
    print("Done", summary)


if __name__ == "__main__":
    main()
