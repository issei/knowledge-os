"""Testes de contrato do benchmark (04-benchmark.md §7, TC-BEN-01..04; BL-14)."""

import json
import os
import tempfile
import unittest
from pathlib import Path

import yaml

from kos import bench
from kos.answer import Answer
from kos.discovery import Policy
from kos.errors import KosError
from tests.fixtures.gitbuilder import Commit, build_repo
from tests.helpers import run_kos

ROOT = Path(__file__).resolve().parents[2]
C0 = ROOT / "bench" / "golden" / "c0.yaml"
POLICY = {"policy_id": "teste", "version": 1, "include": ["**"], "exclude": [],
          "max_bytes": 100_000, "generated": [], "kind_rules": []}
FILES = {
    "AGENTS.md": "# Regras\n\nO piso de contraste é **7:1** na Camada 3.\n",
    "package.json": '{\n  "scripts": {\n    "gate": "node scripts/quality-gate.mjs"\n  }\n}\n',
}


def _case(**over):
    case = {"id": "GS-SPEC-901", "classe": "spec_fact", "pergunta": "Qual é o piso de contraste da Camada 3?",
            "revisao_esperada": None,
            "fontes_relevantes": [{"caminho": "AGENTS.md", "linhas": "3", "relevancia": 2}],
            "evidencia_esperada": [{"caminho": "AGENTS.md", "linhas": "3", "trecho": "**7:1** na Camada 3"}],
            "resultado_esperado": {"outcome": "answered", "afirmacoes_obrigatorias": ["7:1"]}}
    case.update(over)
    return case


class SuiteTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.root = self.base / "repo"
        _, self.commits = build_repo(self.root, [Commit("c1", files=FILES)])

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, cases, name="s.yaml"):
        for c in cases:
            c["revisao_esperada"] = c["revisao_esperada"] or self.commits[0]
        path = self.base / name
        path.write_text(yaml.safe_dump({"suite": "t", "repo": "r", "revisao": self.commits[0], "casos": cases},
                                       allow_unicode=True))
        return path

    def test_ben01_c0_is_valid_with_unique_ids(self):
        suite = bench.load_suite(C0)
        self.assertEqual(len(suite.cases), 14)
        self.assertEqual(len({c.id for c in suite.cases}), 14)
        self.assertEqual(suite.revision, "73570bbc9b99e2a1e44d6844b9375bc4aa16e357")

    def test_ben01_invalid_suites(self):
        bad = {
            "id repetido": [_case(), _case()],
            "classe": [_case(classe="outra")],
            "outcome": [_case(resultado_esperado={"outcome": "talvez"})],
            "abstenção sem códigos": [_case(resultado_esperado={"outcome": "abstained"})],
            "linhas": [_case(fontes_relevantes=[{"caminho": "AGENTS.md", "linhas": "9-3", "relevancia": 2}])],
            "relevância": [_case(fontes_relevantes=[{"caminho": "AGENTS.md", "linhas": "3", "relevancia": 5}])],
        }
        for label, cases in bad.items():
            with self.subTest(label), self.assertRaises(KosError) as ctx:
                bench.load_suite(self._write(cases))
            self.assertEqual(ctx.exception.code, "E_SUITE_INVALID")

    def test_ben02_self_check(self):
        good = bench.load_suite(self._write([_case()]))
        self.assertEqual(bench.self_check(good, self.root), [])
        wrong = bench.load_suite(self._write([_case(evidencia_esperada=[
            {"caminho": "AGENTS.md", "linhas": "1", "trecho": "**7:1** na Camada 3"}])], "w.yaml"))
        self.assertEqual(len(bench.self_check(wrong, self.root)), 1)
        missing = bench.load_suite(self._write([_case(fontes_relevantes=[
            {"caminho": "nao-existe.md", "linhas": "1", "relevancia": 2}])], "m.yaml"))
        self.assertIn("não existe", bench.self_check(missing, self.root)[0])
        proc = run_kos("bench", "check", "--suite", str(self.base / "w.yaml"), "--repo", str(self.root), "--json")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(len(json.loads(proc.stdout)["problems"]), 1)

    @unittest.skipUnless(os.environ.get("KOS_C0_REPO"), "defina KOS_C0_REPO com um clone do mauricio-site")
    def test_ben02_c0_against_real_corpus(self):
        self.assertEqual(bench.self_check(bench.load_suite(C0), Path(os.environ["KOS_C0_REPO"])), [])

    def test_ben04_report_has_resources_and_versions(self):
        path = self._write([_case(), _case(id="GS-ABS-901", classe="no_answer", pergunta="Qual é o RTO?",
                                           fontes_relevantes=[], evidencia_esperada=[],
                                           resultado_esperado={"outcome": "abstained",
                                                               "abstention_codes_aceitos": ["no_hits"]})])
        policy = self.base / "p.json"
        policy.write_text(json.dumps(POLICY))
        out = self.base / "relatorio.json"
        proc = run_kos("bench", "run", "--suite", str(path), "--repo", str(self.root), "--policy", str(policy),
                       "--home", str(self.base / "home"), "--repetitions", "1", "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("B0-grep", proc.stdout)
        report = json.loads(out.read_text())
        self.assertEqual(report["schema"], "kos.bench.v1")
        for key in ("kos", "python", "sqlite", "git"):
            self.assertTrue(report["versions"][key])
        self.assertTrue(report["hardware"]["platform"])
        self.assertEqual(len(report["index"]["fingerprint"]), 64)
        self.assertGreater(report["index"]["fragments"], 0)
        self.assertEqual(set(report["configs"]), {"B0", "atual", "B0-grep", "B0-path"})
        b0 = report["configs"]["B0"]
        self.assertEqual(b0["weights"], [1.0, 1.0, 1.0])
        self.assertIn("p95_ms", b0["latency"]["search"])
        self.assertEqual(b0["retrieval"]["per_case"]["GS-SPEC-901"]["recall@1"], 1.0)
        self.assertTrue(b0["answer"]["per_case"]["GS-SPEC-901"]["expected_evidence_hit"])
        self.assertEqual(b0["citations"]["false_verified_exact"], [])
        self.assertEqual(report["human_review"][0]["case"], "GS-SPEC-901")
        self.assertIn("peak_rss_kib", report["resources"])


class MetricsTest(unittest.TestCase):
    """TC-BEN-03: métricas conferidas contra um caso calculado à mão."""

    CASE = bench.Case("GS-X", "lexical", "q", "0" * 40,
                      (bench.Source("a.md", 10, 12, 2), bench.Source("b.md", 1, 1, 1)), (),
                      "answered", (), (), ())

    def test_retrieval(self):
        units = [bench.Unit("x.md", 1, 5), bench.Unit("a.md", 11, 11), bench.Unit("b.md", 1, 5),
                 bench.Unit("a.md", 12, 20)]
        m = bench.retrieval_metrics(self.CASE, units)
        self.assertEqual((m["recall@1"], m["recall@3"], m["recall@10"]), (0.0, 1.0, 1.0))
        self.assertAlmostEqual(m["precision@3"], 2 / 3)
        self.assertAlmostEqual(m["precision@10"], 3 / 10)
        self.assertEqual((m["mrr"], m["first_essential_rank"]), (0.5, 2))
        self.assertEqual(bench.retrieval_metrics(self.CASE, [])["mrr"], 0.0)

    def test_answer(self):
        abstained = Answer("q", "abstained", "extractive", [], abstention={"code": "no_hits"})
        no_answer = bench.Case("GS-A", "no_answer", "q", "0" * 40, (), (), "abstained",
                               ("no_hits", "insufficient_evidence"), (), ())
        self.assertEqual(bench.answer_metrics(no_answer, abstained)["gap_recognized"], True)
        m = bench.answer_metrics(self.CASE, abstained)
        self.assertEqual((m["outcome_ok"], m["improper_abstention"]), (False, True))
        conflict = bench.Case("GS-C", "conflict", "q", "0" * 40, (), (), "answered_with_conflict", (), (), ())
        answered = Answer("q", "answered", "extractive", [])
        self.assertEqual(bench.answer_metrics(conflict, answered)["conflict_detected"], False)

    def test_baselines(self):
        self.assertEqual(bench.path_units("Qual é o ADR de build?", ["docs/ADR-build.md", "x.md", "adr.md"], 10),
                         [bench.Unit("docs/ADR-build.md", 1, 10**9), bench.Unit("adr.md", 1, 10**9)])


if __name__ == "__main__":
    unittest.main()
