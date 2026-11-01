from html.parser import HTMLParser
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class ProfileHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors, self.images, self.sources, self.anchors = [], [], [], [], []

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if "style" in attr or "class" in attr or any(k.lower().startswith("on") for k in attr):
            self.errors.append(f"Unsupported README styling/behavior on {tag}")
        if tag in {"script", "iframe", "canvas"}:
            self.errors.append(f"Unsupported README element: {tag}")
        if tag == "img":
            self.images.append(attr)
        if tag == "source":
            self.sources.append(attr)
        if tag == "a":
            self.anchors.append(attr.get("href", ""))
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"Unbalanced closing tag: {tag}")
        else:
            self.stack.pop()


class ProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readme = (ROOT / "README.md").read_text()
        cls.html = ProfileHTML()
        cls.html.feed(cls.readme)
        cls.html.close()

    def test_markup_is_balanced_and_github_compatible(self):
        self.assertEqual(self.html.errors, [])
        self.assertEqual(self.html.stack, [])
        self.assertNotIn("- ****", self.readme)
        self.assertNotRegex(self.readme, r"(?m)^!\s*$")

    def test_readme_images_are_local_real_and_described(self):
        self.assertGreaterEqual(len(self.html.images), 5)
        for attr in self.html.images:
            self.assertTrue(attr.get("alt", "").strip())
            self.assertTrue(attr["src"].startswith("./"))
            self.assertTrue((ROOT / attr["src"]).is_file(), attr["src"])
        for attr in self.html.sources:
            self.assertEqual(attr["media"], "(max-width: 640px)")
            self.assertTrue((ROOT / attr["srcset"]).is_file())

    def test_all_navigation_links_match_headings(self):
        headings = re.findall(r"^## (.+)$", self.readme, re.M)
        slugs = {re.sub(r"[^\w\- ]", "", h).lower().replace(" ", "-") for h in headings}
        for href in self.html.anchors:
            if href.startswith("#"):
                self.assertIn(href[1:], slugs)

    def test_no_copied_remote_widgets_or_security_superlatives(self):
        for old in ["shields.io", "socialify", "skillicons", "capsule-render", "github-readme-stats", "github-profile-trophy", "dribbble.com/users/", "1999AZZAR", "Military-grade", "MITM-proof"]:
            self.assertNotIn(old, self.readme)
        self.assertIn("does not claim an independent security audit", self.readme)
        self.assertIn("Deployment notes", self.readme)

    def test_all_vector_assets_are_safe_accessible_and_self_contained(self):
        assets = list((ROOT / "assets").glob("*.svg")) + list((ROOT / "profile-3d-contrib").glob("*.svg"))
        self.assertEqual(len(assets), 6)
        for path in assets:
            with self.subTest(asset=path.name):
                text = path.read_text()
                root = ET.fromstring(text)
                self.assertEqual(root.attrib["role"], "img")
                self.assertIn("aria-labelledby", root.attrib)
                self.assertIn("prefers-reduced-motion:reduce", text)
                ids = [el.attrib["id"] for el in root.iter() if "id" in el.attrib]
                self.assertEqual(len(ids), len(set(ids)))
                self.assertIn("title", ids)
                self.assertIn("desc", ids)
                for reference in re.findall(r"url\(#([^)]+)\)", text):
                    self.assertIn(reference, ids)
                for el in root.iter():
                    self.assertNotIn(el.tag.split("}")[-1], ["script", "foreignObject", "image"])
                    self.assertFalse(any(key.lower().startswith("on") for key in el.attrib))
                    self.assertFalse(any(key.endswith("href") for key in el.attrib))
                self.assertLess(path.stat().st_size, 400_000)

    def test_all_actions_are_pinned_to_full_commit_shas(self):
        workflows = list((ROOT / ".github/workflows").glob("*.yml"))
        self.assertEqual(len(workflows), 2)
        for path in workflows:
            text = path.read_text()
            for action in re.findall(r"uses:\s*(\S+)", text):
                self.assertRegex(action, r"^actions/checkout@[a-f0-9]{40}$")
            self.assertIn("persist-credentials: false", text)
            self.assertNotIn("pull_request_target", text)
            self.assertNotRegex(text, r"secrets\.(PAT|TOKEN|GH_PAT|PERSONAL_ACCESS_TOKEN)\b")

    def test_publishing_workflow_is_not_triggered_by_prs_or_pushes(self):
        workflow = (ROOT / ".github/workflows/profile-3d.yml").read_text()
        self.assertNotIn("pull_request", workflow)
        self.assertNotRegex(workflow, r"(?m)^  push:")
        self.assertIn('cron: "25 18 * * *"', workflow)
        self.assertIn("GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}", workflow)
        self.assertIn('push origin "HEAD:${PROFILE_BRANCH}"', workflow)
        self.assertNotIn("--force", workflow)
        self.assertIn("permissions: {}", workflow)

    def test_pr_checks_are_read_only(self):
        workflow = (ROOT / ".github/workflows/check-profile.yml").read_text()
        self.assertIn("pull_request:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("secrets.", workflow)


if __name__ == "__main__":
    unittest.main()
