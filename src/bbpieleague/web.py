from __future__ import annotations

import os
import secrets
from datetime import date
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for

from bbpieleague.models import COMPETITION_THEME_CHOICES, Competition, Match, Team
from bbpieleague.standings import calculate_standings
from bbpieleague.storage import DEFAULT_COMPETITION_ID, LeagueData, load_league, save_league


def _next_team_id(data: LeagueData) -> int:
    if not data.teams:
        return 1
    return max(team.id for team in data.teams) + 1


def _next_match_id(data: LeagueData) -> int:
    if not data.matches:
        return 1
    return max(match.id for match in data.matches) + 1


def _next_competition_id(data: LeagueData) -> int:
    if not data.competitions:
        return 1
    return max(competition.id for competition in data.competitions) + 1


def _competition_exists(data: LeagueData, competition_id: int) -> bool:
    return any(competition.id == competition_id for competition in data.competitions)


def _team_exists(data: LeagueData, team_id: int) -> bool:
    return any(team.id == team_id for team in data.teams)


def _find_team(data: LeagueData, team_id: int) -> Team | None:
    for team in data.teams:
        if team.id == team_id:
            return team
    return None


def _find_match(data: LeagueData, match_id: int) -> Match | None:
    for match in data.matches:
        if match.id == match_id:
            return match
    return None


def _find_competition(data: LeagueData, competition_id: int) -> Competition | None:
    for competition in data.competitions:
        if competition.id == competition_id:
            return competition
    return None


def _active_competition(data: LeagueData) -> Competition:
    for competition in data.competitions:
        if competition.id == data.active_competition_id:
            return competition
    return data.competitions[0]


def _matches_for_active(data: LeagueData) -> list[Match]:
    active_id = data.active_competition_id
    return [match for match in data.matches if _match_in_competition(match, active_id)]


def _match_in_competition(match: Match, competition_id: int) -> bool:
    # Legacy matches created before multi-season support have competition_id=None.
    # They belong only to the default season (id=1), not every active season.
    return match.competition_id == competition_id or (
        match.competition_id is None and competition_id == DEFAULT_COMPETITION_ID
    )


def _teams_for_matches(teams: list[Team], matches: list[Match]) -> list[Team]:
    season_team_ids = {match.home_team_id for match in matches} | {match.away_team_id for match in matches}
    return [team for team in teams if team.id in season_team_ids]


