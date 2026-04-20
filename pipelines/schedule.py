from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import re
from bs4 import BeautifulSoup


@dataclass
class ScheduledGame:
    game_id: str
    boxscore_url: str
    game_date: str  # YYYY-MM-DD
    start_time: Optional[str]
    home_team_id: str
    away_team_id: str
    doubleheader: Optional[str]  # "1", "2", or None


def parse_schedule_html(html: str, base_url: str) -> List[ScheduledGame]:
    # BRef schedule pages are structured as date headings (h3) followed by <p class=\"game\"> entries.
    # Tables are often comment-wrapped; strip comments for safety.
    cleaned = re.sub(r"<!--", "", html)
    cleaned = re.sub(r"-->", "", cleaned)
    soup = BeautifulSoup(cleaned, "html.parser")

    games: List[ScheduledGame] = []
    current_date: Optional[str] = None

    for tag in soup.find_all(["h3", "p"], class_=lambda c: c in ["game", None]):
        if tag.name == "h3":
            current_date = tag.get_text(strip=True)
            continue

        if tag.name == "p" and "game" in tag.get("class", []):
            box = tag.find("a", string="Boxscore")
            if not box or not box.get("href"):
                continue
            href = box.get("href")
            game_id = href.split("/")[-1].replace(".shtml", "")

            # team anchors: first is away, second inside <strong> is home
            team_links = tag.find_all("a")
            if len(team_links) < 2:
                continue
            away_abbr = team_links[0].get("href", "/").split("/")[2]
            home_abbr = team_links[1].get("href", "/").split("/")[2]

            games.append(
                ScheduledGame(
                    game_id=game_id,
                    boxscore_url=f"{base_url}{href}",
                    game_date=current_date,
                    start_time=None,
                    home_team_id=home_abbr,
                    away_team_id=away_abbr,
                    doubleheader=None,
                )
            )
    return games
