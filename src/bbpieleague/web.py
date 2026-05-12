from __future__ import annotations

import importlib
import os
import secrets
import subprocess
import sys
from datetime import date
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, flash, redirect, render_template, render_template_string, request, send_from_directory, url_for

from bbpieleague.models import COMPETITION_THEME_CHOICES, Competition, Match, Team
from bbpieleague.naf import build_naf_coach_url, fetch_naf_coach_name, normalize_naf_coach_number
from bbpieleague.standings import calculate_standings
from bbpieleague.storage import DEFAULT_COMPETITION_ID, LeagueData, load_league, save_league


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DICED_REPO_URL = "https://github.com/RalfKliemt/DICED.git"
DICED_CACHE_DIR = PROJECT_ROOT / "data" / "integrations" / "diced"
DICED_REPO_DIR = DICED_CACHE_DIR / "repo"
DICED_EXAMPLES = ["224s3", "3++ 4+ 5+", "2+ 2d+ 4+", "2+, 3+, 4+"]


def _run_git_command(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd is not None else None,
        check=False,
        capture_output=True,
        text=True,
    )


def _summarize_command_failure(result: subprocess.CompletedProcess[str]) -> str:
    details = (result.stderr or result.stdout or "git command failed").strip()
    return details.splitlines()[-1] if details else "git command failed"


def _ensure_diced_repo() -> dict[str, object]:
    DICED_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    git_check = _run_git_command(["--version"])
    if git_check.returncode != 0:
        return {
            "ready": False,
            "action": "unavailable",
            "repo_dir": str(DICED_REPO_DIR),
            "error": "git is not available in PATH.",
        }

    if DICED_REPO_DIR.exists() and not (DICED_REPO_DIR / ".git").exists():
        return {
            "ready": False,
            "action": "unavailable",
            "repo_dir": str(DICED_REPO_DIR),
            "error": f"{DICED_REPO_DIR} exists but is not a git checkout.",
        }

    if not DICED_REPO_DIR.exists():
        clone_result = _run_git_command(["clone", "--depth", "1", DICED_REPO_URL, str(DICED_REPO_DIR)])
        if clone_result.returncode != 0:
            return {
                "ready": False,
                "action": "clone-failed",
                "repo_dir": str(DICED_REPO_DIR),
                "error": _summarize_command_failure(clone_result),
            }

        return {
            "ready": True,
            "action": "cloned",
            "repo_dir": str(DICED_REPO_DIR),
            "error": "",
        }

    pull_result = _run_git_command(["pull", "--ff-only"], cwd=DICED_REPO_DIR)
    if pull_result.returncode != 0:
        return {
            "ready": False,
            "action": "update-failed",
            "repo_dir": str(DICED_REPO_DIR),
            "error": _summarize_command_failure(pull_result),
        }

    return {
        "ready": True,
        "action": "updated",
        "repo_dir": str(DICED_REPO_DIR),
        "error": "",
    }


def _adapt_diced_template(template_source: str) -> str:
    template_source = template_source.replace(
        "{{ url_for('static', filename='style.css') }}",
        "{{ url_for('diced_static', filename='style.css') }}",
    )
    template_source = template_source.replace(
        '<form class="sequence-form" method="get" action="/">',
        '<form class="sequence-form" method="get" action="{{ url_for(\'diced_page\') }}">',
    )
    template_source = template_source.replace(
        '<a class="example-chip" href="/?sequence={{ example|urlencode }}">{{ example }}</a>',
        '<a class="example-chip" href="{{ url_for(\'diced_page\', sequence=example) }}">{{ example }}</a>',
    )
    return template_source


@lru_cache(maxsize=1)
def _load_diced_integration() -> dict[str, object]:
    status = _ensure_diced_repo()
    integration: dict[str, object] = {
        "ready": bool(status.get("ready")),
        "action": status.get("action", "unknown"),
        "error": status.get("error", ""),
        "repo_dir": Path(status.get("repo_dir", DICED_REPO_DIR)),
    }

    if not integration["ready"]:
        return integration

    repo_dir = Path(integration["repo_dir"])
    src_dir = repo_dir / "src"
    template_path = src_dir / "diced" / "templates" / "index.html"
    static_dir = src_dir / "diced" / "static"

    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    try:
        importlib.invalidate_caches()
        diced_core = importlib.import_module("diced.core")
        diced_web = importlib.import_module("diced.web")
        template_source = _adapt_diced_template(template_path.read_text(encoding="utf-8"))
    except (ImportError, OSError) as exc:
        integration["ready"] = False
        integration["error"] = str(exc)
        return integration

    integration.update(
        {
            "build_result_view": diced_web.build_result_view,
            "calculator": diced_core.RollSequenceCalculator(),
            "parse_roll_sequence": diced_core.parse_roll_sequence,
            "static_dir": static_dir,
            "template_source": template_source,
        }
    )
    return integration


