"""
Cross-validate scraped Baseball-Reference outputs against MLB Stats API.

Checks:
1) Final score validation against MLB Stats API schedule data.
2) Random player batting statline validation against MLB Stats API boxscore data.
3) Random pitcher statline validation against MLB Stats API boxscore data.
4) Random lineup-slot validation against MLB Stats API boxscore data.

Usage:
    python scripts/validate_external.py --season 2010 --base data/raw
    python scripts/validate_external.py --season 2010 --base data/raw --score-sample 200 --player-sample 30

Requirements:
    pip install duckdb requests beautifulsoup4
"""

from __future__ import annotations

import argparse
import random
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import duckdb
import requests
from bs4 import BeautifulSoup


# Supports both legacy BRef codes and modern MLB codes seen in parsed tables.
TEAM_ID_BY_CODE = {
    "ANA": 108,
    "LAA": 108,
    "ARI": 109,
    "ATL": 144,
    "BAL": 110,
    "BOS": 111,
    "CHA": 145,
    "CHW": 145,
    "CWS": 145,
    "CHN": 112,
    "CHC": 112,
    "CIN": 113,
    "CLE": 114,
    "COL": 115,
    "DET": 116,
    "FLO": 146,
    "FLA": 146,
    "MIA": 146,
    "HOU": 117,
    "KCA": 118,
    "KCR": 118,
    "KC": 118,
    "LAN": 119,
    "LAD": 119,
    "MIL": 158,
    "MIN": 142,
    "NYA": 147,
    "NYY": 147,
    "NYN": 121,
    "NYM": 121,
    "OAK": 133,
    "PHI": 143,
    "PIT": 134,
    "SDN": 135,
    "SDP": 135,
    "SD": 135,
    "SEA": 136,
    "SFN": 137,
    "SFG": 137,
    "SF": 137,
    "SLN": 138,
    "STL": 138,
    "TBA": 139,
    "TBR": 139,
    "TB": 139,
    "TEX": 140,
    "TOR": 141,
    "WAS": 120,
    "WSN": 120,
    "WSH": 120,
}


@dataclass
class GameRow:
    game_id: str
    game_date: str
    home_team_id: str
    away_team_id: str
    home_score: int
    away_score: int


@dataclass
class BatRow:
    game_id: str
    player_id: str
    team_id: str
    is_home: bool
    ab: int
    r: int
    h: int
    rbi: int
    bb: int
    so: int


@dataclass
class PitchRow:
    game_id: str
    player_id: str
    team_id: str
    is_home: bool
    ip: str
    r: int
    er: int
    h: int
    bb: int
    so: int


@dataclass
class LineupRow:
    game_id: str
    player_id: str
    team_id: str
    is_home: bool
    batting_order: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True, help="Season year, e.g., 2010.")
    parser.add_argument("--base", type=Path, default=Path("data/raw"), help="Base raw data directory.")
    parser.add_argument(
        "--score-sample",
        type=int,
        default=0,
        help="Number of games to score-validate (0 = all games).",
    )
    parser.add_argument(
        "--player-sample",
        type=int,
        default=25,
        help="Number of random player statlines to validate.",
    )
    parser.add_argument(
        "--pitcher-sample",
        type=int,
        default=25,
        help="Number of random pitcher statlines to validate.",
    )
    parser.add_argument(
        "--lineup-sample",
        type=int,
        default=25,
        help="Number of random lineup slots to validate.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout seconds.")
    return parser.parse_args()


def parse_game_date_to_iso(game_date: str) -> str:
    # Example: "Thursday, July 1, 2010"
    return datetime.strptime(game_date, "%A, %B %d, %Y").date().isoformat()


def mlb_team_id_from_code(team_code: str) -> Optional[int]:
    return TEAM_ID_BY_CODE.get(team_code)


