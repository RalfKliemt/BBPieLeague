from __future__ import annotations

import argparse
from datetime import date

from bbpieleague.models import Match, Team
from bbpieleague.standings import calculate_standings
from bbpieleague.storage import LeagueData, load_league, save_league


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bbpieleague", description="Blood Bowl league manager")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create an empty league data file")

    add_team_parser = sub.add_parser("add-team", help="Add a team")
    add_team_parser.add_argument("name", help="Team name")
    add_team_parser.add_argument("--coach", default="", help="Coach name")

    sub.add_parser("list-teams", help="List teams")

    record_parser = sub.add_parser("record-match", help="Record match result")
    record_parser.add_argument("home_team_id", type=int)
    record_parser.add_argument("away_team_id", type=int)
    record_parser.add_argument("home_td", type=int)
    record_parser.add_argument("away_td", type=int)
    record_parser.add_argument("home_cas", type=int)
    record_parser.add_argument("away_cas", type=int)
    record_parser.add_argument("--played-on", default=date.today().isoformat(), help="YYYY-MM-DD")

    sub.add_parser("list-matches", help="List all matches")
    sub.add_parser("standings", help="Show league standings")

    return parser


def _next_team_id(data: LeagueData) -> int:
    if not data.teams:
        return 1
    return max(team.id for team in data.teams) + 1


def _next_match_id(data: LeagueData) -> int:
    if not data.matches:
        return 1
    return max(match.id for match in data.matches) + 1


def _team_exists(data: LeagueData, team_id: int) -> bool:
    return any(team.id == team_id for team in data.teams)


def cmd_init() -> int:
    path = save_league(LeagueData(teams=[], matches=[]))
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


def cmd_record_match(
    home_team_id: int,
    away_team_id: int,
    home_td: int,
    away_td: int,
    home_cas: int,
    away_cas: int,
    played_on: str,
) -> int:
    data = load_league()
    if not _team_exists(data, home_team_id):
        raise ValueError(f"Team with id {home_team_id} does not exist")
    if not _team_exists(data, away_team_id):
        raise ValueError(f"Team with id {away_team_id} does not exist")

    match = Match(
        id=_next_match_id(data),
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_td=home_td,
        away_td=away_td,
        home_cas=home_cas,
        away_cas=away_cas,
        played_on=played_on,
    )

    data.matches.append(match)
    save_league(data)
    print(f"Recorded match #{match.id}: {home_team_id} {home_td}-{away_td} {away_team_id}")
    return 0


def cmd_list_matches() -> int:
    data = load_league()
    team_names = {team.id: team.name for team in data.teams}

    if not data.matches:
        print("No matches yet.")
        return 0

    print("ID  Date        Match                          TD    CAS")
    print("--  ----------  -----------------------------  ----  ----")
    for match in sorted(data.matches, key=lambda item: item.id):
        home_name = team_names.get(match.home_team_id, f"#{match.home_team_id}")
        away_name = team_names.get(match.away_team_id, f"#{match.away_team_id}")
        td_score = f"{match.home_td}-{match.away_td}"
        cas_score = f"{match.home_cas}-{match.away_cas}"
        pairing = f"{home_name} vs {away_name}"
        print(f"{match.id:<3} {match.played_on:<10}  {pairing:<29}  {td_score:<4}  {cas_score:<4}")
    return 0


def cmd_standings() -> int:
    data = load_league()
    rows = calculate_standings(data.teams, data.matches)
    if not rows:
        print("No teams yet.")
        return 0

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
        if args.command == "record-match":
            return cmd_record_match(
                home_team_id=args.home_team_id,
                away_team_id=args.away_team_id,
                home_td=args.home_td,
                away_td=args.away_td,
                home_cas=args.home_cas,
                away_cas=args.away_cas,
                played_on=args.played_on,
            )
        if args.command == "list-matches":
            return cmd_list_matches()
        if args.command == "standings":
            return cmd_standings()
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
