#!/usr/bin/env python3
"""Render a self-hosted isometric city from GitHub's PUBLIC calendar HTML.

Python standard library only. No GraphQL, PAT, GITHUB_TOKEN, private repository
content or third-party rendering service is used to fetch or render the data.
The workflow's short-lived GITHUB_TOKEN is used separately, only to publish Git.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
from html import escape
from html.parser import HTMLParser
import math
from pathlib import Path
import re
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MAX_RESPONSE_BYTES = 2_000_000
PALETTE = ("#162039", "#30576e", "#4c6eb0", "#9b80e8", "#7ce9ed")
USERNAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?\Z")
COUNT = re.compile(r"^(No|[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+) contributions? on \S")


@dataclass(frozen=True)
class Day:
    date: date
    count: int
    level: int

    def __post_init__(self) -> None:
        if not isinstance(self.date, date):
            raise ValueError("Calendar dates must be valid dates.")
        if not isinstance(self.count, int) or not 0 <= self.count <= 100_000:
            raise ValueError("Contribution count is outside the accepted range.")
        if self.level not in range(5) or (self.count == 0) != (self.level == 0):
            raise ValueError("Contribution level and count are inconsistent.")


class CalendarParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cells: dict[str, tuple[str, str]] = {}
        self.tooltips: dict[str, str] = {}
        self._tooltip: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if attr.get("data-date"):
            cell_id = attr.get("id")
            if not cell_id or cell_id in self.cells or attr.get("data-level") is None:
                raise ValueError("Missing or duplicate public calendar cell metadata.")
            self.cells[cell_id] = (attr["data-date"], attr["data-level"])  # type: ignore[assignment]
        if tag == "tool-tip" and attr.get("for"):
            self._tooltip = attr["for"]
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._tooltip is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "tool-tip" and self._tooltip is not None:
            if self._tooltip in self.tooltips:
                raise ValueError("Duplicate public calendar tooltip.")
            self.tooltips[self._tooltip] = " ".join("".join(self._text).split())
            self._tooltip = None
            self._text = []


def validate_username(username: str) -> str:
    if not USERNAME.fullmatch(username):
        raise ValueError("Expected a GitHub login, not a URL or path.")
    return username


def validate_days(days: list[Day], minimum_days: int = 365) -> list[Day]:
    if not minimum_days <= len(days) <= 371:
        raise ValueError("Incomplete calendar; keeping the existing SVG unchanged.")
    ordered = sorted(days, key=lambda day: day.date)
    for previous, current in zip(ordered, ordered[1:]):
        if current.date - previous.date != timedelta(days=1):
            raise ValueError("Duplicate dates or a gap in the public calendar.")
    return ordered


def parse_calendar(html: str, minimum_days: int = 365) -> list[Day]:
    parser = CalendarParser()
    parser.feed(html)
    parser.close()
    days = []
    for cell_id, (date_text, level) in parser.cells.items():
        tooltip = parser.tooltips.get(cell_id, "")
        match = COUNT.match(tooltip)
        if not match:
            raise ValueError("Unrecognized calendar counts; refusing to invent data.")
        count = 0 if match[1] == "No" else int(match[1].replace(",", ""))
        days.append(Day(date.fromisoformat(date_text), count, int(level)))
    return validate_days(days, minimum_days)


def fetch_calendar(username: str) -> str:
    username = validate_username(username)
    request = Request(
        f"https://github.com/users/{username}/contributions",
        headers={
            "User-Agent": "tonmoycoder-public-profile-renderer/1.0",
            "Accept": "text/html",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    # Deliberately no Authorization header or token/environment lookup.
    with urlopen(request, timeout=30) as response:
        if response.geturl().split("/", 3)[:3] != ["https:", "", "github.com"]:
            raise ValueError("Unexpected redirect away from the public GitHub calendar.")
        if "text/html" not in response.headers.get("Content-Type", ""):
            raise ValueError("GitHub did not return public calendar HTML.")
        data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("Calendar response was unexpectedly large.")
    return data.decode("utf-8")


def height_for(count: int, peak: int) -> float:
    """Height is logarithmically scaled by real counts, never randomized."""
    if count == 0:
        return 0.0
    return round(6 + 80 * math.log1p(count) / math.log1p(max(peak, 1)), 2)


def shade(color: str, factor: float) -> str:
    return "#" + "".join(f"{round(int(color[i:i + 2], 16) * factor):02x}" for i in (1, 3, 5))


def points(values: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in values)


def render_svg(username: str, days: list[Day]) -> str:
    username = validate_username(username)
    days = validate_days(days, minimum_days=1)
    total = sum(day.count for day in days)
    active = sum(day.count > 0 for day in days)
    peak = max(day.count for day in days)
    start, end = days[0].date, days[-1].date
    sunday = start - timedelta(days=(start.weekday() + 1) % 7)
    weeks = (end - sunday).days // 7 + 1
    # Keep even a 54-column leap-year boundary inside the same viewBox.
    week_step = min(20.4, 1082 / weeks)

    def position(week: int, weekday: int) -> tuple[float, float]:
        return 78 + week * week_step + weekday * 10, 420 - week * 3.7 + weekday * 6

    label = f"{start:%d %b %Y} — {end:%d %b %Y}"
    description = (
        f"{username}'s publicly visible GitHub calendar: {total:,} contributions "
        f"across {active} active days, from {start.isoformat()} to {end.isoformat()}. "
        "Each building is one day. Height is logarithmically scaled by contribution "
        "count; color follows the public calendar level. No activity is fabricated."
    )
    svg = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="560" viewBox="0 0 1280 560" role="img" aria-labelledby="title desc">
<title id="title">{escape(username)} — contribution city</title>
<desc id="desc">{escape(description)}</desc>
<defs>
  <linearGradient id="background" x2="1" y2="1"><stop stop-color="#0b1021"/><stop offset="1" stop-color="#101a2c"/></linearGradient>
  <radialGradient id="aura"><stop stop-color="#8b5cf6" stop-opacity=".12"/><stop offset="1" stop-color="#8b5cf6" stop-opacity="0"/></radialGradient>
  <style>text{{font-family:Inter,'Segoe UI',Arial,sans-serif}}.mono{{font-family:Consolas,'Liberation Mono',monospace}}.city-light{{animation:light 6s ease-in-out infinite}}@keyframes light{{0%,100%{{opacity:.38}}50%{{opacity:.8}}}}@media(prefers-reduced-motion:reduce){{.city-light{{animation:none!important}}}}</style>
</defs>
<rect width="1280" height="560" rx="20" fill="url(#background)"/>
<rect x="1" y="1" width="1278" height="558" rx="19" fill="none" stroke="#a78bfa" stroke-opacity=".2"/>
<ellipse cx="945" cy="285" rx="312" ry="186" fill="url(#aura)"/>
<text x="48" y="36" fill="#a396ce" font-size="10" font-weight="600" letter-spacing="2.1">PUBLIC GITHUB CALENDAR / SELF-HOSTED</text>
<text x="46" y="75" fill="#eef2ff" font-size="30" font-weight="650" letter-spacing="-.8">A city of small steps.</text>
<text x="48" y="100" fill="#7f90b0" font-size="12">{label}</text>
''']
    for x, value, caption in ((862, total, "CONTRIBUTIONS"), (1008, active, "ACTIVE DAYS"), (1152, peak, "BUSIEST DAY")):
        svg.append(f'<text x="{x}" y="69" text-anchor="middle" fill="#dcd9f5" font-size="26" class="mono">{value:,}</text>\n')
        svg.append(f'<text x="{x}" y="91" text-anchor="middle" fill="#7686a4" font-size="9" letter-spacing="1.4">{caption}</text>\n')

    a, b, c, d = position(0, 0), position(weeks, 0), position(weeks, 7), position(0, 7)
    svg.append(f'<polygon points="{points([a, b, c, d])}" fill="#111a2b" stroke="#3b4166" stroke-opacity=".55"/>\n')
    svg.append(f'<polygon points="{points([d, c, (c[0], c[1] + 7), (d[0], d[1] + 7)])}" fill="#141a30" stroke="#292e49" stroke-width=".6"/>\n')

    buildings = []
    for day in days:
        offset = (day.date - sunday).days
        week, weekday = divmod(offset, 7)
        x, y = position(week, weekday)
        buildings.append((y, x, day))
    # Painter's order: farther ground footprints first, not the tallest first.
    for y, x, day in sorted(buildings):
        h = height_for(day.count, peak)
        color = PALETTE[day.level]
        a, b, c, d = (x, y), (x + 16, y - 5), (x + 26, y + 1), (x + 10, y + 6)
        at, bt, ct, dt = [(px, py - h) for px, py in (a, b, c, d)]
        svg.append(f'<g data-date="{day.date.isoformat()}" data-count="{day.count}" data-level="{day.level}" data-height="{h:.2f}"><title>{day.date.isoformat()}: {day.count:,} contributions</title>')
        if h:
            svg.append(f'<polygon points="{points([at, dt, d, a])}" fill="{shade(color, .38)}"/>')
            svg.append(f'<polygon points="{points([dt, ct, c, d])}" fill="{shade(color, .62)}"/>')
        svg.append(f'<polygon points="{points([at, bt, ct, dt])}" fill="{color}" stroke="{shade(color, 1 if h else 1.32)}" stroke-width=".45"/>')
        if h > 20:
            window_paths = []
            for row in range(10, int(h) - 3, 10):
                window_paths.append(f'M{x + 13:.2f} {y + 3 - row:.2f}l3-1 M{x + 19:.2f} {y + 1 - row:.2f}l3-1')
            phase = day.date.toordinal() % 6
            svg.append(f'<path class="city-light" d="{" ".join(window_paths)}" stroke="#e3ffff" stroke-width="1" opacity=".55" style="animation-delay:-{phase}s"/>')
        svg.append('</g>\n')

    # Month labels follow the front edge; the first visible day is not invented.
    month = None
    for day in days:
        if day.date.month != month:
            month = day.date.month
            week = (day.date - sunday).days // 7
            x, y = position(week, 7)
            svg.append(f'<text x="{x + 3:.2f}" y="{y + 23:.2f}" fill="#677a9d" font-size="10">{day.date:%b}</text>\n')
    svg.append('''<path d="M48 510h1184" stroke="#29334c" stroke-opacity=".65"/>
<text x="48" y="538" fill="#8092b1" font-size="10.5">One building = one day. Height is log-scaled activity, not code quality.</text>
<text x="966" y="538" fill="#7183a2" font-size="10">LESS</text>
''')
    for index, color in enumerate(PALETTE):
        svg.append(f'<rect x="{1008 + index * 26}" y="526" width="17" height="12" rx="2" fill="{color}"/>\n')
    svg.append('<text x="1150" y="538" fill="#7183a2" font-size="10">MORE</text>\n</svg>\n')
    return "".join(svg)


def write_svg(output: Path, content: str) -> bool:
    """Write atomically only after successful parsing/rendering; retain on failure."""
    if output.is_file() and output.read_text(encoding="utf-8") == content:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            file.write(content)
        temporary.replace(output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--username", default="tonmoycoder")
    cli.add_argument("--input", type=Path, help="Use previously downloaded public calendar HTML (offline).")
    cli.add_argument("--output", type=Path, default=Path("profile-3d-contrib/profile-night-rainbow.svg"))
    args = cli.parse_args(argv)
    try:
        username = validate_username(args.username)
        html = args.input.read_text(encoding="utf-8") if args.input else fetch_calendar(username)
        days = parse_calendar(html)
        changed = write_svg(args.output, render_svg(username, days))
    except (OSError, ValueError, HTTPError, URLError) as error:
        print(f"Calendar generation failed; existing SVG retained: {error}", file=sys.stderr)
        return 1
    print(f'{"Updated" if changed else "Unchanged"}: {args.output} ({len(days)} public calendar days, {sum(day.count for day in days):,} contributions).')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