def normalize_name(name: str) -> str:
    # Repair common mojibake from mis-decoded UTF-8 names (e.g., "HÃ©ctor").
    if any(ch in name for ch in ("Ã", "Â", "â")):
        try:
            name = name.encode("latin-1").decode("utf-8")
        except UnicodeError:
            pass

    # Strip accents/diacritics so "Hector" and "Hector" with accents normalize identically.
    name = unicodedata.normalize("NFKD", name)
    name = "".join(ch for ch in name if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", name.lower())


def load_games(base: Path, season: int) -> List[GameRow]:
    con = duckdb.connect()
    games_glob = str(base / "games" / f"season={season}" / "*.parquet")
    rows = con.execute(
        """
        SELECT game_id, game_date, home_team_id, away_team_id,
               CAST(home_score AS INT) AS home_score,
               CAST(away_score AS INT) AS away_score
        FROM read_parquet(?)
        ORDER BY game_id
        """,
        [games_glob],
    ).fetchall()
    return [GameRow(*row) for row in rows]


def load_batting_rows(base: Path, season: int) -> List[BatRow]:
    con = duckdb.connect()
    bats_glob = str(base / "player_batting_game" / f"season={season}" / "*.parquet")
    rows = con.execute(
        """
        SELECT game_id, player_id, team_id, is_home,
               COALESCE(TRY_CAST(NULLIF(TRIM(CAST(AB AS VARCHAR)), '') AS INT), 0) AS ab,
               COALESCE(TRY_CAST(NULLIF(TRIM(CAST(R AS VARCHAR)), '') AS INT), 0) AS r,
               COALESCE(TRY_CAST(NULLIF(TRIM(CAST(H AS VARCHAR)), '') AS INT), 0) AS h,
               COALESCE(TRY_CAST(NULLIF(TRIM(CAST(RBI AS VARCHAR)), '') AS INT), 0) AS rbi,
               COALESCE(TRY_CAST(NULLIF(TRIM(CAST(BB AS VARCHAR)), '') AS INT), 0) AS bb,
               COALESCE(TRY_CAST(NULLIF(TRIM(CAST(SO AS VARCHAR)), '') AS INT), 0) AS so
        FROM read_parquet(?)
        WHERE COALESCE(NULLIF(TRIM(CAST(AB AS VARCHAR)), ''), '') != ''
        """,
        [bats_glob],
    ).fetchall()
    return [BatRow(*row) for row in rows]


def load_pitching_rows(base: Path, season: int) -> List[PitchRow]:
    con = duckdb.connect()
    pitch_glob = str(base / "player_pitching_game" / f"season={season}" / "*.parquet")
    rows = con.execute(
        """
        SELECT game_id, player_id, team_id, is_home,
               CAST(IP AS VARCHAR) AS ip,
               COALESCE(TRY_CAST(NULLIF(TRIM(CAST(R AS VARCHAR)), '') AS INT), 0) AS r,
               COALESCE(TRY_CAST(NULLIF(TRIM(CAST(ER AS VARCHAR)), '') AS INT), 0) AS er,
               COALESCE(TRY_CAST(NULLIF(TRIM(CAST(H AS VARCHAR)), '') AS INT), 0) AS h,
               COALESCE(TRY_CAST(NULLIF(TRIM(CAST(BB AS VARCHAR)), '') AS INT), 0) AS bb,
               COALESCE(TRY_CAST(NULLIF(TRIM(CAST(SO AS VARCHAR)), '') AS INT), 0) AS so
        FROM read_parquet(?)
        WHERE COALESCE(NULLIF(TRIM(CAST(IP AS VARCHAR)), ''), '') != ''
        """,
        [pitch_glob],
    ).fetchall()
    return [PitchRow(*row) for row in rows]


def load_lineup_rows(base: Path, season: int) -> List[LineupRow]:
    con = duckdb.connect()
    lineup_glob = str(base / "lineups" / f"season={season}" / "*.parquet")
    rows = con.execute(
        """
        SELECT game_id, player_id, team_id, is_home, CAST(batting_order AS INT) AS batting_order
        FROM read_parquet(?)
        """,
        [lineup_glob],
    ).fetchall()
    return [LineupRow(*row) for row in rows]


class MlbApi:
    def __init__(self, timeout: float) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "MLB_Predictions validator/1.0"})
        self.schedule_cache: Dict[str, List[dict]] = {}
        self.boxscore_cache: Dict[int, dict] = {}

    def schedule_for_date(self, date_iso: str) -> List[dict]:
        if date_iso in self.schedule_cache:
            return self.schedule_cache[date_iso]
        resp = self.session.get(
            "https://statsapi.mlb.com/api/v1/schedule",
            params={"sportId": 1, "date": date_iso},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        dates = payload.get("dates", [])
        games = dates[0].get("games", []) if dates else []
        self.schedule_cache[date_iso] = games
        return games

    def boxscore(self, game_pk: int) -> dict:
        if game_pk in self.boxscore_cache:
            return self.boxscore_cache[game_pk]
        resp = self.session.get(
            f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore",
            timeout=self.timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        self.boxscore_cache[game_pk] = payload
        return payload


def find_mlb_game(
    api: MlbApi,
    game: GameRow,
) -> Tuple[Optional[dict], str]:
    date_iso = parse_game_date_to_iso(game.game_date)
    games = api.schedule_for_date(date_iso)

    home_team_id = mlb_team_id_from_code(game.home_team_id)
    away_team_id = mlb_team_id_from_code(game.away_team_id)
    if home_team_id is None or away_team_id is None:
        return None, "unknown_team_code"

    candidates = []
    for candidate in games:
        c_home = candidate.get("teams", {}).get("home", {}).get("team", {}).get("id")
        c_away = candidate.get("teams", {}).get("away", {}).get("team", {}).get("id")
        if c_home == home_team_id and c_away == away_team_id:
            candidates.append(candidate)

    if not candidates:
        # Fallback for games played at alternate parks where "home" in one source may differ.
        reverse_candidates = []
        for candidate in games:
            c_home = candidate.get("teams", {}).get("home", {}).get("team", {}).get("id")
            c_away = candidate.get("teams", {}).get("away", {}).get("team", {}).get("id")
            if c_home == away_team_id and c_away == home_team_id:
                reverse_candidates.append(candidate)
        if not reverse_candidates:
            return None, "no_team_match"
        if len(reverse_candidates) == 1:
            return reverse_candidates[0], "reverse_home_away"
        reverse_score_match = [
            c
            for c in reverse_candidates
            if c.get("teams", {}).get("home", {}).get("score") == game.away_score
            and c.get("teams", {}).get("away", {}).get("score") == game.home_score
        ]
        if len(reverse_score_match) == 1:
            return reverse_score_match[0], "reverse_score_disambiguated"
        return reverse_candidates[0], "reverse_ambiguous_first"
    if len(candidates) == 1:
        return candidates[0], "exact"

    # For doubleheaders / duplicates on same day, first attempt score-based disambiguation.
    score_match = [
        c
        for c in candidates
        if c.get("teams", {}).get("home", {}).get("score") == game.home_score
        and c.get("teams", {}).get("away", {}).get("score") == game.away_score
    ]
    if len(score_match) == 1:
        return score_match[0], "score_disambiguated"
    return candidates[0], "ambiguous_first"


def extract_player_name_map_from_cached_html(base: Path, game_id: str) -> Dict[str, str]:
    html_path = base / "html" / f"{game_id}.html"
    if not html_path.exists():
        return {}
    html = html_path.read_text(encoding="utf-8")
    html = html.replace("<!--", "").replace("-->", "")
    soup = BeautifulSoup(html, "html.parser")
    mapping: Dict[str, str] = {}
    for th in soup.find_all("th", {"data-stat": "player"}):
        a = th.find("a")
        if a is None:
            continue
        href = a.get("href", "")
        if "/players/" not in href:
            continue
        player_id = href.split("/")[-1].replace(".shtml", "")
        player_name = a.get_text(strip=True)
        mapping[player_id] = player_name
    return mapping


def mlb_boxscore_players_by_side(boxscore: dict, is_home: bool) -> List[dict]:
    side = "home" if is_home else "away"
    players = boxscore.get("teams", {}).get(side, {}).get("players", {})
    return list(players.values())


def batting_stats_from_mlb_player(player: dict) -> Dict[str, int]:
    batting = player.get("stats", {}).get("batting", {})
    return {
        "AB": int(batting.get("atBats", 0) or 0),
        "R": int(batting.get("runs", 0) or 0),
        "H": int(batting.get("hits", 0) or 0),
        "RBI": int(batting.get("rbi", 0) or 0),
        "BB": int(batting.get("baseOnBalls", 0) or 0),
        "SO": int(batting.get("strikeOuts", 0) or 0),
    }


def batting_stats_from_local(row: BatRow) -> Dict[str, int]:
    return {"AB": row.ab, "R": row.r, "H": row.h, "RBI": row.rbi, "BB": row.bb, "SO": row.so}


def innings_to_outs(value: str) -> Optional[int]:
    raw = (value or "").strip()
    if not raw:
        return None
    if "." not in raw:
        return int(raw) * 3 if raw.isdigit() else None
    whole, frac = raw.split(".", 1)
    if not whole.isdigit() or not frac.isdigit():
        return None
    frac_int = int(frac)
    if frac_int not in (0, 1, 2):
        return None
    return int(whole) * 3 + frac_int


def pitching_stats_from_local(row: PitchRow) -> Dict[str, int]:
    outs = innings_to_outs(row.ip)
    return {
        "IP_OUTS": 0 if outs is None else outs,
        "R": row.r,
        "ER": row.er,
        "H": row.h,
        "BB": row.bb,
        "SO": row.so,
    }


def pitching_stats_from_mlb_player(player: dict) -> Dict[str, int]:
    pitching = player.get("stats", {}).get("pitching", {})
    outs = innings_to_outs(str(pitching.get("inningsPitched", "") or ""))
    return {
        "IP_OUTS": 0 if outs is None else outs,
        "R": int(pitching.get("runs", 0) or 0),
        "ER": int(pitching.get("earnedRuns", 0) or 0),
        "H": int(pitching.get("hits", 0) or 0),
        "BB": int(pitching.get("baseOnBalls", 0) or 0),
        "SO": int(pitching.get("strikeOuts", 0) or 0),
    }


def starting_lineup_by_order(boxscore: dict, is_home: bool) -> Dict[int, dict]:
    side_players = mlb_boxscore_players_by_side(boxscore, is_home)
    # MLB uses battingOrder like "100", "201", etc. Starter in each slot has the lowest suffix.
    starters: Dict[int, Tuple[int, dict]] = {}
    for player in side_players:
        batting_order = player.get("battingOrder")
        if batting_order is None:
            continue
        text = str(batting_order).strip()
        if not text.isdigit():
            continue
        order_int = int(text)
        slot = order_int // 100
        seq = order_int % 100
        if slot < 1 or slot > 9:
            continue
        existing = starters.get(slot)
        if existing is None or seq < existing[0]:
            starters[slot] = (seq, player)
    return {slot: pair[1] for slot, pair in starters.items()}


def run_score_validation(
    api: MlbApi,
    games: List[GameRow],
    score_sample: int,
    rng: random.Random,
) -> None:
    pool = games if score_sample <= 0 else rng.sample(games, min(score_sample, len(games)))
    checked = 0
    mismatches: List[dict] = []
    unresolved: List[dict] = []

    for game in pool:
        try:
            candidate, mode = find_mlb_game(api, game)
        except Exception as exc:  # noqa: BLE001
            unresolved.append({"game_id": game.game_id, "reason": f"schedule_error: {exc}"})
            continue
        if candidate is None:
            unresolved.append({"game_id": game.game_id, "reason": mode})
            continue

        checked += 1
        mlb_home = candidate.get("teams", {}).get("home", {}).get("score")
        mlb_away = candidate.get("teams", {}).get("away", {}).get("score")
        # Some games are reversed home/away in alternate-venue metadata; allow flipped comparison
        # only when the match mode indicates reversed orientation.
        if mode.startswith("reverse_"):
            local_home, local_away = game.away_score, game.home_score
        else:
            local_home, local_away = game.home_score, game.away_score

        if mlb_home != local_home or mlb_away != local_away:
            mismatches.append(
                {
                    "game_id": game.game_id,
                    "mode": mode,
                    "local_home": local_home,
                    "mlb_home": mlb_home,
                    "local_away": local_away,
                    "mlb_away": mlb_away,
                }
            )

    print("=== External Score Validation (MLB Stats API) ===")
    print(f"checked={checked} unresolved={len(unresolved)} mismatches={len(mismatches)}")
    if unresolved:
        print("Unresolved sample:")
        for item in unresolved[:10]:
            print(item)
    if mismatches:
        print("Mismatch sample:")
        for item in mismatches[:10]:
            print(item)


def choose_best_name_match(candidates: List[dict], local_stats: Dict[str, int]) -> Optional[dict]:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    best = None
    best_score = -1
    for cand in candidates:
        mlb_stats = batting_stats_from_mlb_player(cand)
        score = sum(1 for k in local_stats if mlb_stats.get(k) == local_stats.get(k))
        if score > best_score:
            best = cand
            best_score = score
    return best


def choose_best_pitcher_match(candidates: List[dict], local_stats: Dict[str, int]) -> Optional[dict]:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    best = None
    best_score = -1
    for cand in candidates:
        mlb_stats = pitching_stats_from_mlb_player(cand)
        score = sum(1 for k in local_stats if mlb_stats.get(k) == local_stats.get(k))
        if score > best_score:
            best = cand
            best_score = score
    return best


def run_player_validation(
    api: MlbApi,
    games_by_id: Dict[str, GameRow],
    bats: List[BatRow],
    base: Path,
    player_sample: int,
    rng: random.Random,
) -> None:
    if not bats:
        print("\n=== External Player Statline Validation ===")
        print("No batting rows available.")
        return

    sample_rows = rng.sample(bats, min(player_sample, len(bats)))
    checked = 0
    mismatches: List[dict] = []
    unresolved: List[dict] = []
    name_map_cache: Dict[str, Dict[str, str]] = {}

    for row in sample_rows:
        game = games_by_id.get(row.game_id)
        if game is None:
            unresolved.append({"game_id": row.game_id, "player_id": row.player_id, "reason": "missing_game"})
            continue

        try:
            candidate, mode = find_mlb_game(api, game)
        except Exception as exc:  # noqa: BLE001
            unresolved.append({"game_id": row.game_id, "player_id": row.player_id, "reason": f"schedule_error: {exc}"})
            continue
        if candidate is None:
            unresolved.append({"game_id": row.game_id, "player_id": row.player_id, "reason": mode})
            continue

        game_pk = candidate.get("gamePk")
        if game_pk is None:
            unresolved.append({"game_id": row.game_id, "player_id": row.player_id, "reason": "missing_gamePk"})
            continue

        try:
            boxscore = api.boxscore(int(game_pk))
        except Exception as exc:  # noqa: BLE001
            unresolved.append({"game_id": row.game_id, "player_id": row.player_id, "reason": f"boxscore_error: {exc}"})
            continue

        if row.game_id not in name_map_cache:
            name_map_cache[row.game_id] = extract_player_name_map_from_cached_html(base, row.game_id)
        name_map = name_map_cache[row.game_id]
        local_name = name_map.get(row.player_id)
        if not local_name:
            unresolved.append({"game_id": row.game_id, "player_id": row.player_id, "reason": "missing_local_name"})
            continue

        target_norm = normalize_name(local_name)
        side_players = mlb_boxscore_players_by_side(boxscore, row.is_home)
        candidates = []
        for p in side_players:
            full_name = p.get("person", {}).get("fullName", "")
            if normalize_name(full_name) == target_norm:
                candidates.append(p)
        if not candidates:
            unresolved.append(
                {"game_id": row.game_id, "player_id": row.player_id, "player_name": local_name, "reason": "name_not_found_on_side"}
            )
            continue

        local_stats = batting_stats_from_local(row)
        chosen = choose_best_name_match(candidates, local_stats)
        if chosen is None:
            unresolved.append({"game_id": row.game_id, "player_id": row.player_id, "reason": "name_ambiguous"})
            continue

        checked += 1
        mlb_stats = batting_stats_from_mlb_player(chosen)
        if mlb_stats != local_stats:
            mismatches.append(
                {
                    "game_id": row.game_id,
                    "player_id": row.player_id,
                    "player_name": local_name,
                    "local": local_stats,
                    "mlb": mlb_stats,
                }
            )

    print("\n=== External Player Statline Validation (MLB Stats API) ===")
    print(f"checked={checked} unresolved={len(unresolved)} mismatches={len(mismatches)}")
    if unresolved:
        print("Unresolved sample:")
        for item in unresolved[:10]:
            print(item)
    if mismatches:
        print("Mismatch sample:")
        for item in mismatches[:10]:
            print(item)


def run_pitcher_validation(
    api: MlbApi,
    games_by_id: Dict[str, GameRow],
    pitches: List[PitchRow],
    base: Path,
    pitcher_sample: int,
    rng: random.Random,
) -> None:
    if not pitches:
        print("\n=== External Pitcher Statline Validation ===")
        print("No pitching rows available.")
        return

    sample_rows = rng.sample(pitches, min(pitcher_sample, len(pitches)))
    checked = 0
    mismatches: List[dict] = []
    unresolved: List[dict] = []
    name_map_cache: Dict[str, Dict[str, str]] = {}

    for row in sample_rows:
        game = games_by_id.get(row.game_id)
        if game is None:
            unresolved.append({"game_id": row.game_id, "player_id": row.player_id, "reason": "missing_game"})
            continue

        try:
            candidate, mode = find_mlb_game(api, game)
        except Exception as exc:  # noqa: BLE001
            unresolved.append({"game_id": row.game_id, "player_id": row.player_id, "reason": f"schedule_error: {exc}"})
            continue
        if candidate is None:
            unresolved.append({"game_id": row.game_id, "player_id": row.player_id, "reason": mode})
            continue

        game_pk = candidate.get("gamePk")
        if game_pk is None:
            unresolved.append({"game_id": row.game_id, "player_id": row.player_id, "reason": "missing_gamePk"})
            continue

        try:
            boxscore = api.boxscore(int(game_pk))
        except Exception as exc:  # noqa: BLE001
            unresolved.append({"game_id": row.game_id, "player_id": row.player_id, "reason": f"boxscore_error: {exc}"})
            continue

        if row.game_id not in name_map_cache:
            name_map_cache[row.game_id] = extract_player_name_map_from_cached_html(base, row.game_id)
        name_map = name_map_cache[row.game_id]
        local_name = name_map.get(row.player_id)
        if not local_name:
            unresolved.append({"game_id": row.game_id, "player_id": row.player_id, "reason": "missing_local_name"})
            continue

        target_norm = normalize_name(local_name)
        side_players = mlb_boxscore_players_by_side(boxscore, row.is_home)
        candidates = []
        for p in side_players:
            full_name = p.get("person", {}).get("fullName", "")
            if normalize_name(full_name) == target_norm:
                candidates.append(p)
        if not candidates:
            unresolved.append(
                {"game_id": row.game_id, "player_id": row.player_id, "player_name": local_name, "reason": "name_not_found_on_side"}
            )
            continue

        local_stats = pitching_stats_from_local(row)
        chosen = choose_best_pitcher_match(candidates, local_stats)
        if chosen is None:
            unresolved.append({"game_id": row.game_id, "player_id": row.player_id, "reason": "name_ambiguous"})
            continue

        checked += 1
        mlb_stats = pitching_stats_from_mlb_player(chosen)
        if mlb_stats != local_stats:
            mismatches.append(
                {
                    "game_id": row.game_id,
                    "player_id": row.player_id,
                    "player_name": local_name,
                    "local": local_stats,
                    "mlb": mlb_stats,
                }
            )

    print("\n=== External Pitcher Statline Validation (MLB Stats API) ===")
    print(f"checked={checked} unresolved={len(unresolved)} mismatches={len(mismatches)}")
    if unresolved:
        print("Unresolved sample:")
        for item in unresolved[:10]:
            print(item)
    if mismatches:
        print("Mismatch sample:")
        for item in mismatches[:10]:
            print(item)


def run_lineup_validation(
    api: MlbApi,
    games_by_id: Dict[str, GameRow],
    lineups: List[LineupRow],
    base: Path,
    lineup_sample: int,
    rng: random.Random,
) -> None:
    if not lineups:
        print("\n=== External Lineup Validation ===")
        print("No lineup rows available.")
        return

    sample_rows = rng.sample(lineups, min(lineup_sample, len(lineups)))
    checked = 0
    mismatches: List[dict] = []
    unresolved: List[dict] = []
    name_map_cache: Dict[str, Dict[str, str]] = {}

    for row in sample_rows:
        game = games_by_id.get(row.game_id)
        if game is None:
            unresolved.append({"game_id": row.game_id, "player_id": row.player_id, "reason": "missing_game"})
            continue

        try:
            candidate, mode = find_mlb_game(api, game)
        except Exception as exc:  # noqa: BLE001
            unresolved.append({"game_id": row.game_id, "player_id": row.player_id, "reason": f"schedule_error: {exc}"})
            continue
        if candidate is None:
            unresolved.append({"game_id": row.game_id, "player_id": row.player_id, "reason": mode})
            continue

        game_pk = candidate.get("gamePk")
        if game_pk is None:
            unresolved.append({"game_id": row.game_id, "player_id": row.player_id, "reason": "missing_gamePk"})
            continue

        try:
            boxscore = api.boxscore(int(game_pk))
        except Exception as exc:  # noqa: BLE001
            unresolved.append({"game_id": row.game_id, "player_id": row.player_id, "reason": f"boxscore_error: {exc}"})
            continue

        if row.game_id not in name_map_cache:
            name_map_cache[row.game_id] = extract_player_name_map_from_cached_html(base, row.game_id)
        name_map = name_map_cache[row.game_id]
        local_name = name_map.get(row.player_id)
        if not local_name:
            unresolved.append({"game_id": row.game_id, "player_id": row.player_id, "reason": "missing_local_name"})
            continue

        starters = starting_lineup_by_order(boxscore, row.is_home)
        external_player = starters.get(row.batting_order)
        if external_player is None:
            unresolved.append(
                {
                    "game_id": row.game_id,
                    "player_id": row.player_id,
                    "player_name": local_name,
                    "reason": "missing_external_slot",
                    "batting_order": row.batting_order,
                }
            )
            continue

        checked += 1
        external_name = external_player.get("person", {}).get("fullName", "")
        if normalize_name(local_name) != normalize_name(external_name):
            mismatches.append(
                {
                    "game_id": row.game_id,
                    "batting_order": row.batting_order,
                    "player_id": row.player_id,
                    "local_name": local_name,
                    "external_name": external_name,
                }
            )

    print("\n=== External Lineup Validation (MLB Stats API) ===")
    print(f"checked={checked} unresolved={len(unresolved)} mismatches={len(mismatches)}")
    if unresolved:
        print("Unresolved sample:")
        for item in unresolved[:10]:
            print(item)
    if mismatches:
        print("Mismatch sample:")
        for item in mismatches[:10]:
            print(item)


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)

    games = load_games(args.base, args.season)
    games_by_id = {g.game_id: g for g in games}
    bats = load_batting_rows(args.base, args.season)
    pitches = load_pitching_rows(args.base, args.season)
    lineups = load_lineup_rows(args.base, args.season)

    print(
        f"Loaded games={len(games)} batting_rows={len(bats)} "
        f"pitching_rows={len(pitches)} lineup_rows={len(lineups)}"
    )
    api = MlbApi(timeout=args.timeout)

    run_score_validation(api, games, args.score_sample, rng)
    run_player_validation(api, games_by_id, bats, args.base, args.player_sample, rng)
    run_pitcher_validation(api, games_by_id, pitches, args.base, args.pitcher_sample, rng)
    run_lineup_validation(api, games_by_id, lineups, args.base, args.lineup_sample, rng)


if __name__ == "__main__":
    main()
