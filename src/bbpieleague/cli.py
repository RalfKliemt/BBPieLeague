from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date

from bbpieleague.models import COMPETITION_THEME_CHOICES, Competition, Match, Player, Team
from bbpieleague.standings import calculate_standings
from bbpieleague.storage import DEFAULT_COMPETITION_ID, LeagueData, load_league, save_league


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bbpieleague", description="Blood Bowl league manager")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create an empty league data file")

    add_team_parser = sub.add_parser("add-team", help="Add a team")
    add_team_parser.add_argument("name", help="Team name")
    add_team_parser.add_argument("--coach", default="", help="Coach name")

    sub.add_parser("list-teams", help="List teams")

    add_comp_parser = sub.add_parser("add-competition", help="Add a season or tournament")
    add_comp_parser.add_argument("name", help="Competition name")
    add_comp_parser.add_argument(
        "--type",
        dest="kind",
        choices=["season", "tournament"],
        default="season",
        help="Competition type",
    )
    add_comp_parser.add_argument(
        "--theme",
        choices=COMPETITION_THEME_CHOICES,
        default="imperial",
        help="Competition color theme",
    )

    sub.add_parser("list-competitions", help="List seasons/tournaments")

    use_comp_parser = sub.add_parser("use-competition", help="Set active competition context")
    use_comp_parser.add_argument("competition_id", type=int, help="Competition id")

    add_player_parser = sub.add_parser("add-player", help="Add a player to a team roster")
    add_player_parser.add_argument("team_id", type=int, help="Team id")
    add_player_parser.add_argument("name", help="Player name")
    add_player_parser.add_argument("--position", default="", help="Player position")
    add_player_parser.add_argument("--number", type=int, default=None, help="Jersey number")

    list_players_parser = sub.add_parser("list-players", help="List all players or by team")
    list_players_parser.add_argument("--team-id", type=int, default=None, help="Filter to one team")

    record_parser = sub.add_parser("record-match", help="Record match result")
    record_parser.add_argument("home_team_id", type=int)
    record_parser.add_argument("away_team_id", type=int)
    record_parser.add_argument("home_td", type=int)
    record_parser.add_argument("away_td", type=int)
    record_parser.add_argument("home_cas", type=int)
    record_parser.add_argument("away_cas", type=int)
    record_parser.add_argument("--competition-id", type=int, default=None, help="Override active competition")
    record_parser.add_argument("--played-on", default=date.today().isoformat(), help="YYYY-MM-DD")

    list_matches_parser = sub.add_parser("list-matches", help="List matches")
    list_matches_parser.add_argument("--competition-id", type=int, default=None, help="Filter competition")

    standings_parser = sub.add_parser("standings", help="Show league standings")
    standings_parser.add_argument("--competition-id", type=int, default=None, help="Filter competition")

    return parser


def _next_team_id(data: LeagueData) -> int:
    if not data.teams:
        return 1
    return max(team.id for team in data.teams) + 1


def _next_match_id(data: LeagueData) -> int:
    if not data.matches:
        return 1
    return max(match.id for match in data.matches) + 1


def _next_player_id(data: LeagueData) -> int:
    if not data.players:
        return 1
    return max(player.id for player in data.players) + 1


def _next_competition_id(data: LeagueData) -> int:
    if not data.competitions:
        return 1
    return max(competition.id for competition in data.competitions) + 1


def _team_exists(data: LeagueData, team_id: int) -> bool:
    return any(team.id == team_id for team in data.teams)


def _competition_exists(data: LeagueData, competition_id: int) -> bool:
    return any(competition.id == competition_id for competition in data.competitions)


def _resolve_competition_id(data: LeagueData, override_id: int | None) -> int:
    competition_id = data.active_competition_id if override_id is None else override_id
    if not _competition_exists(data, competition_id):
        raise ValueError(f"Competition with id {competition_id} does not exist")
    return competition_id


def _competition_label(data: LeagueData, competition_id: int) -> str:
    for competition in data.competitions:
        if competition.id == competition_id:
            return f"{competition.name} ({competition.kind})"
    return f"Unknown Competition #{competition_id}"


def _match_in_competition(match: Match, competition_id: int) -> bool:
    # Legacy matches created before multi-season support have competition_id=None.
    # They belong only to the default season (id=1), not every selected season.
    return match.competition_id == competition_id or (
        match.competition_id is None and competition_id == DEFAULT_COMPETITION_ID
    )


