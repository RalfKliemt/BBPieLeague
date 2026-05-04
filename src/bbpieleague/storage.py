from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from bbpieleague.models import Match, Team


@dataclass(slots=True)
class LeagueData:
    teams: list[Team]
    matches: list[Match]


def get_data_path() -> Path:
    return Path.cwd() / "data" / "league.json"


def load_league(path: Path | None = None) -> LeagueData:
    data_path = path or get_data_path()
    if not data_path.exists():
        return LeagueData(teams=[], matches=[])

    with data_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    teams = [Team(**item) for item in payload.get("teams", [])]
    matches = [Match(**item) for item in payload.get("matches", [])]
    return LeagueData(teams=teams, matches=matches)


def save_league(data: LeagueData, path: Path | None = None) -> Path:
    data_path = path or get_data_path()
    data_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "teams": [team.to_dict() for team in data.teams],
        "matches": [match.to_dict() for match in data.matches],
    }
    with data_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)

    return data_path
