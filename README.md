# BBPieLeague

A lightweight Blood Bowl league manager to track:

- Teams
- Players (rosters)
- Matches
- Standings based on points, then TD difference, then CAS difference
- Multiple competitions (seasons and tournaments)
- Web UI for day-to-day league admin

## Quickstart

```bash
cd /Users/ralfk/Documents/Wargaming/BB/Pyleague2
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Initialize a fresh league file:

```bash
bbpieleague init
```

## Usage

Add teams:

```bash
bbpieleague add-team "Reikland Reavers" --coach-naf-number 12345
bbpieleague add-team "Orcland Smashers" --coach "Gorbad"
```

List teams:

```bash
bbpieleague list-teams
```

Add players to team rosters:

```bash
bbpieleague add-player 1 "Ludwig Kruger" --position "Blitzer" --number 7
bbpieleague add-player 1 "Otto Weiss" --position "Thrower" --number 12
```

List all players (or one team with --team-id):

```bash
bbpieleague list-players
bbpieleague list-players --team-id 1
```

Record a match:

```bash
bbpieleague record-match 1 2 2 1 3 2 --played-on 2026-05-04
```

Manage seasons and tournaments:

```bash
bbpieleague add-competition "Season 1" --type season
bbpieleague add-competition "Spike Cup" --type tournament
bbpieleague add-competition "Chaos Invitational" --type tournament --theme chaos
bbpieleague list-competitions
bbpieleague use-competition 2
```

Record/list/standings use the active competition by default, or override with --competition-id:

```bash
bbpieleague record-match 1 2 2 1 3 2 --competition-id 2
bbpieleague list-matches --competition-id 2
bbpieleague standings --competition-id 2
```

Show standings:

```bash
bbpieleague standings
```

Show all matches:

```bash
bbpieleague list-matches
```

## Web UI

Run the browser app:

```bash
bbpieleague-web
```

Then open:

- <http://127.0.0.1:8000>

What you can do in the UI:

- Add competitions and switch active competition
- Pick a visual theme per competition (imperial, chaos, orc, undead)
- Record matches in the active competition
- Register teams with a NAF coach number and auto-generate the coach profile link
- View recent matches and standings
- View teams (read-only)

CLI team creation also supports NAF coach numbers:

```bash
bbpieleague add-team "Reikland Reavers" --coach-naf-number 12345
```

## Data storage

Data is stored in:

- `data/league.json`

The file is ignored by git so your league state stays local.
