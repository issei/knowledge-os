"""Consolidação da revisão independente (docs/fase-1/plano-revisao-multiagente.md, etapa B)."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

import yaml

from tests.helpers import ROOT

_spec = importlib.util.spec_from_file_location("consolidate", ROOT / "scripts" / "review" / "consolidate.py")
consolidate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(consolidate)

GOLDEN = {"suite": "t", "revisao": "x", "casos": [
    {"id": "A", "classe": "lexical", "pergunta": "Qual comando roda o quality gate?",
     "evidencia_esperada": [{"caminho": "package.json", "linhas": "2", "trecho": '"gate": "node gate.mjs"'}],
     "resultado_esperado": {"outcome": "answered"}},
    {"id": "B", "classe": "no_answer", "pergunta": "Qual é o RTO?", "evidencia_esperada": [],
     "resultado_esperado": {"outcome": "abstained"}},
]}


def _p2(a_type="resposta", a_line="2", a_quote='"gate": "node gate.mjs"'):
    return {"papel": "P2", "casos": [
        {"id": "A", "tipo": a_type, "resposta": "npm run gate", "confianca": "alta",
         "evidencias": [{"caminho": "package.json", "linhas": a_line, "trecho": a_quote}]},
        {"id": "B", "tipo": "sem_resposta", "resposta": "não há", "confianca": "alta", "evidencias": []},
    ]}


def _p3(defects=()):
    return {"papel": "P3", "casos": [
        {"id": "A", "veredito": "defeito" if defects else "sem_defeito", "defeitos": list(defects)},
        {"id": "B", "veredito": "sem_defeito", "defeitos": []},
    ]}


class ConsolidateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.corpus = self.base / "corpus"
        self.corpus.mkdir()
        (self.corpus / "package.json").write_text('{\n  "gate": "node gate.mjs"\n}\n', encoding="utf-8")
        (self.base / "golden.yaml").write_text(yaml.safe_dump(GOLDEN, allow_unicode=True), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def run_with(self, p2, p3):
        for name, data in (("p2.yaml", p2), ("p3.yaml", p3)):
            (self.base / name).write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        return consolidate.consolidate(self.base / "golden.yaml", self.corpus,
                                       self.base / "p2.yaml", self.base / "p3.yaml")

    def test_agreement(self):
        report = self.run_with(_p2(), _p3())
        self.assertEqual(report["resumo"]["concordantes"], 2)
        self.assertEqual(report["resumo"]["amostra_para_o_arbitro"], ["A", "B"])

    def test_type_and_evidence_divergence(self):
        report = self.run_with(_p2(a_type="conflito", a_line="1", a_quote="{"), _p3())
        a = report["casos"][0]
        self.assertFalse(a["concordante"])
        self.assertFalse(a["tipo_concorda"])
        self.assertFalse(a["evidencia_concorda"])

    def test_invented_quote_is_flagged(self):
        report = self.run_with(_p2(a_quote="texto inventado"), _p3())
        self.assertIn("P2 citou evidência que não confere com o corpus", report["casos"][0]["motivos_divergencia"])

    def test_only_proven_high_defect_blocks(self):
        proven = {"tipo": "resposta_errada", "gravidade": "alta", "descricao": "x",
                  "prova": {"caminho": "package.json", "linhas": "2", "trecho": '"gate"'}}
        unproven = {**proven, "prova": {"caminho": "package.json", "linhas": "2", "trecho": "não existe"}}
        self.assertFalse(self.run_with(_p2(), _p3([proven]))["casos"][0]["concordante"])
        self.assertTrue(self.run_with(_p2(), _p3([unproven]))["casos"][0]["concordante"])

    def test_path_outside_corpus_is_rejected(self):
        ok, why = consolidate.check_evidence(self.corpus, {"caminho": "../golden.yaml", "linhas": "1", "trecho": "x"})
        self.assertFalse(ok)
        self.assertEqual(why, "caminho fora do corpus")

    def test_missing_case_is_invalid(self):
        p2 = _p2()
        p2["casos"].pop()
        with self.assertRaises(consolidate.InvalidOutput):
            self.run_with(p2, _p3())


if __name__ == "__main__":
    unittest.main()
