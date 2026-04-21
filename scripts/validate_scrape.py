"""
Quick validation script for scraped Baseball-Reference data.

Checks:
- Uniqueness and counts of games.
- Lineup completeness (9 starters per team, unique batting_order 1-9).
- Batting coverage (each starter has a batting line).
- Score consistency (sum of runs per side vs recorded game scores).
- Random spot inspection printing a small sample of rows per game.

Usage:
    python scripts/validate_scrape.py --season 2010 --base data/raw --sample 5

Requires: duckdb (pip install duckdb)
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import duckdb


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True, help="Season year, e.g., 2010.")
    parser.add_argument(
        "--base",
        type=Path,
        default=Path("data/raw"),
        help="Base directory containing table/season=YYYY parquet partitions.",
    )
    parser.add_argument("--sample", type=int, default=5, help="Number of random games to print for spot checks.")
    args = parser.parse_args()

    season_part = f"season={args.season}"
    games_glob = str(args.base / "games" / season_part / "*.parquet")
    lineups_glob = str(args.base / "lineups" / season_part / "*.parquet")
    bats_glob = str(args.base / "player_batting_game" / season_part / "*.parquet")
    pitch_glob = str(args.base / "player_pitching_game" / season_part / "*.parquet")

    con = duckdb.connect()

    con.execute("CREATE OR REPLACE TABLE games AS SELECT * FROM read_parquet(?)", [games_glob])
    con.execute("CREATE OR REPLACE TABLE lineups AS SELECT * FROM read_parquet(?)", [lineups_glob])
    con.execute("CREATE OR REPLACE TABLE bats AS SELECT * FROM read_parquet(?)", [bats_glob])
    con.execute("CREATE OR REPLACE TABLE pitch AS SELECT * FROM read_parquet(?)", [pitch_glob])

    print("=== Counts ===")
    print(con.execute("SELECT COUNT(*) AS games FROM games").fetchdf())
    print(con.execute("SELECT COUNT(*) AS lineups FROM lineups").fetchdf())
    print(con.execute("SELECT COUNT(*) AS batting_lines FROM bats").fetchdf())
    print(con.execute("SELECT COUNT(*) AS pitching_lines FROM pitch").fetchdf())

    print("\n=== Game ID uniqueness ===")
    print(
        con.execute(
            "SELECT COUNT(*) AS rows, COUNT(DISTINCT game_id) AS unique_ids FROM games"
        ).fetchdf()
    )

    print("\n=== Lineup completeness (expect 0 bad_games) ===")
    bad_lineups = con.execute(
        """
        WITH agg AS (
          SELECT game_id, is_home, COUNT(*) AS n, COUNT(DISTINCT batting_order) AS u
          FROM lineups
          GROUP BY 1,2
        )
        SELECT COUNT(*) AS bad_games FROM agg WHERE n != 9 OR u != 9
        """
    ).fetchdf()
    print(bad_lineups)

    print("\n=== Missing batting lines for starters (expect 0) ===")
    missing_bats = con.execute(
        """
        SELECT COUNT(*) AS missing
        FROM lineups l
        LEFT JOIN bats b
          ON l.game_id=b.game_id AND l.player_id=b.player_id AND l.is_home=b.is_home
        WHERE b.player_id IS NULL
        """
    ).fetchdf()
    print(missing_bats)

    print("\n=== Score consistency (runs from batting lines vs game scores) ===")
    mismatches = con.execute(
        """
        WITH cleaned AS (
          SELECT game_id, is_home,
                 TRY_CAST(NULLIF(TRIM(R), '') AS INT) AS R_clean
          FROM bats
        ),
        totals AS (
          SELECT game_id,
                 SUM(CASE WHEN is_home THEN COALESCE(R_clean, 0) ELSE 0 END) AS home_runs,
                 SUM(CASE WHEN NOT is_home THEN COALESCE(R_clean, 0) ELSE 0 END) AS away_runs
          FROM cleaned
          GROUP BY 1
        )
        SELECT COUNT(*) AS mismatches
        FROM totals t
        JOIN games g USING(game_id)
        WHERE home_runs != home_score OR away_runs != away_score
        """
    ).fetchdf()
    print(mismatches)

    mismatch_details = con.execute(
        """
        WITH cleaned AS (
          SELECT game_id, is_home,
                 TRY_CAST(NULLIF(TRIM(R), '') AS INT) AS R_clean
          FROM bats
        ),
        totals AS (
          SELECT game_id,
                 SUM(CASE WHEN is_home THEN COALESCE(R_clean, 0) ELSE 0 END) AS home_runs,
                 SUM(CASE WHEN NOT is_home THEN COALESCE(R_clean, 0) ELSE 0 END) AS away_runs
          FROM cleaned
          GROUP BY 1
        )
        SELECT g.game_id,
               g.home_team_id,
               g.away_team_id,
               g.game_date,
               t.home_runs, g.home_score, (t.home_runs - g.home_score) AS home_diff,
               t.away_runs, g.away_score, (t.away_runs - g.away_score) AS away_diff
        FROM totals t
        JOIN games g USING(game_id)
        WHERE home_runs != home_score OR away_runs != away_score
        ORDER BY g.game_date
        """
    ).fetchdf()
    if not mismatch_details.empty:
        print("\nMismatching games (batting-line runs vs recorded scores):")
        print(mismatch_details)

    # Random spot check
    ids = con.execute("SELECT game_id FROM games").fetchdf()["game_id"].tolist()
    sample_n = min(args.sample, len(ids))
    sample_ids = random.sample(ids, sample_n) if sample_n else []

    print(f"\n=== Spot check {sample_n} games ===")
    for gid in sample_ids:
        print(f"\nGame {gid}")
        print(con.execute("SELECT * FROM games WHERE game_id = ?", [gid]).fetchdf())
        print(con.execute("SELECT * FROM lineups WHERE game_id = ? ORDER BY is_home, batting_order", [gid]).fetchdf())
        print(
            con.execute(
                "SELECT player_id, is_home, AB, R, H, RBI, BB, SO, PA "
                "FROM bats WHERE game_id = ? ORDER BY is_home, batting_order NULLS LAST",
                [gid],
            ).fetchdf()
        )
        print(
            con.execute(
                "SELECT player_id, is_home, IP, R, ER, H, BB, SO FROM pitch WHERE game_id = ? ORDER BY is_home",
                [gid],
            ).fetchdf()
        )


if __name__ == "__main__":
    main()