def _diced_status_view() -> dict[str, object]:
    integration = _load_diced_integration()
    return {
        "ready": bool(integration.get("ready")),
        "action": integration.get("action", "unknown"),
        "error": integration.get("error", ""),
    }


def _render_diced_unavailable(status: dict[str, object], status_code: int = 503) -> tuple[str, int]:
    error = status.get("error", "Unknown integration error.")
    return (
        render_template_string(
            """<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>DICED unavailable</title>
    <style>
      body { font-family: Helvetica, Arial, sans-serif; margin: 0; padding: 1.5rem; background: #f4f8ff; color: #0c1733; }
      main { max-width: 42rem; margin: 0 auto; background: #fff; border: 2px solid #d2deff; border-radius: 14px; padding: 1.25rem; }
      h1 { margin-top: 0; }
      p { line-height: 1.5; }
      code { font-family: Menlo, monospace; }
    </style>
  </head>
  <body>
    <main>
      <h1>DICED is unavailable</h1>
      <p>The integration could not be prepared automatically.</p>
      <p><strong>Reason:</strong> {{ error }}</p>
      <p><strong>Action:</strong> {{ action }}</p>
      <p>The main league app is still available.</p>
    </main>
  </body>
</html>
""",
            error=error,
            action=status.get("action", "unknown"),
        ),
        status_code,
    )


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


def _active_teams_for_competition(data: LeagueData, competition_id: int) -> list[Team]:
    excluded_team_ids = set(data.competition_team_exclusions.get(competition_id, []))
    return [team for team in data.teams if team.id not in excluded_team_ids]


def _normalize_web_link(raw: str) -> str:
    link = raw.strip()
    if not link:
        return ""

    parsed = urlparse(link)
    if not parsed.scheme and not parsed.netloc:
        link = f"https://{link}"
        parsed = urlparse(link)

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Links must be valid http(s) URLs.")

    return link


def _display_web_link(raw: str) -> str:
    link = raw.strip()
    if not link:
        return ""

    parsed = urlparse(link)
    if not parsed.scheme and not parsed.netloc:
        return f"https://{link}"

    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return link

    return ""


def _resolve_coach_profile(
    raw_naf_number: str,
    requested_coach: str = "",
    existing_team: Team | None = None,
) -> tuple[str, str, str, str | None]:
    normalized_naf_number = normalize_naf_coach_number(raw_naf_number)
    manual_coach = requested_coach.strip()
    if raw_naf_number.strip() and not normalized_naf_number:
        raise ValueError("Coach NAF number must be numeric or a valid NAF coach URL.")

    if not normalized_naf_number:
        coach_name = manual_coach if manual_coach else (existing_team.coach if existing_team is not None else "")
        return coach_name, "", "", None

    coach_url = build_naf_coach_url(normalized_naf_number)
    existing_coach = existing_team.coach if existing_team is not None else ""
    coach_name = manual_coach if manual_coach else existing_coach
    warning: str | None = None

    # If the submitted coach field changed, treat it as a manual override.
    # Otherwise refresh from NAF whenever a NAF number is provided.
    manual_override = bool(existing_team is not None and manual_coach and manual_coach != existing_coach)
    if not manual_override:
        try:
            fetched_name = fetch_naf_coach_name(normalized_naf_number)
        except ValueError as exc:
            warning = str(exc)
        else:
            if fetched_name:
                coach_name = fetched_name
            else:
                warning = "Coach name could not be read from the NAF profile page."

    return coach_name, normalized_naf_number, coach_url, warning


