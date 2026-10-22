"""Testes de contrato da resposta extrativa e da abstenção (CTR-08, CTR-09; BL-13).

TC-ANS-01, TC-ANS-04, TC-ANS-05 (parte sem rede: o adaptador nem existe ainda),
TC-ABS-01, TC-ABS-03, TC-ABS-04, TC-ABS-05.
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from kos.answer import VERIFIED, Thresholds, ask, essential_terms, split_parts
from kos.discovery import Policy
from kos.errors import KosError
from kos.ingest import ingest_full
from tests.fixtures.gitbuilder import Commit, build_repo
from tests.helpers import run_kos

POLICY = Policy.from_dict({"policy_id": "teste", "version": 1, "include": ["**"], "exclude": [],
                           "max_bytes": 100_000, "generated": [], "kind_rules": []})
FILES = {
    "AGENTS.md": ("# Regras\n\n## Apresentação\n\nA página usa paleta própria\n"
                  "e um piso de contraste de **7:1** na Camada 3.\n\n## Outra\n\nfim\n"),
    "docs/kpis.md": "# Métricas\n\nO painel define 18 KPIs cognitivos em 4 camadas.\n",
    "pagina.html": "<h1>Observabilidade</h1>\n<p>São 22 KPIs cognitivos em 5 camadas.</p>\n",
    "package.json": '{\n  "scripts": {\n    "gate": "node scripts/quality-gate.mjs"\n  }\n}\n',
}


class AnswerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        base = Path(cls._tmp.name)
        cls.root, cls.home = base / "repo", base / "home"
        _, cls.commits = build_repo(cls.root, [Commit("c1", files=FILES)])
        ingest_full(cls.home, cls.root, rev=cls.commits[0], policy=POLICY, repo_name="r")
        build_repo(base / "outro", [Commit("x", files={"x.md": "x\n"})])
        cls.other = base / "outro"

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _audit(self, sql, params=()):
        conn = sqlite3.connect(self.home / "audit.sqlite")
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def assertSupported(self, answer):
        """CTR-08 inv. 1: toda afirmação tem ao menos uma citação verificada."""
        for claim in answer.claims:
            self.assertTrue(any(answer.citations[n - 1].verification in VERIFIED for n in claim.citation_nos),
                            claim)

    def test_ans01_extractive_cites_the_exact_line(self):
        a = ask(self.home, "Qual é o piso de contraste da Camada 3 da apresentação?")
        self.assertEqual(a.outcome, "answered")
        self.assertSupported(a)
        first = a.citations[a.claims[0].citation_nos[0] - 1]
        self.assertEqual((first.path_text, first.locator.start_line, first.locator.end_line), ("AGENTS.md", 6, 6))
        self.assertEqual(first.verification, "verified_exact")
        self.assertIn("**7:1** na Camada 3", a.claims[0].text)

    def test_ans04_numeric_conflict_shows_both_sides(self):
        a = ask(self.home, "Quantos KPIs cognitivos o painel define?")
        self.assertEqual(a.outcome, "answered_with_conflict")
        self.assertSupported(a)
        [conflict] = a.conflicts
        self.assertEqual(conflict["topic"], "kpis")
        self.assertEqual([s["value"] for s in conflict["sides"]], ["18", "22"])
        paths = [{x["path"] for x in s["scope"]} for s in conflict["sides"]]
        self.assertEqual(paths, [{"docs/kpis.md"}, {"pagina.html"}])

    def test_abs01_term_absent_from_corpus(self):
        a = ask(self.home, "Qual é o RTO da página?")
        self.assertEqual(a.outcome, "abstained")
        self.assertEqual(a.abstention["code"], "insufficient_evidence")
        self.assertIn("rto", a.abstention["message"])
        self.assertLessEqual(len(a.citations), 3)
        self.assertFalse(a.claims)

    def test_no_hits(self):
        a = ask(self.home, "zzqx wwqy")
        self.assertEqual((a.outcome, a.abstention["code"]), ("abstained", "no_hits"))

    def test_abs03_revision_not_indexed(self):
        a = ask(self.home, "piso de contraste", commit="f" * 40)
        self.assertEqual(a.abstention["code"], "revision_unavailable")

    def test_abs04_all_citations_unverified(self):
        a = ask(self.home, "piso de contraste", repos={"r": self.other})
        self.assertEqual(a.abstention["code"], "unverifiable_evidence")
        self.assertTrue(all(c.verification == "unverified" for c in a.citations))

    def test_abs05_partial_answer_declares_the_gap(self):
        a = ask(self.home, "Qual é o piso de contraste da Camada 3? E qual é o RTO da página?")
        self.assertEqual(a.outcome, "answered")
        self.assertSupported(a)
        self.assertEqual(a.gaps, [{"part": "qual é o RTO da página", "missing_terms": ["rto"]}])

    def test_coverage_threshold_is_optional(self):
        strict = Thresholds(min_term_coverage=1.0)
        # Os dois termos existem no corpus, mas com k=1 só um aparece nos trechos recuperados.
        a = ask(self.home, "Qual paleta usa o gate?", k=1, thresholds=strict)
        self.assertEqual(a.abstention["code"], "insufficient_evidence")
        self.assertEqual(ask(self.home, "Qual paleta usa o gate?", k=1).outcome, "answered")

    def test_llm_mode_is_disabled_and_audited(self):
        with self.assertRaises(KosError) as ctx:
            ask(self.home, "piso", mode="llm")
        self.assertEqual(ctx.exception.code, "E_LLM_DISABLED")
        rows = self._audit("SELECT a.outcome, a.mode FROM answer_record a JOIN query_event q USING (query_id)"
                           " WHERE q.params_json LIKE '%\"mode\":\"llm\"%'")
        self.assertIn(("error", "llm"), rows)

    def test_ask_is_audited_with_claims(self):
        a = ask(self.home, "Qual é o piso de contraste da Camada 3 da apresentação?", interface="bench")
        [(outcome, code)] = self._audit("SELECT outcome, abstention_code FROM answer_record WHERE query_id = ?",
                                        (a.query_id,))
        self.assertEqual((outcome, code), ("answered", None))
        claims = self._audit("SELECT citation_no, claim_ids FROM citation_record WHERE query_id = ?"
                             " ORDER BY citation_no", (a.query_id,))
        self.assertEqual(len(claims), len(a.citations))
        self.assertEqual(json.loads(claims[0][1]), ["c1"])
        self.assertEqual(self._audit("SELECT count(*) FROM query_event WHERE query_id = ?", (a.query_id,)), [(1,)])

    def test_cli_exit_codes_and_json(self):
        proc = run_kos("ask", "Qual é o RTO da página?", "--home", str(self.home), "--json")
        self.assertEqual(proc.returncode, 3, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual((out["schema"], out["outcome"]), ("kos.answer.v1", "abstained"))
        proc = run_kos("ask", "Quantos KPIs cognitivos o painel define?", "--home", str(self.home))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Conflito sobre 'kpis'", proc.stdout)
        self.assertIn("Nenhum lado foi escolhido", proc.stdout)
        proc = run_kos("ask", "piso", "--mode", "llm", "--home", str(self.home), "--json")
        self.assertEqual((proc.returncode, json.loads(proc.stdout)["code"]), (2, "E_LLM_DISABLED"))


class QuestionTest(unittest.TestCase):
    def test_split_parts(self):
        self.assertEqual(split_parts("Qual é o RTO e o RPO do site?"), ["Qual é o RTO e o RPO do site"])
        self.assertEqual(split_parts("Qual é o piso? E qual é o RTO?"), ["Qual é o piso", "qual é o RTO"])
        self.assertEqual(split_parts("Por que não usa X e quando isso pode mudar?"),
                         ["Por que não usa X", "quando isso pode mudar"])
        self.assertEqual(split_parts("???"), ["???"])

    def test_essential_terms_fold_accents_and_drop_stopwords(self):
        self.assertEqual(essential_terms("Qual é o piso da Página de Produção?"), ["piso", "pagina", "producao"])


if __name__ == "__main__":
    unittest.main()
