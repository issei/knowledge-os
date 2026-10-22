"""Testes de contrato da recuperação (CTR-06, TC-RET-01..06; BL-10)."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from kos.discovery import Policy
from kos.errors import KosError
from kos.ingest import ingest_full
from kos.search import fts_query, search
from tests.fixtures.gitbuilder import Commit, build_repo
from tests.helpers import run_kos

POLICY = Policy.from_dict({
    "policy_id": "teste", "version": 1, "include": ["**"], "exclude": [], "max_bytes": 100_000,
    "generated": ["en/**"],
    "kind_rules": [{"pattern": "docs/**", "kind": "doc"}, {"pattern": "**/*.mjs", "kind": "code"}],
})


class SearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        base = Path(cls._tmp.name)
        cls.root, cls.home = base / "repo", base / "home"
        _, cls.commits = build_repo(cls.root, [
            Commit("c1", files={
                "docs/apresentação.md": "# Apresentação\n\nPiso de contraste 7:1 na Camada 3.\n",
                "docs/historia.md": "# História\n\nTermo alfaromeo só aqui.\n",
                "scripts/gen.mjs": "export function genPortfolio(cv) {\n  return pfBlock(cv);\n}\n",
                "en/apresentacao.md": "# Presentation\n\nContrast floor 7:1 on layer 3.\n",
                "docs/a.md": "# Igual\n\npalavra gemea\n", "docs/b.md": "# Igual\n\npalavra gemea\n",
            }),
            Commit("c2", files={"docs/historia.md": "# História\n\nTexto novo sem o termo.\n"}),
        ])
        for commit in cls.commits:
            ingest_full(cls.home, cls.root, rev=commit, policy=POLICY, repo_name="r")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _paths(self, query, **kw):
        return [h.path_text for h in search(self.home, query, **kw).results]

    def test_ret01_termo_unico_em_primeiro(self):
        result = search(self.home, "contraste")
        self.assertEqual(result.results[0].path_text, "docs/apresentação.md")
        self.assertEqual(result.results[0].rank, 1)
        self.assertEqual(result.revisions, [{"repo": "r", "commit_oid": self.commits[-1]}])

    def test_ret02_sem_acento_casa_com_acento(self):
        self.assertIn("docs/apresentação.md", self._paths("apresentacao"))

    def test_ret03_identificadores(self):
        self.assertEqual(self._paths("gen portfolio"), ["scripts/gen.mjs"])
        self.assertEqual(self._paths("pf block"), ["scripts/gen.mjs"])
        self.assertIn('"gen"', fts_query("genPortfolio"))

    def test_ret04_sintaxe_fts_nao_vira_operador(self):
        for q in ['"contraste', "contraste*", "NEAR(contraste piso)", "text:contraste", "a OR", "-contraste ^x"]:
            with self.subTest(q=q):
                result = search(self.home, q)
                self.assertNotIn("NEAR(", result.diagnostics["parsed_query"])
        self.assertEqual(fts_query('a"b'), '"a" OR "b"')

    def test_ret05_resultado_sempre_do_manifesto_da_revisao(self):
        self.assertEqual(self._paths("alfaromeo"), [])  # sumiu em c2
        old = search(self.home, "alfaromeo", commit=self.commits[0])
        self.assertEqual([h.path_text for h in old.results], ["docs/historia.md"])
        self.assertEqual(old.results[0].commit_oid, self.commits[0])
        conn = sqlite3.connect(self.home / "index.sqlite")
        self.addCleanup(conn.close)
        for commit in self.commits:
            manifest = {row[0] for row in conn.execute(
                "SELECT f.fragment_key FROM fragment f JOIN revision_manifest m USING (version_id)"
                " JOIN source_revision s USING (revision_id) WHERE s.commit_oid = ?", (commit,))}
            for q in ("termo", "história", "palavra", "contraste", "texto"):
                for hit in search(self.home, q, commit=commit, k=50, include_generated=True).results:
                    self.assertIn(hit.fragment_key, manifest)

    def test_ret06_fts_em_dia_com_fragmentos(self):
        conn = sqlite3.connect(self.home / "index.sqlite")
        self.addCleanup(conn.close)
        conn.execute("INSERT INTO fragment_fts(fragment_fts) VALUES ('integrity-check')")
        self.assertEqual(conn.execute("SELECT count(*) FROM fragment").fetchone(),
                         conn.execute("SELECT count(*) FROM fragment_fts_docsize").fetchone())

    def test_gerados_fora_por_padrao_e_marcados_quando_incluidos(self):
        self.assertNotIn("en/apresentacao.md", self._paths("contrast"))
        hits = search(self.home, "contrast", include_generated=True).results
        self.assertEqual([(h.path_text, h.is_generated) for h in hits], [("en/apresentacao.md", True)])

    def test_empate_desempata_por_fragment_key(self):
        hits = search(self.home, "gemea").results
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0].score, hits[1].score)
        self.assertLess(hits[0].fragment_key, hits[1].fragment_key)

    def test_filtros(self):
        self.assertEqual(self._paths("contraste OR genPortfolio", kinds=["code"]), ["scripts/gen.mjs"])
        self.assertEqual(self._paths("contraste genPortfolio", path_glob="docs/**"), ["docs/apresentação.md"])
        self.assertEqual(len(search(self.home, "palavra", k=1).results), 1)

    def test_vazio_e_valido(self):
        self.assertEqual(search(self.home, "inexistentezzz").results, [])

    def test_erros(self):
        cases = [
            (dict(query="?!"), "E_QUERY_EMPTY"),
            (dict(query="x", kinds=["nada"]), "E_FILTER_INVALID"),
            (dict(query="x", k=0), "E_FILTER_INVALID"),
            (dict(query="x", path_glob="/abs"), "E_FILTER_INVALID"),
            (dict(query="x", commit="abc"), "E_FILTER_INVALID"),
            (dict(query="x", commit="f" * 40), "E_REVISION_NOT_INDEXED"),
            (dict(query="x", repo="outro"), "E_NO_INDEXED_REVISION"),
        ]
        for kwargs, code in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(KosError) as ctx:
                search(self.home, **kwargs)
            self.assertEqual(ctx.exception.code, code)
        with self.assertRaises(KosError) as ctx:
            search(Path(self._tmp.name) / "vazio", "x")
        self.assertEqual(ctx.exception.code, "E_NO_INDEXED_REVISION")

    def test_cli(self):
        proc = run_kos("search", "apresentacao", "--home", str(self.home), "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema"], "kos.search.v1")
        first = payload["results"][0]
        self.assertEqual(first["locator"]["start_line"], 1)
        self.assertEqual(first["path_text"], "docs/apresentação.md")
        text = run_kos("search", "contraste", "--home", str(self.home))
        self.assertIn("docs/apresentação.md#L1-L3", text.stdout)
        bad = run_kos("search", "?!", "--home", str(self.home), "--json")
        self.assertEqual((bad.returncode, json.loads(bad.stdout)["code"]), (2, "E_QUERY_EMPTY"))


if __name__ == "__main__":
    unittest.main()
