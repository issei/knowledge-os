"""Testes de contrato de `kos init` (BL-01; TC-CLI-01 e TC-CLI-02 para este comando)."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tests.helpers import run_kos


class InitCommandTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name) / "kos-home"

    def tearDown(self):
        self._tmp.cleanup()

    def _init_json(self):
        proc = run_kos("init", "--home", str(self.home), "--json")
        return proc, (json.loads(proc.stdout) if proc.stdout.strip() else None)

    def test_creates_both_databases(self):
        proc, out = self._init_json()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(out["schema"], "kos.init.v1")
        self.assertEqual({d["name"]: d["status"] for d in out["databases"]},
                         {"index.sqlite": "created", "audit.sqlite": "created"})
        for name, meta in (("index.sqlite", "index_meta"), ("audit.sqlite", "audit_meta")):
            conn = sqlite3.connect(self.home / name)
            self.assertEqual(conn.execute(
                f"SELECT value FROM {meta} WHERE key='schema_version'").fetchone()[0], "1")
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            conn.close()
        leftovers = [p.name for p in self.home.iterdir() if ".tmp-" in p.name]
        self.assertEqual(leftovers, [])

    def test_is_idempotent(self):
        self._init_json()
        conn = sqlite3.connect(self.home / "index.sqlite")
        created_at = conn.execute(
            "SELECT value FROM index_meta WHERE key='created_at'").fetchone()[0]
        conn.close()
        proc, out = self._init_json()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual({d["status"] for d in out["databases"]}, {"existing"})
        conn = sqlite3.connect(self.home / "index.sqlite")
        self.assertEqual(conn.execute(
            "SELECT value FROM index_meta WHERE key='created_at'").fetchone()[0], created_at)
        conn.close()

    def test_schema_mismatch_is_execution_error(self):
        self._init_json()
        conn = sqlite3.connect(self.home / "index.sqlite")
        conn.execute("UPDATE index_meta SET value='0' WHERE key='schema_version'")
        conn.commit()
        conn.close()
        proc, out = self._init_json()
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(out, {"schema": "kos.error.v1", "code": "E_SCHEMA_MISMATCH",
                               "message": out["message"]})

    def test_foreign_file_is_schema_mismatch(self):
        self.home.mkdir(parents=True)
        (self.home / "index.sqlite").write_text("não é um banco")
        proc, out = self._init_json()
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(out["code"], "E_SCHEMA_MISMATCH")

    def test_unwritable_home(self):
        self.home.parent.mkdir(parents=True, exist_ok=True)
        self.home.write_text("arquivo no lugar do diretório")
        proc, out = self._init_json()
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(out["code"], "E_STORE_UNWRITABLE")

    def test_usage_error_exits_1(self):
        proc = run_kos("comando-inexistente")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("erro de uso", proc.stderr)

    def test_human_output_without_json(self):
        proc = run_kos("init", "--home", str(self.home))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("criado", proc.stdout)


if __name__ == "__main__":
    unittest.main()
