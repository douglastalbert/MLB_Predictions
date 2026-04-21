"""
Backfill and validate MLB raw data by season.

Design:
- Scraping is serial (safe for source rate limits).
- Validation runs in parallel workers (local + MLB API checks).
- Outputs/logs are partitioned by season for auditing.

Example:
    python scripts/backfill_and_validate.py \
      --start-season 2005 --end-season 2025 \
      --out data/raw \
      --reports-dir data/reports/backfill \
      --validation-workers 4 \
      --score-sample 0 --player-sample 50 --pitcher-sample 50 --lineup-sample 50
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def run_command(cmd: List[str], log_path: Path) -> Tuple[int, float]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    with log_path.open("w", encoding="utf-8") as handle:
        handle.write(f"$ {' '.join(cmd)}\n\n")
        handle.flush()
        proc = subprocess.run(cmd, stdout=handle, stderr=subprocess.STDOUT, text=True)
    return proc.returncode, round(time.time() - start, 2)


def write_manifest(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def validate_season(
    season: int,
    out_dir: Path,
    reports_dir: Path,
    python_exe: str,
    external_seed: int,
    score_sample: int,
    player_sample: int,
    pitcher_sample: int,
    lineup_sample: int,
) -> Dict:
    season_dir = reports_dir / f"season={season}"
    internal_log = season_dir / "validate_internal.log"
    external_log = season_dir / "validate_external.log"

    internal_cmd = [
        python_exe,
        "scripts/validate_scrape.py",
        "--season",
        str(season),
        "--base",
        str(out_dir),
        "--sample",
        "0",
        "--fail-on-issues",
    ]
    external_cmd = [
        python_exe,
        "scripts/validate_external.py",
        "--season",
        str(season),
        "--base",
        str(out_dir),
        "--score-sample",
        str(score_sample),
        "--player-sample",
        str(player_sample),
        "--pitcher-sample",
        str(pitcher_sample),
        "--lineup-sample",
        str(lineup_sample),
        "--seed",
        str(external_seed),
        "--fail-on-issues",
    ]

    internal_rc, internal_sec = run_command(internal_cmd, internal_log)
    external_rc, external_sec = run_command(external_cmd, external_log)

    return {
        "internal": {"status": "passed" if internal_rc == 0 else "failed", "return_code": internal_rc, "seconds": internal_sec},
        "external": {"status": "passed" if external_rc == 0 else "failed", "return_code": external_rc, "seconds": external_sec},
        "status": "passed" if internal_rc == 0 and external_rc == 0 else "failed",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill and validate MLB seasons with safe scrape + parallel validation.")
    parser.add_argument("--start-season", type=int, default=2005)
    parser.add_argument("--end-season", type=int, default=2025)
    parser.add_argument("--out", type=Path, default=Path("data/raw"))
    parser.add_argument("--reports-dir", type=Path, default=Path("data/reports/backfill"))
    parser.add_argument("--delay-seconds", type=float, default=3.2, help="Polite scrape delay between requests.")
    parser.add_argument("--validation-workers", type=int, default=4, help="Parallel validation worker count.")
    parser.add_argument("--score-sample", type=int, default=0, help="External score validation sample size (0 = full season).")
    parser.add_argument("--player-sample", type=int, default=50)
    parser.add_argument("--pitcher-sample", type=int, default=50)
    parser.add_argument("--lineup-sample", type=int, default=50)
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional base seed for reproducible multi-season validation sampling.",
    )
    parser.add_argument("--force-scrape", action="store_true", help="Force re-download/reparse for each season.")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Skip scraping and run validators only for each season.",
    )
    parser.add_argument("--max-games", type=int, default=None, help="Debug limiter; omit for full season.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.start_season > args.end_season:
        raise SystemExit("--start-season must be <= --end-season")

    seasons = list(range(args.start_season, args.end_season + 1))
    python_exe = sys.executable
    manifest_path = args.reports_dir / "manifest.json"
    if args.seed is None:
        run_seed = random.SystemRandom().randrange(0, 2**32)
        seed_source = "generated"
    else:
        run_seed = args.seed
        seed_source = "provided"
    print(f"Validation base seed={run_seed} ({seed_source})")

    manifest = {
        "started_at": now_iso(),
        "config": {
            "start_season": args.start_season,
            "end_season": args.end_season,
            "out": str(args.out),
            "reports_dir": str(args.reports_dir),
            "delay_seconds": args.delay_seconds,
            "validation_workers": args.validation_workers,
            "score_sample": args.score_sample,
            "player_sample": args.player_sample,
            "pitcher_sample": args.pitcher_sample,
            "lineup_sample": args.lineup_sample,
            "seed": args.seed,
            "seed_source": seed_source,
            "run_seed": run_seed,
            "force_scrape": args.force_scrape,
            "max_games": args.max_games,
        },
        "seasons": {},
    }
    write_manifest(manifest_path, manifest)

    futures: Dict[Future, int] = {}
    with ThreadPoolExecutor(max_workers=max(1, args.validation_workers)) as executor:
        for season in seasons:
            season_key = str(season)
            season_seed = (run_seed + season) % (2**32)
            season_dir = args.reports_dir / f"season={season}"
            season_dir.mkdir(parents=True, exist_ok=True)
            scrape_log = season_dir / "scrape.log"

            manifest["seasons"][season_key] = {
                "scrape": {"status": "running", "started_at": now_iso()},
                "validation": {"status": "pending"},
            }
            write_manifest(manifest_path, manifest)

            if args.validate_only:
                rc, seconds = 0, 0.0
                manifest["seasons"][season_key]["scrape"] = {
                    "status": "skipped_validate_only",
                    "return_code": 0,
                    "seconds": seconds,
                    "finished_at": now_iso(),
                }
            else:
                scrape_cmd = [
                    python_exe,
                    "-m",
                    "pipelines.scrape_boxscores",
                    "--season",
                    str(season),
                    "--out",
                    str(args.out),
                    "--cache-html",
                    "--resume",
                    "--delay-seconds",
                    str(args.delay_seconds),
                ]
                if args.force_scrape:
                    scrape_cmd.append("--force")
                if args.max_games is not None:
                    scrape_cmd.extend(["--max-games", str(args.max_games)])

                rc, seconds = run_command(scrape_cmd, scrape_log)
                manifest["seasons"][season_key]["scrape"] = {
                    "status": "passed" if rc == 0 else "failed",
                    "return_code": rc,
                    "seconds": seconds,
                    "finished_at": now_iso(),
                }

            if rc == 0:
                manifest["seasons"][season_key]["validation"] = {"status": "queued", "external_seed": season_seed}
                future = executor.submit(
                    validate_season,
                    season,
                    args.out,
                    args.reports_dir,
                    python_exe,
                    season_seed,
                    args.score_sample,
                    args.player_sample,
                    args.pitcher_sample,
                    args.lineup_sample,
                )
                futures[future] = season
            else:
                manifest["seasons"][season_key]["validation"] = {"status": "skipped_due_to_scrape_failure"}
            write_manifest(manifest_path, manifest)
            if args.validate_only:
                print(f"[{season}] scrape skipped (validate-only, validation seed={season_seed})")
            else:
                print(f"[{season}] scrape {'passed' if rc == 0 else 'failed'} ({seconds}s, validation seed={season_seed})")

        for future in as_completed(futures):
            season = futures[future]
            season_key = str(season)
            existing_seed = manifest["seasons"][season_key]["validation"].get("external_seed")
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                manifest["seasons"][season_key]["validation"] = {
                    "status": "failed",
                    "error": str(exc),
                    "external_seed": existing_seed,
                }
                print(f"[{season}] validation failed with exception (seed={existing_seed})")
            else:
                result["external_seed"] = existing_seed
                manifest["seasons"][season_key]["validation"] = result
                print(f"[{season}] validation {result['status']} (seed={existing_seed})")
            write_manifest(manifest_path, manifest)

    failed = []
    for season in seasons:
        season_key = str(season)
        scrape_status = manifest["seasons"][season_key]["scrape"]["status"]
        validation_status = manifest["seasons"][season_key]["validation"]["status"]
        scrape_ok = scrape_status in {"passed", "skipped_validate_only"}
        if not scrape_ok or validation_status != "passed":
            failed.append(season)

    manifest["finished_at"] = now_iso()
    manifest["overall_status"] = "passed" if not failed else "failed"
    manifest["failed_seasons"] = failed
    write_manifest(manifest_path, manifest)

    if failed:
        print(f"Backfill completed with failures in seasons: {failed}")
        raise SystemExit(1)
    print("Backfill completed successfully for all seasons.")


if __name__ == "__main__":
    main()
