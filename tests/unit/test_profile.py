"""Perfis, localizadores e chave de fragmento (BL-04; TC-PRS-08)."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from kos.parsing.normalize import normalize
from kos.parsing.profile import Locator, Profile, fragment_key, register_profile
from kos.store import schema

BASE = Profile("md-native", "markdown-it-py", "3.0.0", "1", {"max_section_lines": 60})
LOC = Locator("text", start_byte=0, end_byte=10, start_line=1, end_line=2)


class ProfileTest(unittest.TestCase):
    def test_fingerprint_is_stable_and_order_independent(self):
        same = Profile("md-native", "markdown-it-py", "3.0.0", "1", {"max_section_lines": 60})
        self.assertEqual(BASE.fingerprint, same.fingerprint)
        a = Profile("p", "x", "1", "1", {"a": 1, "b": 2})
        b = Profile("p", "x", "1", "1", {"b": 2, "a": 1})
        self.assertEqual(a.fingerprint, b.fingerprint)

    def test_prs08_any_field_change_changes_fingerprint_and_keys(self):
        variants = [
            Profile("md-native", "markdown-it-py", "3.0.0", "1", {"max_section_lines": 61}),
            Profile("md-native", "markdown-it-py", "3.0.1", "1", {"max_section_lines": 60}),
            Profile("md-native", "markdown-it-py", "3.0.0", "2", {"max_section_lines": 60}),
            Profile("md-native", "markdown-it-py", "3.0.0", "1", {"max_section_lines": 60}, "g1"),
        ]
        base_key = fragment_key("a" * 40, BASE.fingerprint, LOC)
        for v in variants:
            with self.subTest(v=v):
                self.assertNotEqual(v.fingerprint, BASE.fingerprint)
                self.assertNotEqual(fragment_key("a" * 40, v.fingerprint, LOC), base_key)

    def test_fragment_key_depends_on_blob_and_locator(self):
        k = fragment_key("a" * 40, BASE.fingerprint, LOC)
        self.assertEqual(k, fragment_key("a" * 40, BASE.fingerprint,
                                         Locator("text", start_byte=0, end_byte=10, start_line=1, end_line=2)))
        self.assertNotEqual(k, fragment_key("b" * 40, BASE.fingerprint, LOC))
        self.assertNotEqual(k, fragment_key("a" * 40, BASE.fingerprint,
                                            Locator("text", start_byte=0, end_byte=11, start_line=1, end_line=2)))
        self.assertRegex(k, r"^[0-9a-f]{64}$")

    def test_locator_validation(self):
        for kwargs in ({"type": "linha"}, {"type": "text"}, {"type": "text", "start_byte": 5, "end_byte": 4},
                       {"type": "page", "page_start": 3, "page_end": 2},
                       {"type": "text", "start_byte": 0, "end_byte": 1, "start_line": 3, "end_line": 2}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Locator(**kwargs)
        Locator("page", page_start=1, page_end=1)

    def test_register_profile_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            schema.initialize(Path(tmp))
            conn = sqlite3.connect(Path(tmp) / "index.sqlite")
            first = register_profile(conn, BASE)
            self.assertEqual(register_profile(conn, BASE), first)
            other = register_profile(conn, Profile("x", "y", "1", "1"))
            self.assertNotEqual(other, first)
            conn.close()


class NormalizeTest(unittest.TestCase):
    def test_line_endings_bom_and_nfc(self):
        self.assertEqual(normalize(b"a\r\nb\rc\n"), "a\nb\nc\n")
        self.assertEqual(normalize("﻿x".encode()), "x")
        self.assertEqual(normalize("ação".encode()), "ação")

    def test_invalid_utf8(self):
        from kos.errors import KosError
        with self.assertRaises(KosError) as ctx:
            normalize(b"\xff")
        self.assertEqual(ctx.exception.code, "E_DECODE")


if __name__ == "__main__":
    unittest.main()
