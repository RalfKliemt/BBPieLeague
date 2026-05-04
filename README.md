# BBPieLeague

A lightweight Blood Bowl league manager to track:

- Teams
- Matches
- Standings based on points, then TD difference, then CAS difference

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
bbpieleague add-team "Reikland Reavers" --coach "Griff"
bbpieleague add-team "Orcland Smashers" --coach "Gorbad"
```

List teams:

```bash
bbpieleague list-teams
```

Record a match:

```bash
bbpieleague record-match 1 2 2 1 3 2 --played-on 2026-05-04
```

Show standings:

```bash
bbpieleague standings
```

Show all matches:

```bash
bbpieleague list-matches
```

## Data storage

Data is stored in:

- `data/league.json`

The file is ignored by git so your league state stays local.