def create_app() -> Flask:
    template_dir = Path(__file__).with_name("templates")
    static_dir = Path(__file__).with_name("static")
    app = Flask(__name__, template_folder=str(template_dir), static_folder=str(static_dir))
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

    @app.get("/")
    def index():
        data = load_league()
        diced_integration = _diced_status_view()
        active_competition = _active_competition(data)
        matches = sorted(_matches_for_active(data), key=lambda item: item.id, reverse=True)
        teams = sorted(data.teams, key=lambda item: item.id)
        excluded_team_ids = set(data.competition_team_exclusions.get(data.active_competition_id, []))
        active_teams = sorted(
            _active_teams_for_competition(data, data.active_competition_id),
            key=lambda item: item.id,
        )
        removed_teams = [team for team in teams if team.id in excluded_team_ids]
        standings = calculate_standings(active_teams, list(reversed(matches)))
        competitions = sorted(data.competitions, key=lambda item: item.id)
        team_names = {team.id: team.name for team in teams}
        team_coaches = {team.id: team.coach for team in teams}
        team_urls = {team.id: _display_web_link(team.team_url) for team in teams}
        coach_urls = {
            team.id: _display_web_link(build_naf_coach_url(team.coach_naf_number) if team.coach_naf_number else team.coach_url)
            for team in teams
        }

        return render_template(
            "index.html",
            active_competition=active_competition,
            default_competition_id=data.default_competition_id,
            competitions=competitions,
            competition_themes=COMPETITION_THEME_CHOICES,
            teams=teams,
            active_teams=active_teams,
            removed_teams=removed_teams,
            matches=matches,
            standings=standings,
            team_names=team_names,
            team_coaches=team_coaches,
            team_urls=team_urls,
            coach_urls=coach_urls,
            today=date.today().isoformat(),
            diced_integration=diced_integration,
        )

    @app.get("/tools/diced")
    def diced_page():
        integration = _load_diced_integration()
        if not integration.get("ready"):
            return _render_diced_unavailable(integration)

        calculator = integration["calculator"]
        parse_roll_sequence = integration["parse_roll_sequence"]
        build_result_view = integration["build_result_view"]

        sequence_text = request.args.get("sequence", "").strip()
        error = ""
        result_view = None

        if sequence_text:
            try:
                sequence = parse_roll_sequence(sequence_text)
                result = calculator.calculate(sequence, max_global_rerolls=2)
                result_view = build_result_view(result)
            except ValueError as exc:
                error = str(exc)

        return render_template_string(
            str(integration["template_source"]),
            sequence_text=sequence_text,
            error=error,
            result=result_view,
            examples=DICED_EXAMPLES,
        )

    @app.get("/tools/diced/static/<path:filename>")
    def diced_static(filename: str):
        integration = _load_diced_integration()
        if not integration.get("ready"):
            abort(404)

        return send_from_directory(Path(integration["static_dir"]), filename)

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
        set_default = request.form.get("set_default") == "on"

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

        if set_default:
            data.default_competition_id = competition.id
            data.active_competition_id = competition.id

        save_league(data)
        if set_default:
            flash(
                f"Renamed season #{competition.id}: {previous_name} -> {competition.name}. Set as default season.",
                "success",
            )
        else:
            flash(f"Renamed season #{competition.id}: {previous_name} -> {competition.name}", "success")
        return redirect(url_for("index"))

    @app.post("/teams")
    def add_team():
        data = load_league()
        name = request.form.get("name", "").strip()
        coach_raw = request.form.get("coach", "")
        coach_naf_number_raw = request.form.get("coach_naf_number", "")
        team_url_raw = request.form.get("team_url", "")

        if not name:
            flash("Team name is required.", "error")
            return redirect(url_for("index"))

        # Keep names unique to avoid confusion in match entry dropdowns and standings.
        if any(team.name.lower() == name.lower() for team in data.teams):
            flash("A team with that name already exists.", "error")
            return redirect(url_for("index"))

        try:
            team_url = _normalize_web_link(team_url_raw)
            coach, coach_naf_number, coach_url, warning = _resolve_coach_profile(
                coach_naf_number_raw,
                requested_coach=coach_raw,
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("index"))

        team = Team(
            id=_next_team_id(data),
            name=name,
            coach=coach,
            coach_naf_number=coach_naf_number,
            team_url=team_url,
            coach_url=coach_url,
        )
        data.teams.append(team)
        save_league(data)
        if warning:
            flash(warning, "warning")
        flash(f"Registered team #{team.id}: {team.name}", "success")
        return redirect(url_for("index"))

    @app.post("/teams/update")
    def update_team():
        data = load_league()
        team_id_raw = request.form.get("team_id", "").strip()
        name = request.form.get("name", "").strip()
        coach_raw = request.form.get("coach", "")
        coach_naf_number_raw = request.form.get("coach_naf_number", "")
        team_url_raw = request.form.get("team_url", "")

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

        try:
            team_url = _normalize_web_link(team_url_raw)
            coach, coach_naf_number, coach_url, warning = _resolve_coach_profile(
                coach_naf_number_raw,
                requested_coach=coach_raw,
                existing_team=team,
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("index"))

        previous_name = team.name
        team.name = name
        team.coach = coach
        team.coach_naf_number = coach_naf_number
        team.team_url = team_url
        team.coach_url = coach_url
        save_league(data)
        if warning:
            flash(warning, "warning")
        flash(f"Updated team #{team.id}: {previous_name} -> {team.name}", "success")
        return redirect(url_for("index"))

    @app.post("/teams/delete")
    def delete_team():
        data = load_league()
        team_id_raw = request.form.get("team_id", "").strip()
        scope = request.form.get("scope", "season").strip().lower()

        try:
            team_id = int(team_id_raw)
        except ValueError:
            flash("Invalid team id.", "error")
            return redirect(url_for("index"))

        team = _find_team(data, team_id)
        if team is None:
            flash(f"Team #{team_id} does not exist.", "error")
            return redirect(url_for("index"))

        if scope == "global":
            data.teams = [current for current in data.teams if current.id != team_id]
            data.players = [player for player in data.players if player.team_id != team_id]
            data.matches = [
                match
                for match in data.matches
                if match.home_team_id != team_id and match.away_team_id != team_id
            ]

            cleaned_exclusions: dict[int, list[int]] = {}
            for competition_id, excluded in data.competition_team_exclusions.items():
                remaining = [excluded_team_id for excluded_team_id in excluded if excluded_team_id != team_id]
                if remaining:
                    cleaned_exclusions[competition_id] = remaining
            data.competition_team_exclusions = cleaned_exclusions

            save_league(data)
            flash(f"Deleted team #{team_id} globally.", "success")
            return redirect(url_for("index"))

        active_competition_id = data.active_competition_id
        excluded = set(data.competition_team_exclusions.get(active_competition_id, []))
        excluded.add(team_id)
        data.competition_team_exclusions[active_competition_id] = sorted(excluded)

        before_count = len(data.matches)
        data.matches = [
            match
            for match in data.matches
            if not (
                _match_in_competition(match, active_competition_id)
                and (match.home_team_id == team_id or match.away_team_id == team_id)
            )
        ]
        removed_matches = before_count - len(data.matches)

        save_league(data)
        flash(
            f"Removed team #{team_id} from active season and deleted {removed_matches} season matches.",
            "success",
        )
        return redirect(url_for("index"))

    @app.post("/teams/restore")
    def restore_team():
        data = load_league()
        team_id_raw = request.form.get("team_id", "").strip()

        try:
            team_id = int(team_id_raw)
        except ValueError:
            flash("Invalid team id.", "error")
            return redirect(url_for("index"))

        team = _find_team(data, team_id)
        if team is None:
            flash(f"Team #{team_id} does not exist.", "error")
            return redirect(url_for("index"))

        active_competition_id = data.active_competition_id
        excluded = set(data.competition_team_exclusions.get(active_competition_id, []))
        if team_id not in excluded:
            flash(f"Team #{team_id} is already active in this season.", "success")
            return redirect(url_for("index"))

        excluded.remove(team_id)
        if excluded:
            data.competition_team_exclusions[active_competition_id] = sorted(excluded)
        else:
            data.competition_team_exclusions.pop(active_competition_id, None)

        save_league(data)
        flash(f"Re-added team #{team_id} to active season.", "success")
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

        active_team_ids = {
            team.id
            for team in _active_teams_for_competition(data, data.active_competition_id)
        }
        if home_team_id not in active_team_ids or away_team_id not in active_team_ids:
            flash("Both teams must be active in this season.", "error")
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

        active_team_ids = {
            team.id
            for team in _active_teams_for_competition(data, data.active_competition_id)
        }
        if home_team_id not in active_team_ids or away_team_id not in active_team_ids:
            flash("Both teams must be active in this season.", "error")
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