def create_app() -> Flask:
    template_dir = Path(__file__).with_name("templates")
    static_dir = Path(__file__).with_name("static")
    app = Flask(__name__, template_folder=str(template_dir), static_folder=str(static_dir))
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

    @app.get("/")
    def index():
        data = load_league()
        active_competition = _active_competition(data)
        matches = sorted(_matches_for_active(data), key=lambda item: item.id, reverse=True)
        teams = sorted(data.teams, key=lambda item: item.id)
        season_teams = _teams_for_matches(teams, matches)
        standings = calculate_standings(season_teams, list(reversed(matches)))
        competitions = sorted(data.competitions, key=lambda item: item.id)
        team_names = {team.id: team.name for team in teams}
        team_coaches = {team.id: team.coach for team in teams}

        return render_template(
            "index.html",
            active_competition=active_competition,
            competitions=competitions,
            competition_themes=COMPETITION_THEME_CHOICES,
            teams=teams,
            matches=matches,
            standings=standings,
            team_names=team_names,
            team_coaches=team_coaches,
            today=date.today().isoformat(),
        )

    @app.post("/competitions")
    def add_competition():
        data = load_league()
        name = request.form.get("name", "").strip()
        kind = "season"
        theme = request.form.get("theme", "imperial").strip()

        if not name:
            flash("Competition name is required.", "error")
            return redirect(url_for("index"))

        try:
            competition = Competition(id=_next_competition_id(data), name=name, kind=kind, theme=theme)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("index"))

        data.competitions.append(competition)
        save_league(data)
        flash(f"Added {competition.kind}: {competition.name}", "success")
        return redirect(url_for("index"))

    @app.post("/competitions/use")
    def use_competition():
        data = load_league()
        competition_id_raw = request.form.get("competition_id", "").strip()

        try:
            competition_id = int(competition_id_raw)
        except ValueError:
            flash("Invalid competition id.", "error")
            return redirect(url_for("index"))

        if not _competition_exists(data, competition_id):
            flash(f"Competition #{competition_id} does not exist.", "error")
            return redirect(url_for("index"))

        data.active_competition_id = competition_id
        save_league(data)
        flash(f"Active competition set to #{competition_id}.", "success")
        return redirect(url_for("index"))

    @app.post("/competitions/update")
    def update_competition():
        data = load_league()
        competition_id_raw = request.form.get("competition_id", "").strip()
        name = request.form.get("name", "").strip()

        try:
            competition_id = int(competition_id_raw)
        except ValueError:
            flash("Invalid competition id.", "error")
            return redirect(url_for("index"))

        competition = _find_competition(data, competition_id)
        if competition is None:
            flash(f"Competition #{competition_id} does not exist.", "error")
            return redirect(url_for("index"))

        if not name:
            flash("Competition name is required.", "error")
            return redirect(url_for("index"))

        if any(existing.id != competition_id and existing.name.lower() == name.lower() for existing in data.competitions):
            flash("A season with that name already exists.", "error")
            return redirect(url_for("index"))

        previous_name = competition.name
        competition.name = name
        save_league(data)
        flash(f"Renamed season #{competition.id}: {previous_name} -> {competition.name}", "success")
        return redirect(url_for("index"))

    @app.post("/teams")
    def add_team():
        data = load_league()
        name = request.form.get("name", "").strip()
        coach = request.form.get("coach", "").strip()

        if not name:
            flash("Team name is required.", "error")
            return redirect(url_for("index"))

        # Keep names unique to avoid confusion in match entry dropdowns and standings.
        if any(team.name.lower() == name.lower() for team in data.teams):
            flash("A team with that name already exists.", "error")
            return redirect(url_for("index"))

        team = Team(id=_next_team_id(data), name=name, coach=coach)
        data.teams.append(team)
        save_league(data)
        flash(f"Registered team #{team.id}: {team.name}", "success")
        return redirect(url_for("index"))

    @app.post("/teams/update")
    def update_team():
        data = load_league()
        team_id_raw = request.form.get("team_id", "").strip()
        name = request.form.get("name", "").strip()
        coach = request.form.get("coach", "").strip()

        try:
            team_id = int(team_id_raw)
        except ValueError:
            flash("Invalid team id.", "error")
            return redirect(url_for("index"))

        team = _find_team(data, team_id)
        if team is None:
            flash(f"Team #{team_id} does not exist.", "error")
            return redirect(url_for("index"))

        if not name:
            flash("Team name is required.", "error")
            return redirect(url_for("index"))

        if any(existing.id != team_id and existing.name.lower() == name.lower() for existing in data.teams):
            flash("A team with that name already exists.", "error")
            return redirect(url_for("index"))

        previous_name = team.name
        team.name = name
        team.coach = coach
        save_league(data)
        flash(f"Updated team #{team.id}: {previous_name} -> {team.name}", "success")
        return redirect(url_for("index"))

    @app.post("/matches")
    def add_match():
        data = load_league()

        def int_field(name: str) -> int:
            raw = request.form.get(name, "").strip()
            if raw == "":
                raise ValueError(f"{name} is required")
            return int(raw)

        try:
            home_team_id = int_field("home_team_id")
            away_team_id = int_field("away_team_id")
            home_td = int_field("home_td")
            away_td = int_field("away_td")
            home_cas = int_field("home_cas")
            away_cas = int_field("away_cas")
        except ValueError as exc:
            flash(f"Invalid match input: {exc}", "error")
            return redirect(url_for("index"))

        played_on = request.form.get("played_on", date.today().isoformat()).strip()

        if not _team_exists(data, home_team_id) or not _team_exists(data, away_team_id):
            flash("Both teams must exist.", "error")
            return redirect(url_for("index"))

        try:
            match = Match(
                id=_next_match_id(data),
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                home_td=home_td,
                away_td=away_td,
                home_cas=home_cas,
                away_cas=away_cas,
                competition_id=data.active_competition_id,
                played_on=played_on,
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("index"))

        data.matches.append(match)
        save_league(data)
        flash(f"Recorded match #{match.id} in active competition.", "success")
        return redirect(url_for("index"))

    @app.post("/matches/update")
    def update_match():
        data = load_league()

        def int_field(name: str) -> int:
            raw = request.form.get(name, "").strip()
            if raw == "":
                raise ValueError(f"{name} is required")
            return int(raw)

        try:
            match_id = int_field("match_id")
            home_team_id = int_field("home_team_id")
            away_team_id = int_field("away_team_id")
            home_td = int_field("home_td")
            away_td = int_field("away_td")
            home_cas = int_field("home_cas")
            away_cas = int_field("away_cas")
        except ValueError as exc:
            flash(f"Invalid match input: {exc}", "error")
            return redirect(url_for("index"))

        played_on = request.form.get("played_on", date.today().isoformat()).strip()

        match = _find_match(data, match_id)
        if match is None:
            flash(f"Match #{match_id} does not exist.", "error")
            return redirect(url_for("index"))

        if not _match_in_competition(match, data.active_competition_id):
            flash("You can only edit matches from the active competition.", "error")
            return redirect(url_for("index"))

        if not _team_exists(data, home_team_id) or not _team_exists(data, away_team_id):
            flash("Both teams must exist.", "error")
            return redirect(url_for("index"))

        try:
            # Re-validate with the model rules before mutating stored data.
            Match(
                id=match.id,
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                home_td=home_td,
                away_td=away_td,
                home_cas=home_cas,
                away_cas=away_cas,
                competition_id=match.competition_id,
                played_on=played_on,
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("index"))

        match.home_team_id = home_team_id
        match.away_team_id = away_team_id
        match.home_td = home_td
        match.away_td = away_td
        match.home_cas = home_cas
        match.away_cas = away_cas
        match.played_on = played_on
        save_league(data)
        flash(f"Updated match #{match.id} in active competition.", "success")
        return redirect(url_for("index"))

    @app.post("/matches/delete")
    def delete_match():
        data = load_league()
        match_id_raw = request.form.get("match_id", "").strip()

        try:
            match_id = int(match_id_raw)
        except ValueError:
            flash("Invalid match id.", "error")
            return redirect(url_for("index"))

        match = _find_match(data, match_id)
        if match is None:
            flash(f"Match #{match_id} does not exist.", "error")
            return redirect(url_for("index"))

        if not _match_in_competition(match, data.active_competition_id):
            flash("You can only delete matches from the active competition.", "error")
            return redirect(url_for("index"))

        data.matches = [existing for existing in data.matches if existing.id != match_id]
        save_league(data)
        flash(f"Deleted match #{match_id} from active competition.", "success")
        return redirect(url_for("index"))

    return app


def main() -> int:
    app = create_app()
    app.run(host="127.0.0.1", port=8000, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
