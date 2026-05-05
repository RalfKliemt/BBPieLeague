from __future__ import annotations

from dataclasses import asdict, dataclass

from bbpieleague.naf import extract_naf_coach_number_from_url


COMPETITION_THEME_CHOICES = ("imperial", "chaos", "orc", "undead")


@dataclass(slots=True)
class Team:
    id: int
    name: str
    coach: str = ""
    coach_naf_number: str = ""
    team_url: str = ""
    coach_url: str = ""

    def __post_init__(self) -> None:
        self.coach_naf_number = self.coach_naf_number.strip()
        if not self.coach_naf_number and self.coach_url:
            self.coach_naf_number = extract_naf_coach_number_from_url(self.coach_url)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class Player:
    id: int
    team_id: int
    name: str
    position: str = ""
    number: int | None = None

    def __post_init__(self) -> None:
        if self.number is not None and self.number < 1:
            raise ValueError("number must be 1 or greater when provided.")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class Competition:
    id: int
    name: str
    kind: str = "season"
    theme: str = "imperial"

    def __post_init__(self) -> None:
        if self.kind not in {"season", "tournament"}:
            raise ValueError("kind must be either 'season' or 'tournament'.")
        if self.theme not in COMPETITION_THEME_CHOICES:
            allowed = ", ".join(COMPETITION_THEME_CHOICES)
            raise ValueError(f"theme must be one of: {allowed}.")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class Match:
    id: int
    home_team_id: int
    away_team_id: int
    home_td: int
    away_td: int
    home_cas: int
    away_cas: int
    competition_id: int | None = None
    played_on: str = ""

    def __post_init__(self) -> None:
        if self.home_team_id == self.away_team_id:
            raise ValueError("A team cannot play against itself.")

        for attr_name in ("home_td", "away_td", "home_cas", "away_cas"):
            value = getattr(self, attr_name)
            if value < 0:
                raise ValueError(f"{attr_name} must be 0 or greater.")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class StandingRow:
    team_id: int
    team_name: str
    games: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    points: int = 0
    td_for: int = 0
    td_against: int = 0
    cas_for: int = 0
    cas_against: int = 0

    @property
    def td_diff(self) -> int:
        return self.td_for - self.td_against

    @property
    def cas_diff(self) -> int:
        return self.cas_for - self.cas_against