def _teams_for_matches(teams: list[Team], matches: list[Match]) -> list[Team]:
    season_team_ids = {match.home_team_id for match in matches} | {match.away_team_id for match in matches}
    return [team for team in teams if team.id in season_team_ids]


def cmd_init() -> int:
    default_competition = Competition(id=1, name="Default Season", kind="season")
    path = save_league(
        LeagueData(
            teams=[],
            players=[],
            competitions=[default_competition],
            active_competition_id=default_competition.id,
            matches=[],
        )
    )
    print(f"Initialized league file at: {path}")
    return 0


def cmd_add_team(name: str, coach: str) -> int:
    data = load_league()
    team = Team(id=_next_team_id(data), name=name, coach=coach)
    data.teams.append(team)
    save_league(data)
    print(f"Added team #{team.id}: {team.name}")
    return 0


def cmd_list_teams() -> int:
    data = load_league()
    if not data.teams:
        print("No teams yet.")
        return 0

    print("ID  Team                      Coach")
    print("--  ------------------------  ------------------------")
    for team in sorted(data.teams, key=lambda item: item.id):
        print(f"{team.id:<3} {team.name:<24} {team.coach}")
    return 0


def cmd_add_competition(name: str, kind: str, theme: str) -> int:
    data = load_league()
    competition = Competition(id=_next_competition_id(data), name=name, kind=kind, theme=theme)
    data.competitions.append(competition)
    save_league(data)
    print(f"Added {competition.kind} #{competition.id}: {competition.name} [{competition.theme}]")
    return 0


def cmd_list_competitions() -> int:
    data = load_league()
    if not data.competitions:
        print("No competitions yet.")
        return 0

    print("ID  Type        Theme     Active  Name")
    print("--  ----------  --------  ------  ------------------------")
    for competition in sorted(data.competitions, key=lambda item: item.id):
        active = "*" if competition.id == data.active_competition_id else ""
        print(f"{competition.id:<3} {competition.kind:<10}  {competition.theme:<8}  {active:<6}  {competition.name}")
    return 0


def cmd_use_competition(competition_id: int) -> int:
    data = load_league()
    if not _competition_exists(data, competition_id):
        raise ValueError(f"Competition with id {competition_id} does not exist")

    data.active_competition_id = competition_id
    save_league(data)
    print(f"Active competition set to #{competition_id}: {_competition_label(data, competition_id)}")
    return 0


def cmd_add_player(team_id: int, name: str, position: str, number: int | None) -> int:
    data = load_league()
    if not _team_exists(data, team_id):
        raise ValueError(f"Team with id {team_id} does not exist")

    if number is not None:
        duplicate_number = any(
            player.team_id == team_id and player.number == number for player in data.players
        )
        if duplicate_number:
            raise ValueError(f"Team {team_id} already has a player with number {number}")

    player = Player(
        id=_next_player_id(data),
        team_id=team_id,
        name=name,
        position=position,
        number=number,
    )
    data.players.append(player)
    save_league(data)
    print(f"Added player #{player.id}: {player.name} (team {team_id})")
    return 0


def cmd_list_players(team_id: int | None) -> int:
    data = load_league()
    if not data.players:
        print("No players yet.")
        return 0

    if team_id is not None and not _team_exists(data, team_id):
        raise ValueError(f"Team with id {team_id} does not exist")

    team_names = {team.id: team.name for team in data.teams}
    players = sorted(
        (
            player
            for player in data.players
            if team_id is None or player.team_id == team_id
        ),
        key=lambda item: (item.team_id, item.number if item.number is not None else 999, item.name.lower()),
    )

    if not players:
        print("No players found for that team.")
        return 0

    grouped: dict[int, list[Player]] = defaultdict(list)
    for player in players:
        grouped[player.team_id].append(player)

    for current_team_id in sorted(grouped):
        team_name = team_names.get(current_team_id, f"Unknown Team #{current_team_id}")
        print(f"Team {current_team_id}: {team_name}")
        print("ID  #    Name                      Position")
        print("--  ---  ------------------------  ----------------")
        for player in grouped[current_team_id]:
            number_text = str(player.number) if player.number is not None else "-"
            print(f"{player.id:<3} {number_text:<4} {player.name:<24} {player.position}")
        print()

    return 0


