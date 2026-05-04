from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from bbpieleague.models import Competition, Match, Player, Team


DEFAULT_COMPETITION_ID = 1
DEFAULT_COMPETITION_NAME = "Default Season"


@dataclass(slots=True)
class LeagueData:
    teams: list[Team]
    players: list[Player]
    competitions: list[Competition]
    active_competition_id: int
    matches: list[Match]
    default_competition_id: int = DEFAULT_COMPETITION_ID
    competition_team_exclusions: dict[int, list[int]] = field(default_factory=dict)


def get_data_path() -> Path:
    return Path.cwd() / "data" / "league.json"


def load_league(path: Path | None = None) -> LeagueData:
    data_path = path or get_data_path()
    if not data_path.exists():
        return LeagueData(
            teams=[],
            players=[],
            competitions=[
                Competition(id=DEFAULT_COMPETITION_ID, name=DEFAULT_COMPETITION_NAME, kind="season")
            ],
            active_competition_id=DEFAULT_COMPETITION_ID,
            matches=[],
            default_competition_id=DEFAULT_COMPETITION_ID,
            competition_team_exclusions={},
        )

    with data_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    teams = [Team(**item) for item in payload.get("teams", [])]
    players = [Player(**item) for item in payload.get("players", [])]
    competitions = [Competition(**item) for item in payload.get("competitions", [])]
    if not competitions:
        competitions = [
            Competition(id=DEFAULT_COMPETITION_ID, name=DEFAULT_COMPETITION_NAME, kind="season")
        ]

    competition_ids = {competition.id for competition in competitions}
    default_competition_id = payload.get("default_competition_id")
    if default_competition_id is None:
        default_competition_id = competitions[0].id
    if default_competition_id not in competition_ids:
        default_competition_id = competitions[0].id

    active_competition_id = payload.get("active_competition_id")
    if active_competition_id is None:
        active_competition_id = default_competition_id
    if active_competition_id not in competition_ids:
        active_competition_id = default_competition_id

    matches = [Match(**item) for item in payload.get("matches", [])]

    raw_exclusions = payload.get("competition_team_exclusions", {})
    competition_team_exclusions: dict[int, list[int]] = {}
    for raw_competition_id, raw_team_ids in raw_exclusions.items():
        try:
            competition_id = int(raw_competition_id)
        except (TypeError, ValueError):
            continue

        if competition_id not in competition_ids:
            continue

        team_ids: list[int] = []
        for raw_team_id in raw_team_ids if isinstance(raw_team_ids, list) else []:
            try:
                team_id = int(raw_team_id)
            except (TypeError, ValueError):
                continue
            team_ids.append(team_id)

        if team_ids:
            competition_team_exclusions[competition_id] = sorted(set(team_ids))

    return LeagueData(
        teams=teams,
        players=players,
        competitions=competitions,
        active_competition_id=active_competition_id,
        matches=matches,
        default_competition_id=default_competition_id,
        competition_team_exclusions=competition_team_exclusions,
    )


def save_league(data: LeagueData, path: Path | None = None) -> Path:
    data_path = path or get_data_path()
    data_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "teams": [team.to_dict() for team in data.teams],
        "players": [player.to_dict() for player in data.players],
        "competitions": [competition.to_dict() for competition in data.competitions],
        "active_competition_id": data.active_competition_id,
        "default_competition_id": data.default_competition_id,
        "competition_team_exclusions": data.competition_team_exclusions,
        "matches": [match.to_dict() for match in data.matches],
    }
    with data_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)

    return data_path
