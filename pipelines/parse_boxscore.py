from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

from bs4 import BeautifulSoup


@dataclass
class ParsedBoxscore:
    game: Dict
    lineups: List[Dict]
    batting_lines: List[Dict]
    pitching_lines: List[Dict]


def _strip_comments(html: str) -> str:
    # Baseball-Reference wraps tables inside HTML comments; remove them crudely.
    html = re.sub(r"<!--", "", html)
    html = re.sub(r"-->", "", html)
    return html


def parse_boxscore(html: str) -> ParsedBoxscore:
    soup = BeautifulSoup(_strip_comments(html), "html.parser")

    # Game summary
    scorebox = soup.find("div", {"class": "scorebox"})
    if not scorebox:
        raise ValueError("scorebox not found")
    strongs = scorebox.find_all("strong")
    away_team_abbr = strongs[0].find("a")["href"].split("/")[-2]
    home_team_abbr = strongs[1].find("a")["href"].split("/")[-2]
    away_team_name = strongs[0].get_text(strip=True)
    home_team_name = strongs[1].get_text(strip=True)
    def _norm(name: str) -> str:
        return re.sub(r"[^a-z]", "", name.lower())
    team_name_to_abbr = {
        _norm(away_team_name): away_team_abbr,
        _norm(home_team_name): home_team_abbr,
    }
    meta = scorebox.find("div", {"class": "scorebox_meta"}).find_all("div")
    date_str = meta[0].get_text(strip=True)
    start_time = meta[1].get_text(strip=True).replace("Start Time:", "").strip() if len(meta) > 1 else None

    def score_for(idx: int) -> int:
        line = scorebox.find_all("div", {"class": "scores"})[idx]
        return int(line.find("div").get_text(strip=True))

    game_id = soup.find("input", {"name": "game_id"})
    game_id = game_id["value"] if game_id and game_id.get("value") else soup.find("meta", {"property": "og:url"}).get("content", "").split("/")[-1].replace(".shtml", "")

    game_row = {
        "game_id": game_id,
        "game_date": date_str,
        "start_time": start_time,
        "home_team_id": home_team_abbr,
        "away_team_id": away_team_abbr,
        "home_score": score_for(1),
        "away_score": score_for(0),
    }

    stats_tables = soup.find_all("table", {"class": "stats_table"})
    batting_lines, lineups, pitching_lines = [], [], []

    for table in stats_tables:
        table_id = table.get("id", "")
        caption = table.find("caption")
        if not caption:
            continue
        team_name = caption.get_text(strip=True).replace(" Table", "")
        team_abbr = team_name_to_abbr.get(_norm(team_name))
        if not team_abbr:
            continue
        is_home = team_abbr == home_team_abbr

        # Batting tables
        if "batting" in table_id.lower():
            rows = table.find_all("tr")[1:-1]  # skip header and totals footer
            order = 1
            for r in rows:
                player_th = r.find("th", {"data-stat": "player"})
                if player_th is None:
                    continue
                player_link = player_th.find("a")
                if player_link is None or player_link.get("href") is None:
                    continue
                player_id = player_link.get("href").split("/")[-1].replace(".shtml", "")

                # Subs are indented with non-breaking spaces; skip them for lineup order
                if "\xa0\xa0" in player_th.get_text():
                    batting_order = None
                else:
                    batting_order = order

                stat_cells = {td["data-stat"]: td.get_text(strip=True) for td in r.find_all("td")}
                line = {
                    "game_id": game_id,
                    "player_id": player_id,
                    "is_home": is_home,
                    "batting_order": batting_order if batting_order is not None else None,
                    "team_id": team_abbr,
                    **stat_cells,
                }
                batting_lines.append(line)
                # add to lineup if batting order present (starter)
                if batting_order is not None and batting_order <= 9:
                    lineups.append(
                        {
                            "game_id": game_id,
                            "team_id": team_abbr,
                            "batting_order": batting_order,
                            "player_id": player_id,
                            "position": stat_cells.get("pos"),
                            "is_home": is_home,
                        }
                    )
                    order += 1

        # Pitching tables
        if "pitching" in table_id.lower():
            rows = table.find_all("tr")[1:-1]
            for r in rows:
                player_th = r.find("th", {"data-stat": "player"})
                if player_th is None:
                    continue
                player_link = player_th.find("a")
                if player_link is None or player_link.get("href") is None:
                    continue
                player_id = player_link.get("href").split("/")[-1].replace(".shtml", "")
                stat_cells = {td["data-stat"]: td.get_text(strip=True) for td in r.find_all("td")}
                line = {
                    "game_id": game_id,
                    "player_id": player_id,
                    "is_home": is_home,
                    "team_id": team_abbr,
                    **stat_cells,
                }
                pitching_lines.append(line)

    return ParsedBoxscore(
        game=game_row,
        lineups=lineups,
        batting_lines=batting_lines,
        pitching_lines=pitching_lines,
    )
