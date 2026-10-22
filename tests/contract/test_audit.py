"""Testes de contrato da auditoria (CTR-10, TC-AUD-01, TC-AUD-05; BL-12)."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from kos import audit
from kos.cite import cite
from kos.discovery import Policy
from kos.errors import KosError
from kos.ingest import ingest_full
from kos.rebuild import rebuild
from tests.fixtures.gitbuilder import Commit, build_repo
from tests.helpers import run_kos

POLICY = Policy.from_dict({"policy_id": "teste", "version": 1, "include": ["**"], "exclude": [],
                           "max_bytes": 100_000, "generated": [], "kind_rules": []})
FILES = {
    "AGENTS.md": "# Regras\n\nO piso de contraste é 7:1 na Camada 3.\n\n## Outra\n\nfim\n",
    "pagina.html": "<h1>Contraste</h1>\n<p>Piso &gt; 7:1</p>\n",
}


class AuditTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.root, self.home = base / "repo", base / "home"
        _, self.commits = build_repo(self.root, [Commit("c1", files=FILES),
                                                 Commit("c2", files={"novo.md": "# Novo\n\ncontraste\n"})])
        ingest_full(self.home, self.root, rev=self.commits[0], policy=POLICY, repo_name="r")

    def tearDown(self):
        self._tmp.cleanup()

    def _audit_rows(self, sql, params=()):
        conn = sqlite3.connect(self.home / "audit.sqlite")
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def _search(self, *args):
        proc = run_kos("search", *args, "--home", str(self.home), "--json")
        return proc, (json.loads(proc.stdout) if proc.stdout else None)

    def test_aud01_each_search_writes_one_event_with_its_results(self):
        proc, out = self._search("contraste", "-k", "5")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        [(interface, question, params)] = self._audit_rows(
            "SELECT interface, question, params_json FROM query_event WHERE query_id = ?", (out["query_id"],))
        self.assertEqual((interface, question), ("cli", "contraste"))
        self.assertEqual(json.loads(params), {"command": "search", "k": 5})
        recorded = self._audit_rows("SELECT rank, fragment_key FROM retrieval_result WHERE query_id = ?"
                                    " ORDER BY rank", (out["query_id"],))
        self.assertEqual(recorded, [(h["rank"], h["fragment_key"]) for h in out["results"]])
        self.assertTrue(recorded)
        self._search("camada")
        self.assertEqual(self._audit_rows("SELECT count(*) FROM query_event"), [(2,)])

    def test_failed_search_still_has_its_event(self):
        proc, out = self._search("!!! ???")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(out["code"], "E_QUERY_EMPTY")
        self.assertEqual(self._audit_rows("SELECT question FROM query_event"), [("!!! ???",)])
        self.assertEqual(self._audit_rows("SELECT count(*) FROM retrieval_result"), [(0,)])

    def test_search_without_index_does_not_create_one(self):
        empty = Path(self._tmp.name) / "vazio"
        proc = run_kos("search", "x", "--home", str(empty), "--json")
        self.assertEqual(json.loads(proc.stdout)["code"], "E_NO_INDEXED_REVISION")
        self.assertFalse((empty / "index.sqlite").exists())
        self.assertTrue((empty / "audit.sqlite").exists())

    def test_fingerprint_follows_content_not_runs(self):
        before = audit.index_fingerprint(self.home)
        rebuild(self.home, {"r": self.root}, policy=POLICY)
        self.assertEqual(audit.index_fingerprint(self.home), before)
        ingest_full(self.home, self.root, rev=self.commits[1], policy=POLICY, repo_name="r")
        self.assertNotEqual(audit.index_fingerprint(self.home), before)

    def _cited_query(self):
        query_id, result = audit.audited_search(self.home, "contraste piso", interface="bench")
        keys = [h.fragment_key for h in result.results if h.path_text in ("AGENTS.md", "pagina.html")]
        citations = cite(self.home, keys, repos={"r": self.root})
        audit.record_citations(self.home, query_id, citations, claim_ids={1: ["a1"]})
        return query_id, citations

    def test_aud05_audited_citation_reverifies_without_index(self):
        query_id, citations = self._cited_query()
        self.assertEqual({c.verification for c in citations}, {"verified_exact", "verified_normalized"})
        (self.home / "index.sqlite").unlink()
        checks = audit.reverify(self.home, query_id, {"r": self.root})
        self.assertEqual([(c.verification, c.recorded) for c in checks],
                         [(c.verification, c.verification) for c in citations])
        [(claims,)] = self._audit_rows("SELECT claim_ids FROM citation_record WHERE citation_no = 1")
        self.assertEqual(json.loads(claims), ["a1"])

        proc = run_kos("audit", "verify", query_id, "--repo", f"r={self.root}", "--home", str(self.home), "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out["schema"], "kos.audit.verify.v1")
        self.assertEqual(len(out["citations"]), len(citations))

    def test_reverify_against_wrong_clone_is_unverified(self):
        query_id, _ = self._cited_query()
        _, _ = build_repo(Path(self._tmp.name) / "outro", [Commit("x", files={"x.md": "x\n"})])
        checks = audit.reverify(self.home, query_id, {"r": Path(self._tmp.name) / "outro"})
        self.assertTrue(checks)
        for c in checks:
            self.assertEqual(c.verification, "unverified")
            self.assertTrue(c.note.startswith("E_BLOB_UNREADABLE"))
        proc = run_kos("audit", "verify", query_id, "--repo", f"r={Path(self._tmp.name) / 'outro'}",
                       "--home", str(self.home))
        self.assertIn("não verificada", proc.stdout)

    def test_invalid_citation_is_not_recorded(self):
        query_id, citations = self._cited_query()
        bad = citations[0]
        bad.commit_oid = bad.commit_oid[:12]
        with self.assertRaises(ValueError):
            audit.record_citations(self.home, audit.start_query(
                self.home, interface="cli", question="q", params={}), [bad])
        self.assertEqual(self._audit_rows("SELECT count(DISTINCT query_id) FROM citation_record"), [(1,)])

    def test_unknown_query(self):
        with self.assertRaises(KosError) as ctx:
            audit.reverify(self.home, "nao-existe", {})
        self.assertEqual(ctx.exception.code, "E_FILTER_INVALID")


if __name__ == "__main__":
    unittest.main()
