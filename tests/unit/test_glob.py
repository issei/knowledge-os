"""Padrões de caminho estilo gitignore usados pela política."""

import unittest

from kos.discovery.glob import matches


class GlobTest(unittest.TestCase):
    def test_patterns(self):
        cases = [
            ("**", "a/b/c.md", True),
            ("**/*.md", "a.md", True),
            ("**/*.md", "a/b/c.md", True),
            ("*.md", "a/b.md", False),
            ("src/en/**", "src/en/x/y.html", True),
            ("src/en/**", "src/eng/x.html", False),
            ("**/ADR-*.md", "docs/apresentação/ADR-ap-001.md", True),
            ("docs/?.md", "docs/a.md", True),
            ("docs/?.md", "docs/ab.md", False),
            ("a.b", "aXb", False),
        ]
        for pattern, path, expected in cases:
            with self.subTest(pattern=pattern, path=path):
                self.assertEqual(matches(path, pattern), expected)

    def test_invalid(self):
        for bad in ("", "/abs"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                matches("x", bad)


if __name__ == "__main__":
    unittest.main()
