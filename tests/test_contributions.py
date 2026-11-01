from datetime import date, timedelta
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from scripts.render_contributions import (
    fetch_calendar, height_for, main,
    parse_calendar, render_svg, validate_username, write_svg,
)


def fixture(length=365, start=date(2025, 1, 1), counts=None):
    counts = counts or {}
    cells, tooltips = [], []
    for i in range(length):
        day = start + timedelta(days=i)
        count = counts.get(i, 0)
        level = 0 if count == 0 else min(count, 4)
        cells.append(f'<td data-date="{day.isoformat()}" id="day-{i}" data-level="{level}"></td>')
        label = "No contributions" if count == 0 else f'{count:,} contribution{"s" if count != 1 else ""}'
        tooltips.append(f'<tool-tip for="day-{i}">{label} on January 1st.</tool-tip>')
    # GitHub's table groups days by weekday, not in chronological order.
    return "<table>" + "".join(cells[::2] + cells[1::2]) + "</table>" + "".join(tooltips)


class CalendarTests(unittest.TestCase):
    def test_realistic_year_is_sorted_and_counted(self):
        days = parse_calendar(fixture(counts={5: 1, 82: 1234, 364: 8}))
        self.assertEqual(len(days), 365)
        self.assertEqual(days[0].date, date(2025, 1, 1))
        self.assertEqual(sum(d.count for d in days), 1243)
        self.assertEqual(days[82].level, 4)

    def test_leap_year_and_54_week_boundary(self):
        days = parse_calendar(fixture(length=366, start=date(2028, 1, 1)))
        self.assertEqual(days[-1].date, date(2028, 12, 31))
        ET.fromstring(render_svg("tonmoycoder", days))

    def test_changed_or_empty_markup_is_not_a_zero_activity_year(self):
        for html in ["", "<html>rate limited</html>", fixture(length=100)]:
            with self.subTest(html=html[:20]), self.assertRaises(ValueError):
                parse_calendar(html)

    def test_missing_tooltip_fails_instead_of_inventing_a_count(self):
        html = fixture().replace('for="day-10"', 'for="unknown-day"')
        with self.assertRaisesRegex(ValueError, "Unrecognized"):
            parse_calendar(html)

    def test_unknown_language_or_malformed_count_fails(self):
        for label in ["নেই", "many", "-4", "100001", "1,2,3"]:
            html = fixture().replace("No contributions on January 1st.", f"{label} contributions on January 1st.", 1)
            with self.subTest(label=label), self.assertRaises(ValueError):
                parse_calendar(html)

    def test_duplicate_cell_and_date_and_missing_day_fail(self):
        cases = [
            fixture().replace('id="day-2"', 'id="day-0"'),
            fixture().replace('data-date="2025-01-03"', 'data-date="2025-01-01"'),
            fixture().replace('<td data-date="2025-01-03" id="day-2" data-level="0"></td>', ''),
        ]
        for html in cases:
            with self.assertRaises(ValueError):
                parse_calendar(html)

    def test_duplicate_tooltip_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            parse_calendar(fixture() + '<tool-tip for="day-0">No contributions on January 1st.</tool-tip>')

    def test_level_must_agree_with_actual_count(self):
        with self.assertRaises(ValueError):
            parse_calendar(fixture().replace('id="day-0" data-level="0"', 'id="day-0" data-level="4"'))

    def test_username_cannot_be_a_path_or_markup(self):
        self.assertEqual(validate_username("tonmoycoder"), "tonmoycoder")
        for username in ["../secret", "x/y", "-bad", "bad-", "<script>", "", "a" * 40]:
            with self.subTest(username=username), self.assertRaises(ValueError):
                validate_username(username)

    @patch("scripts.render_contributions.urlopen")
    def test_fetch_is_public_bounded_and_has_no_authorization(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.geturl.return_value = "https://github.com/users/tonmoycoder/contributions"
        response.headers = {"Content-Type": "text/html; charset=utf-8"}
        response.read.return_value = b"<html>public data</html>"
        self.assertEqual(fetch_calendar("tonmoycoder"), "<html>public data</html>")
        request = urlopen.call_args.args[0]
        self.assertFalse(request.has_header("Authorization"))
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 30)
        self.assertEqual(response.read.call_args.args[0], 2_000_001)

    @patch("scripts.render_contributions.urlopen")
    def test_redirects_non_html_and_oversized_responses_fail(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.geturl.return_value = "https://example.com/not-github"
        with self.assertRaises(ValueError):
            fetch_calendar("tonmoycoder")
        response.geturl.return_value = "https://github.com/users/tonmoycoder/contributions"
        response.headers = {"Content-Type": "application/json"}
        with self.assertRaises(ValueError):
            fetch_calendar("tonmoycoder")
        response.headers = {"Content-Type": "text/html"}
        response.read.return_value = b"x" * 2_000_001
        with self.assertRaises(ValueError):
            fetch_calendar("tonmoycoder")


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.days = parse_calendar(fixture(counts={80: 1, 160: 8, 364: 24}))

    def test_svg_is_valid_and_every_real_day_is_represented_once(self):
        root = ET.fromstring(render_svg("tonmoycoder", self.days))
        buildings = [e for e in root.iter() if "data-date" in e.attrib]
        self.assertEqual(len(buildings), 365)
        self.assertEqual(len({e.attrib["data-date"] for e in buildings}), 365)
        self.assertEqual(sum(int(e.attrib["data-count"]) for e in buildings), 33)
        self.assertEqual(root.attrib["viewBox"], "0 0 1280 560")
        for element in root.iter():
            self.assertNotIn(element.tag.split("}")[-1], ["script", "foreignObject", "image"])
            self.assertFalse(any(k.lower().startswith("on") for k in element.attrib))

    def test_all_zero_year_is_valid_and_has_no_fake_buildings(self):
        root = ET.fromstring(render_svg("tonmoycoder", parse_calendar(fixture())))
        heights = [float(e.attrib["data-height"]) for e in root.iter() if "data-height" in e.attrib]
        self.assertEqual(sum(heights), 0)

    def test_height_is_monotonic_and_deterministic(self):
        self.assertEqual(height_for(0, 0), 0)
        self.assertLess(height_for(1, 100), height_for(8, 100))
        self.assertLess(height_for(8, 100), height_for(100, 100))
        self.assertLessEqual(height_for(100, 100), 86)
        self.assertEqual(render_svg("tonmoycoder", self.days), render_svg("tonmoycoder", list(reversed(self.days))))

    def test_reduced_motion_and_accessible_summary_exist(self):
        svg = render_svg("tonmoycoder", self.days)
        self.assertIn("prefers-reduced-motion:reduce", svg)
        self.assertIn('aria-labelledby="title desc"', svg)
        self.assertIn("33 contributions", svg)
        self.assertIn("not code quality", svg)

    def test_write_is_idempotent_and_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "assets" / "calendar.svg"
            self.assertTrue(write_svg(output, "first"))
            timestamp = output.stat().st_mtime_ns
            self.assertFalse(write_svg(output, "first"))
            self.assertEqual(output.stat().st_mtime_ns, timestamp)
            with patch.object(Path, "replace", side_effect=OSError("disk error")):
                with self.assertRaises(OSError):
                    write_svg(output, "second")
            self.assertEqual(output.read_text(), "first")
            self.assertEqual(list(output.parent.glob("*.tmp")), [])

    def test_failed_generation_retains_previous_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            output, html = Path(tmp) / "calendar.svg", Path(tmp) / "error.html"
            output.write_text("previous good SVG")
            html.write_text("rate limited")
            with patch("sys.stderr", new=io.StringIO()):
                status = main(["--input", str(html), "--output", str(output)])
            self.assertEqual(status, 1)
            self.assertEqual(output.read_text(), "previous good SVG")


if __name__ == "__main__":
    unittest.main()
