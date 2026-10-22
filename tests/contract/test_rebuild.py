"""Testes de contrato do rebuild (CTR-05, TC-REB-02, TC-REB-03, TC-AUD-02; BL-09)."""

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from kos.discovery import Policy
from kos.errors import KosError
from kos.ingest import ingest_full
from kos.parsing import json_doc
from kos.rebuild import rebuild
from kos.store.dump import digest, logical_dump
from tests.fixtures.gitbuilder import Commit, build_repo
from tests.helpers import run_kos

POLICY_DICT = {"policy_id": "teste", "version": 1, "include": ["**"], "exclude": [],
               "max_bytes": 100_000, "generated": [], "kind_rules": []}
POLICY = Policy.from_dict(POLICY_DICT)


class RebuildTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.root, self.home = base / "repo", base / "home"
        _, self.commits = build_repo(self.root, [
            Commit("c1", files={"a.md": "# A\n\nação\n", "b.json": '{"x": {"y": 1}}\n'}),
            Commit("c2", files={"a.md": "# A\n\nação nova\n", "c.mjs": "const fooBar = 1;\n"}),
        ])
        for commit in self.commits:
            ingest_full(self.home, self.root, rev=commit, policy=POLICY, repo_name="r")

    def tearDown(self):
        self._tmp.cleanup()

    def _digest(self):
        conn = sqlite3.connect(f"file:{self.home / 'index.sqlite'}?mode=ro", uri=True)
        try:
            return digest(logical_dump(conn))
        finally:
            conn.close()

    def _audit_hash(self):
        return hashlib.sha256((self.home / "audit.sqlite").read_bytes()).hexdigest()

    def test_reb02_rebuild_reproduz_o_conteudo_logico(self):
        before, audit = self._digest(), self._audit_hash()
        first = rebuild(self.home, {"r": self.root}, policy=POLICY)
        self.assertEqual(first.status, "succeeded")
        self.assertEqual([r["commit_oid"] for r in first.revisions], self.commits)
        self.assertEqual(first.old_digest, before)
        self.assertEqual(first.new_digest, before)
        self.assertEqual((first.fragments_added, first.fragments_removed), ({}, {}))
        second = rebuild(self.home, {"r": self.root}, policy=POLICY)
        self.assertEqual(second.new_digest, before)
        self.assertEqual(self._digest(), before)
        self.assertEqual(self._audit_hash(), audit)  # TC-AUD-02
        self.assertEqual([p.name for p in self.home.iterdir() if p.name.startswith(".rebuild")], [])
        modes = sqlite3.connect(self.home / "index.sqlite").execute("SELECT DISTINCT mode FROM ingest_run")
        self.assertEqual(modes.fetchall(), [("rebuild",)])

    def test_indice_apagado_reconstroi_com_rev(self):
        before = self._digest()
        (self.home / "index.sqlite").unlink()
        revs = [("r", c) for c in self.commits]
        result = rebuild(self.home, {"r": self.root}, policy=POLICY, revisions=revs)
        self.assertIsNone(result.old_digest)
        self.assertEqual(result.new_digest, before)

    def test_indice_de_outro_esquema_e_substituido(self):
        (self.home / "index.sqlite").write_bytes(b"isto nao e um banco sqlite")
        revs = [("r", c) for c in self.commits]
        result = rebuild(self.home, {"r": self.root}, policy=POLICY, revisions=revs)
        self.assertIsNone(result.old_digest)
        self.assertEqual(result.status, "succeeded")

    def test_sem_revisoes_e_sem_indice(self):
        (self.home / "index.sqlite").unlink()
        with self.assertRaises(KosError) as ctx:
            rebuild(self.home, {"r": self.root}, policy=POLICY)
        self.assertEqual(ctx.exception.code, "E_NO_INDEXED_REVISION")

    def test_reb03_commit_ausente_deixa_partial(self):
        revs = [("r", self.commits[0]), ("r", "f" * 40), ("outro", self.commits[1])]
        result = rebuild(self.home, {"r": self.root}, policy=POLICY, revisions=revs)
        self.assertEqual(result.status, "partial")
        self.assertEqual([m["code"] for m in result.missing], ["E_COMMIT_NOT_FOUND", "E_REPO_NOT_FOUND"])
        self.assertEqual([r["commit_oid"] for r in result.revisions], [self.commits[0]])

    def test_falha_antes_da_troca_preserva_o_indice_antigo(self):
        before = self._digest()
        with self.assertRaises(KosError):
            rebuild(self.home, {"r": self.root}, policy=POLICY, revisions=[("r", "f" * 40)])
        self.assertEqual(self._digest(), before)
        self.assertEqual([p.name for p in self.home.iterdir() if p.name.startswith(".rebuild")], [])

    def test_relatorio_de_diferencas_por_perfil(self):
        no_json = Policy.from_dict(dict(POLICY_DICT, exclude=["**/*.json"]))
        result = rebuild(self.home, {"r": self.root}, policy=no_json)
        self.assertNotEqual(result.new_digest, result.old_digest)
        self.assertEqual(result.fragments_removed, {json_doc.PROFILE.fingerprint: 1})
        self.assertEqual(result.fragments_added, {})

    def test_cli(self):
        policy = Path(self._tmp.name) / "policy.json"
        policy.write_text(json.dumps(POLICY_DICT))
        proc = run_kos("rebuild", "--repo", f"r={self.root}", "--policy", str(policy),
                       "--home", str(self.home), "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema"], "kos.rebuild.v1")
        self.assertEqual(payload["old_digest"], payload["new_digest"])
        bad = run_kos("rebuild", "--repo", "sem-igual", "--home", str(self.home))
        self.assertEqual(bad.returncode, 1)
        partial = run_kos("rebuild", "--repo", f"r={self.root}", "--rev", f"r@{self.commits[0]}",
                          "--rev", f"r@{'f' * 40}", "--home", str(self.home))
        self.assertEqual(partial.returncode, 4, partial.stderr)


if __name__ == "__main__":
    unittest.main()
