from __future__ import annotations

from bbpieleague.models import Match, StandingRow, Team


def calculate_standings(teams: list[Team], matches: list[Match]) -> list[StandingRow]:
    table = {
        team.id: StandingRow(team_id=team.id, team_name=team.name)
        for team in teams
    }

    for match in matches:
        home = table.get(match.home_team_id)
        away = table.get(match.away_team_id)
        if not home or not away:
            continue

        home.games += 1
        away.games += 1

        home.td_for += match.home_td
        home.td_against += match.away_td
        away.td_for += match.away_td
        away.td_against += match.home_td

        home.cas_for += match.home_cas
        home.cas_against += match.away_cas
        away.cas_for += match.away_cas
        away.cas_against += match.home_cas

        if match.home_td > match.away_td:
            home.wins += 1
            home.points += 3
            away.losses += 1
        elif match.home_td < match.away_td:
            away.wins += 1
            away.points += 3
            home.losses += 1
        else:
            home.draws += 1
            away.draws += 1
            home.points += 1
            away.points += 1

    return sorted(
        table.values(),
        key=lambda row: (
            row.points,
            row.td_diff,
            row.cas_diff,
            row.td_for,
            -row.team_id,
        ),
        reverse=True,
    )
