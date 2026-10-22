"""Testes de contrato da ingestão full (CTR-03 modo full, CTR-10; BL-08).

TC-INC-03 (falha em um arquivo → partial), TC-INC-05 (execução morta → aborted),
TC-AUD-03 (erro registrado com stage, código e caminho), mais E_LOCKED,
manifesto completo, reaproveitamento e fragmentos verificáveis contra o blob.
"""

import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from kos.discovery import Policy
from kos.errors import ERROR_CODES, KosError
from kos.ingest import ingest_full, split_identifiers
from kos.parsing import registry
from kos.parsing.profile import Locator, fragment_key
from tests.fixtures.gitbuilder import Commit, build_repo
from tests.helpers import run_kos

POLICY = Policy.from_dict({
    "policy_id": "teste", "version": 1, "include": ["**"], "exclude": [],
    "max_bytes": 100_000, "generated": ["en/**"],
    "kind_rules": [{"pattern": "**/*.md", "kind": "doc"}, {"pattern": "**/*.mjs", "kind": "code"}],
})

FILES = {
    "docs/guia.md": "# Guia\n\nComo publicar a ação.\n\n## Detalhes\n\nTexto.\n",
    "en/guia.md": "# Guia\n\nComo publicar a ação.\n\n## Detalhes\n\nTexto.\n",  # mesmo blob
    "package.json": '{\n  "scripts": {\n    "gate": "npm test"\n  }\n}\n',
    "src/gen.mjs": "export function pfBlockFill(x) {\n  return x;\n}\n",
    "pagina.html": "<h1>Título</h1><p>P95 &lt; 800ms</p>",
    "imagem.png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01",
}


class IngestTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.root, self.home = base / "repo", base / "home"

    def tearDown(self):
        self._tmp.cleanup()

    def _build(self, files, **extra):
        _, oids = build_repo(self.root, [Commit("base", files=files, **extra)])
        return oids[-1]

    def _db(self):
        conn = sqlite3.connect(self.home / "index.sqlite")
        self.addCleanup(conn.close)
        return conn

    def test_full_indexa_tudo_e_e_consultavel(self):
        commit = self._build(FILES, symlinks={"link.md": "docs/guia.md"})
        result = ingest_full(self.home, self.root, rev=commit, policy=POLICY, repo_name="r")
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.counts["discovered"], 7)
        self.assertEqual(result.counts["eligible"], 5)
        self.assertEqual(result.counts["processed"], 5)
        db = self._db()
        manifest = dict(db.execute(
            "SELECT a.path_text, coalesce(m.exclusion_rule, m.eligibility) FROM revision_manifest m"
            " JOIN artifact a USING (artifact_id)").fetchall())
        self.assertEqual(manifest, {
            "docs/guia.md": "eligible", "en/guia.md": "eligible", "package.json": "eligible",
            "src/gen.mjs": "eligible", "pagina.html": "eligible",
            "imagem.png": "binary_unsupported", "link.md": "symlink_not_followed",
        })
        hits = db.execute(
            "SELECT a.path_text FROM fragment_fts JOIN fragment f ON f.fragment_id = fragment_fts.rowid"
            " JOIN artifact_version v USING (version_id) JOIN artifact a USING (artifact_id)"
            " WHERE fragment_fts MATCH 'acao' ORDER BY a.path_text").fetchall()
        self.assertEqual(hits, [("docs/guia.md",), ("en/guia.md",)])  # sem acento também acha
        self.assertEqual(db.execute("SELECT is_generated FROM artifact_version v JOIN artifact a"
                                    " USING (artifact_id) WHERE path_text = 'en/guia.md'").fetchone(), (1,))
        self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_fragmentos_verificaveis_e_chave_determinista(self):
        commit = self._build(FILES)
        ingest_full(self.home, self.root, rev=commit, policy=POLICY, repo_name="r")
        rows = self._db().execute(
            "SELECT a.path_bytes, v.blob_oid, v.media_type, p.profile_fingerprint, f.fragment_key, f.text,"
            " l.locator_type, l.start_byte, l.end_byte, l.start_line, l.end_line, l.struct_path"
            " FROM fragment f JOIN fragment_locator l USING (fragment_id)"
            " JOIN artifact_version v USING (version_id) JOIN artifact a USING (artifact_id)"
            " JOIN processing_profile p USING (profile_id)").fetchall()
        self.assertTrue(rows)
        for path, oid, media, fp, key, text, ltype, sb, eb, sl, el, sp in rows:
            blob = subprocess.run(["git", "-C", str(self.root), "cat-file", "blob", oid],
                                  capture_output=True, check=True).stdout
            self.assertEqual(registry.expected_text(media, blob[sb:eb]), text)
            loc = Locator(ltype, start_byte=sb, end_byte=eb, start_line=sl, end_line=el, struct_path=sp)
            self.assertEqual(fragment_key("r", path, oid, fp, loc), key)
        paths = {r[4]: r[0] for r in rows}
        self.assertEqual(len(paths), len(rows))  # mesmo blob em dois caminhos, chaves diferentes

    def test_segunda_execucao_reaproveita(self):
        commit = self._build(FILES)
        first = ingest_full(self.home, self.root, rev=commit, policy=POLICY, repo_name="r")
        second = ingest_full(self.home, self.root, rev=commit, policy=POLICY, repo_name="r")
        self.assertEqual((second.counts["reused"], second.counts["processed"]), (5, 0))
        db = self._db()
        self.assertEqual(db.execute("SELECT count(*) FROM fragment").fetchone()[0], first.counts["fragments"])
        self.assertEqual(db.execute("SELECT count(*) FROM revision_manifest").fetchone()[0], 6)

    def test_inc03_falha_em_um_arquivo_deixa_partial(self):
        files = dict(FILES, **{"quebrado.md": b"# T\xff\xfe texto latin-1 \xe7\n"})
        commit = self._build(files)
        result = ingest_full(self.home, self.root, rev=commit, policy=POLICY, repo_name="r")
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.counts["failed"], 1)
        db = self._db()
        err = db.execute("SELECT stage, error_code, severity, path_text FROM processing_error").fetchall()
        self.assertEqual(err, [("decode", "E_DECODE", "error", "quebrado.md")])  # TC-AUD-03
        status, count = db.execute(
            "SELECT vp.status, vp.fragment_count FROM version_processing vp JOIN artifact_version v"
            " USING (version_id) JOIN artifact a USING (artifact_id) WHERE a.path_text = 'quebrado.md'"
        ).fetchone()
        self.assertEqual((status, count), ("failed", 0))
        self.assertTrue(db.execute("SELECT count(*) FROM fragment_fts WHERE fragment_fts MATCH 'publicar'")
                        .fetchone()[0])
        for (code,) in db.execute("SELECT error_code FROM processing_error"):
            self.assertIn(code, ERROR_CODES)

    def test_sintaxe_invalida_e_aviso_nao_falha(self):
        commit = self._build({"conf.json": '{\n  // comentário\n  "a": 1\n}\n'})
        result = ingest_full(self.home, self.root, rev=commit, policy=POLICY, repo_name="r")
        self.assertEqual((result.status, result.counts["warnings"]), ("succeeded", 1))
        self.assertEqual(result.errors[0]["code"], "E_PARSE_SYNTAX")
        self.assertEqual(result.errors[0]["severity"], "warning")

    def test_submodulo_entra_no_manifesto(self):
        commit = self._build({"a.md": "a\n"}, submodules={"vendor/lib": "2" * 40})
        ingest_full(self.home, self.root, rev=commit, policy=POLICY, repo_name="r")
        row = self._db().execute(
            "SELECT m.exclusion_rule, v.content_sha256, v.byte_size FROM revision_manifest m"
            " JOIN artifact_version v USING (version_id) JOIN artifact a ON a.artifact_id = m.artifact_id"
            " WHERE a.path_text = 'vendor/lib'").fetchone()
        self.assertEqual(row, ("submodule_not_followed", "gitlink:" + "2" * 40, 0))

    def test_inc05_execucao_morta_vira_aborted(self):
        commit = self._build(FILES)
        ingest_full(self.home, self.root, rev=commit, policy=POLICY, repo_name="r")
        with sqlite3.connect(self.home / "index.sqlite") as db:
            db.execute("INSERT INTO ingest_run(run_uuid, repo_id, mode, target_revision_id, policy_sha256,"
                       " tool_version, started_at, status) VALUES ('morta', 1, 'full', 1, 'x', 'x', 'x', 'running')")
        ingest_full(self.home, self.root, rev=commit, policy=POLICY, repo_name="r")
        status = self._db().execute("SELECT status FROM ingest_run WHERE run_uuid = 'morta'").fetchone()
        self.assertEqual(status, ("aborted",))

    def test_outra_ingestao_em_curso_da_e_locked(self):
        commit = self._build(FILES)
        ingest_full(self.home, self.root, rev=commit, policy=POLICY, repo_name="r")
        holder = sqlite3.connect(self.home / "index.sqlite", isolation_level=None)
        self.addCleanup(holder.close)
        holder.execute("BEGIN IMMEDIATE")
        with self.assertRaises(KosError) as ctx:
            ingest_full(self.home, self.root, rev=commit, policy=POLICY, repo_name="r")
        self.assertEqual(ctx.exception.code, "E_LOCKED")
        holder.execute("ROLLBACK")

    def test_cli_json_e_codigo_de_saida(self):
        commit = self._build(dict(FILES, **{"quebrado.md": b"\xff\n"}))
        policy = Path(self._tmp.name) / "policy.json"
        policy.write_text(json.dumps({
            "policy_id": "teste", "version": 1, "include": ["**"], "exclude": [], "max_bytes": 100_000,
            "generated": [], "kind_rules": []}))
        proc = run_kos("ingest", str(self.root), "--rev", commit, "--full", "--name", "r",
                       "--policy", str(policy), "--home", str(self.home), "--json")
        self.assertEqual(proc.returncode, 4, proc.stderr)  # partial
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema"], "kos.ingest.v1")
        self.assertEqual((payload["status"], payload["commit_oid"]), ("partial", commit))
        usage = run_kos("ingest", str(self.root), "--home", str(self.home))
        self.assertEqual(usage.returncode, 1)  # --full é obrigatório até o BL-16

    def test_ident_terms(self):
        self.assertEqual(split_identifiers("export function pfBlockFill(x_y, HTMLParser) {}"),
                         "pf block fill x y html parser")
        self.assertIsNone(split_identifiers("return x;"))


if __name__ == "__main__":
    unittest.main()
