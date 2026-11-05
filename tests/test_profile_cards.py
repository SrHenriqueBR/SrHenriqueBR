"""Testes offline dos cartões do perfil; não há rede nem token aqui."""
import importlib.util
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "profile_stats", ROOT / "scripts" / "profile_stats.py"
)
STATS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STATS)


class ProfileCardsTests(unittest.TestCase):
    def test_valid_stats_svg(self):
        svg = STATS.stats_svg(
            commit_count=42, total_contributions=60,
            repo_count=6, stars=2, updated="05/11/2026")
        root = ElementTree.fromstring(svg)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertIn("42", svg)
        self.assertIn("Commits públicos", svg)
        self.assertIn("6", svg)
        self.assertIn("60", svg)

    def test_unavailable_commits_are_not_assumed_zero(self):
        svg = STATS.stats_svg(
            commit_count=None, total_contributions=None,
            repo_count=6, stars=0, updated="05/11/2026")
        ElementTree.fromstring(svg)
        self.assertIn("dado indisponível", svg)
        self.assertIn("—", svg)

    def test_languages_are_escaped_and_percentages_stay_valid(self):
        svg = STATS.languages_svg(
            Counter({"Python": 190, "C++": 75, "A&B": 15}), "05/11/2026")
        ElementTree.fromstring(svg)
        self.assertIn("A&amp;B", svg)
        self.assertIn("Python", svg)
        self.assertIn("67.9%", svg)

    def test_cards_stored_locally_and_linked_to_readme(self):
        md = (ROOT / "README.md").read_text(encoding="utf-8")
        for path in ("assets/github-stats.svg", "assets/top-languages.svg"):
            svg = (ROOT / path).read_text(encoding="utf-8")
            ElementTree.fromstring(svg)
            self.assertIn(path, md)
        self.assertNotIn("github-readme-stats.vercel.app", md)

    def test_does_not_download_private_repositories(self):
        source = (ROOT / "scripts" / "profile_stats.py").read_text(encoding="utf-8")
        self.assertIn("/users/{LOGIN}/repos?", source)
        self.assertIn("not repo.get", source)
        self.assertNotIn('type": "all"', source)


if __name__ == "__main__":
    unittest.main()