def cmd_record_match(
    home_team_id: int,
    away_team_id: int,
    home_td: int,
    away_td: int,
    home_cas: int,
    away_cas: int,
    competition_id: int | None,
    played_on: str,
) -> int:
    data = load_league()
    if not _team_exists(data, home_team_id):
        raise ValueError(f"Team with id {home_team_id} does not exist")
    if not _team_exists(data, away_team_id):
        raise ValueError(f"Team with id {away_team_id} does not exist")

    target_competition_id = _resolve_competition_id(data, competition_id)

    match = Match(
        id=_next_match_id(data),
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_td=home_td,
        away_td=away_td,
        home_cas=home_cas,
        away_cas=away_cas,
        competition_id=target_competition_id,
        played_on=played_on,
    )

    data.matches.append(match)
    save_league(data)
    label = _competition_label(data, target_competition_id)
    print(f"Recorded match #{match.id} in {label}: {home_team_id} {home_td}-{away_td} {away_team_id}")
    return 0


def cmd_list_matches(competition_id: int | None) -> int:
    data = load_league()
    team_names = {team.id: team.name for team in data.teams}
    target_competition_id = _resolve_competition_id(data, competition_id)

    matches = [
        match
        for match in data.matches
        if _match_in_competition(match, target_competition_id)
    ]

    if not matches:
        print("No matches yet.")
        return 0

    print(f"Competition: {_competition_label(data, target_competition_id)}")
    print("ID  Date        Match                          TD    CAS")
    print("--  ----------  -----------------------------  ----  ----")
    for match in sorted(matches, key=lambda item: item.id):
        home_name = team_names.get(match.home_team_id, f"#{match.home_team_id}")
        away_name = team_names.get(match.away_team_id, f"#{match.away_team_id}")
        td_score = f"{match.home_td}-{match.away_td}"
        cas_score = f"{match.home_cas}-{match.away_cas}"
        pairing = f"{home_name} vs {away_name}"
        print(f"{match.id:<3} {match.played_on:<10}  {pairing:<29}  {td_score:<4}  {cas_score:<4}")
    return 0


def cmd_standings(competition_id: int | None) -> int:
    data = load_league()
    target_competition_id = _resolve_competition_id(data, competition_id)
    matches = [
        match
        for match in data.matches
        if _match_in_competition(match, target_competition_id)
    ]
    rows = calculate_standings(_teams_for_matches(data.teams, matches), matches)
    if not rows:
        print("No standings yet for this competition.")
        return 0

    print(f"Competition: {_competition_label(data, target_competition_id)}")
    print("Pos Team                      GP W D L PTS  TD    CAS")
    print("--- ------------------------  -- - - - ---  ----  ----")
    for index, row in enumerate(rows, start=1):
        td = f"{row.td_for}:{row.td_against}"
        cas = f"{row.cas_for}:{row.cas_against}"
        print(
            f"{index:<3} {row.team_name:<24}  {row.games:<2} {row.wins:<1} {row.draws:<1} {row.losses:<1} {row.points:<3}  {td:<4}  {cas:<4}"
        )
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "init":
            return cmd_init()
        if args.command == "add-team":
            return cmd_add_team(name=args.name, coach=args.coach)
        if args.command == "list-teams":
            return cmd_list_teams()
        if args.command == "add-competition":
            return cmd_add_competition(name=args.name, kind=args.kind, theme=args.theme)
        if args.command == "list-competitions":
            return cmd_list_competitions()
        if args.command == "use-competition":
            return cmd_use_competition(competition_id=args.competition_id)
        if args.command == "add-player":
            return cmd_add_player(
                team_id=args.team_id,
                name=args.name,
                position=args.position,
                number=args.number,
            )
        if args.command == "list-players":
            return cmd_list_players(team_id=args.team_id)
        if args.command == "record-match":
            return cmd_record_match(
                home_team_id=args.home_team_id,
                away_team_id=args.away_team_id,
                home_td=args.home_td,
                away_td=args.away_td,
                home_cas=args.home_cas,
                away_cas=args.away_cas,
                competition_id=args.competition_id,
                played_on=args.played_on,
            )
        if args.command == "list-matches":
            return cmd_list_matches(competition_id=args.competition_id)
        if args.command == "standings":
            return cmd_standings(competition_id=args.competition_id)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
