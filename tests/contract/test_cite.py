"""Testes de contrato das citações (CTR-07, TC-CIT-01..03, 05, 06; BL-11)."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from kos.cite import VERIFICATIONS, cite, validate_citation
from kos.discovery import Policy
from kos.errors import KosError
from kos.ingest import ingest_full
from tests.fixtures.gitbuilder import Commit, build_repo
from tests.helpers import run_kos

POLICY = Policy.from_dict({"policy_id": "teste", "version": 1, "include": ["**"], "exclude": [],
                           "max_bytes": 100_000, "generated": [], "kind_rules": []})

FILES = {
    "AGENTS.md": "# Regras\n\nlinha um\nlinha dois com ação\nlinha três\n\n## Outra\n\nfim\n",
    "package.json": '{\n  "name": "site",\n  "scripts": {\n    "gate": "node scripts/quality-gate.mjs"\n  }\n}\n',
    "pagina.html": "<h1>Título</h1>\n<p>P95 &lt; 800ms</p>\n",
}


class CiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        base = Path(cls._tmp.name)
        cls.root, cls.home = base / "repo", base / "home"
        _, cls.commits = build_repo(cls.root, [Commit("c1", files=FILES),
                                               Commit("c2", files={"AGENTS.md": "# Novo\n\noutro texto\n"})])
        for commit in cls.commits:
            ingest_full(cls.home, cls.root, rev=commit, policy=POLICY, repo_name="r")
        _, cls.other_commits = build_repo(base / "outro", [Commit("x", files={"x.md": "x\n"})])
        cls.other = base / "outro"

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _keys(self, path, commit=None):
        conn = sqlite3.connect(self.home / "index.sqlite")
        try:
            return [row[0] for row in conn.execute(
                "SELECT f.fragment_key FROM fragment f JOIN artifact_version v USING (version_id)"
                " JOIN artifact a USING (artifact_id) JOIN revision_manifest m ON m.version_id = v.version_id"
                " JOIN source_revision s USING (revision_id)"
                " WHERE a.path_text = ? AND s.commit_oid = ? ORDER BY f.ordinal",
                (path, commit or self.commits[0]))]
        finally:
            conn.close()

    def test_cit01_markdown_verified_exact(self):
        [c] = cite(self.home, self._keys("AGENTS.md")[:1], commit=self.commits[0])
        self.assertEqual(c.verification, "verified_exact")
        self.assertEqual((c.repo_name, c.path_text, c.commit_oid), ("r", "AGENTS.md", self.commits[0]))
        self.assertEqual((c.locator.start_line, c.locator.end_line), (1, 5))
        self.assertIn("linha dois com ação", c.quoted_text)
        data = c.to_json()
        self.assertEqual(len(data["commit_oid"]), 40)
        self.assertTrue(c.human().startswith(f"[1] r:AGENTS.md#L1-L5 @{self.commits[0][:12]} (verified_exact)"))

    def test_revisao_padrao_e_a_mais_recente_que_contem_o_fragmento(self):
        [c] = cite(self.home, self._keys("package.json")[:1])
        self.assertEqual(c.commit_oid, self.commits[1])  # package.json não mudou em c2

    def test_cit02_json_struct_path_e_linhas(self):
        keys = self._keys("package.json")
        cits = cite(self.home, keys)
        gate = next(c for c in cits if c.locator.struct_path == "/scripts/gate")
        self.assertEqual((gate.locator.start_line, gate.locator.end_line), (4, 4))
        self.assertEqual(gate.quoted_text, '"gate": "node scripts/quality-gate.mjs"')
        self.assertEqual(gate.verification, "verified_exact")
        self.assertIn("#L4 /scripts/gate", gate.human())

    def test_html_verified_normalized(self):
        [c] = cite(self.home, self._keys("pagina.html"))
        self.assertEqual(c.verification, "verified_normalized")
        self.assertEqual(c.quoted_text, "Título\nP95 < 800ms")

    def test_cit03_blob_ilegivel_vira_nao_verificada(self):
        [c] = cite(self.home, self._keys("AGENTS.md")[:1], commit=self.commits[0], repos={"r": self.other})
        self.assertEqual(c.verification, "unverified")
        self.assertIn("E_BLOB_UNREADABLE", c.verification_note)
        self.assertIn("(não verificada)", c.human())

    def test_cit03_texto_adulterado_no_indice_vira_nao_verificada(self):
        home = Path(self._tmp.name) / "home-adulterado"
        ingest_full(home, self.root, rev=self.commits[0], policy=POLICY, repo_name="r")
        with sqlite3.connect(home / "index.sqlite") as conn:
            conn.execute("UPDATE fragment SET text = 'adulterado', text_sha256 = ? WHERE ordinal = 0",
                         ("0" * 64,))
            key = conn.execute("SELECT f.fragment_key FROM fragment f JOIN artifact_version v USING (version_id)"
                               " JOIN artifact a USING (artifact_id) WHERE a.path_text = 'AGENTS.md'"
                               " AND f.ordinal = 0").fetchone()[0]
        [c] = cite(home, [key])
        self.assertEqual(c.verification, "unverified")
        self.assertIn("não confere", c.verification_note)

    def test_sub_intervalo_de_linhas(self):
        [c] = cite(self.home, self._keys("AGENTS.md")[:1], commit=self.commits[0], lines=(4, 4))
        self.assertEqual((c.quoted_text, c.verification), ("linha dois com ação", "verified_exact"))
        self.assertEqual((c.locator.start_line, c.locator.end_line), (4, 4))
        for lines in ((8, 9), (0, 1)):
            with self.assertRaises(KosError) as ctx:
                cite(self.home, self._keys("AGENTS.md")[:1], commit=self.commits[0], lines=lines)
            self.assertEqual(ctx.exception.code, "E_SUBRANGE_OUT_OF_BOUNDS")
        with self.assertRaises(KosError) as ctx:
            cite(self.home, self._keys("pagina.html"), lines=(1, 1))
        self.assertEqual(ctx.exception.code, "E_SUBRANGE_OUT_OF_BOUNDS")

    def test_fragmento_inexistente_ou_fora_da_revisao(self):
        old = self._keys("AGENTS.md")[0]
        for kwargs in ({"fragment_keys": ["0" * 64]}, {"fragment_keys": [old], "commit": self.commits[1]}):
            with self.subTest(kwargs=kwargs), self.assertRaises(KosError) as ctx:
                cite(self.home, **kwargs)
            self.assertEqual(ctx.exception.code, "E_FRAGMENT_GONE")

    def test_cit05_toda_citacao_tem_verificacao(self):
        keys = [k for path in FILES for k in self._keys(path)]
        for c in cite(self.home, keys, commit=self.commits[0]) + cite(
                self.home, keys[:2], commit=self.commits[0], repos={"r": self.other}):
            self.assertIn(c.verification, VERIFICATIONS)
            validate_citation(c.to_json())

    def test_cit06_commit_abreviado_e_rejeitado(self):
        data = cite(self.home, self._keys("package.json")[:1])[0].to_json()
        validate_citation(data)
        for field, value in (("commit_oid", data["commit_oid"][:12]), ("verification", None),
                             ("blob_oid", "xyz")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_citation(dict(data, **{field: value}))

    def test_cli(self):
        key = self._keys("AGENTS.md")[0]
        proc = run_kos("cite", key, "--rev", self.commits[0], "--home", str(self.home), "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema"], "kos.cite.v1")
        self.assertEqual(payload["citations"][0]["verification"], "verified_exact")
        human = run_kos("cite", key, "--rev", self.commits[0], "--lines", "4-4", "--home", str(self.home))
        self.assertIn("#L4 @", human.stdout)
        gone = run_kos("cite", "0" * 64, "--home", str(self.home), "--json")
        self.assertEqual((gone.returncode, json.loads(gone.stdout)["code"]), (2, "E_FRAGMENT_GONE"))


if __name__ == "__main__":
    unittest.main()
