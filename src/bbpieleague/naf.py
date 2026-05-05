from __future__ import annotations

import re
from html import unescape
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


NAF_COACH_URL_TEMPLATE = (
    "https://member.thenaf.net/index.php?module=NAF&type=coachpage&coach={coach_number}"
)
_NAF_NAME_ROW_RE = re.compile(
    r"<tr>\s*<td>\s*NAF name\s*</td>\s*<td>(?P<name>.*?)</td>\s*</tr>",
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def build_naf_coach_url(coach_number: str) -> str:
    normalized = normalize_naf_coach_number(coach_number)
    if not normalized:
        return ""
    return NAF_COACH_URL_TEMPLATE.format(coach_number=normalized)


def extract_naf_coach_number_from_url(raw_url: str) -> str:
    link = raw_url.strip()
    if not link:
        return ""

    parsed = urlparse(link)
    if not parsed.scheme and not parsed.netloc:
        parsed = urlparse(f"https://{link}")

    query_values = parse_qs(parsed.query)
    coach_values = query_values.get("coach", [])
    if not coach_values:
        return ""

    coach_number = coach_values[0].strip()
    return coach_number if coach_number.isdigit() else ""


def normalize_naf_coach_number(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return ""
    if value.isdigit():
        return value
    return extract_naf_coach_number_from_url(value)


def fetch_naf_coach_name(coach_number: str, timeout: float = 10.0) -> str:
    normalized = normalize_naf_coach_number(coach_number)
    if not normalized:
        return ""

    request = Request(
        build_naf_coach_url(normalized),
        headers={"User-Agent": "bbpieleague/0.1 (+https://member.thenaf.net/)"},
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except URLError as exc:
        raise ValueError(f"Unable to reach NAF coach page: {exc.reason}") from exc

    match = _NAF_NAME_ROW_RE.search(body)
    if not match:
        return ""

    name = _TAG_RE.sub("", match.group("name"))
    name = unescape(name)
    return re.sub(r"\s+", " ", name).strip()