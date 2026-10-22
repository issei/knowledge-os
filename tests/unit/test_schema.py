"""O DDL empacotado é válido e é o mesmo da especificação (BL-01)."""

import sqlite3
import unittest
from unittest import mock

from kos.errors import KosError
from kos.store import schema
from tests.helpers import spec_sql_blocks


def _columns(ddl: str) -> dict[str, list[tuple]]:
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(ddl)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        return {t: conn.execute(f"PRAGMA table_info({t})").fetchall() for t in tables}
    finally:
        conn.close()


class SchemaTest(unittest.TestCase):
    def test_packaged_ddl_matches_spec(self):
        spec_index, spec_audit = spec_sql_blocks()
        self.assertEqual(_columns(schema.load_ddl("index.sql")), _columns(spec_index))
        self.assertEqual(_columns(schema.load_ddl("audit.sql")), _columns(spec_audit))

    def test_ddl_applies_without_foreign_key_violations(self):
        for _, ddl_name, meta in schema.DATABASES:
            with self.subTest(ddl=ddl_name):
                conn = sqlite3.connect(":memory:")
                conn.executescript(schema.load_ddl(ddl_name))
                self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertTrue(conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE name = ?", (meta,)).fetchone())
                conn.close()

    def test_no_vector_columns(self):
        # TC-ARQ-01 (parte do esquema): nenhuma coluna reserva espaço para vetores.
        for _, ddl_name, _ in schema.DATABASES:
            for table, cols in _columns(schema.load_ddl(ddl_name)).items():
                for col in cols:
                    self.assertNotRegex(col[1].lower(), r"embed|vector", f"{table}.{col[1]}")

    def test_require_fts5_passes_here(self):
        schema.require_fts5()

    def test_missing_fts5_raises_catalog_error(self):
        fake = mock.MagicMock()
        fake.execute.side_effect = sqlite3.OperationalError("no such module: fts5")
        with mock.patch.object(schema.sqlite3, "connect", return_value=fake):
            with self.assertRaises(KosError) as ctx:
                schema.require_fts5()
        self.assertEqual(ctx.exception.code, "E_FTS5_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
