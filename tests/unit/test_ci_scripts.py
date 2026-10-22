"""Regras de classificação da CI e verificação de links (docs/ci-cd.md)."""

import importlib.util
import unittest

from tests.helpers import ROOT


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "ci" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


classify = _load("classify_changes").classify
check_docs = _load("check_docs")


class ClassifyChangesTest(unittest.TestCase):
    def test_docs_only(self):
        self.assertEqual(classify(["README.md", "docs/fase-0/04-benchmark.md"]),
                         {"system": False, "docs": True})

    def test_code_is_system(self):
        self.assertTrue(classify(["src/kos/cli.py"])["system"])
        self.assertTrue(classify(["tests/unit/test_schema.py"])["system"])
        self.assertTrue(classify([".github/workflows/ci.yml"])["system"])
        self.assertTrue(classify(["pyproject.toml"])["system"])

    def test_spec_files_read_by_tests_are_system(self):
        self.assertTrue(classify(["docs/fase-0/02-modelo-de-dados.md"])["system"])
        self.assertTrue(classify(["docs/fase-0/03-contratos.md"])["system"])

    def test_unknown_or_empty_runs_everything(self):
        self.assertTrue(classify(["LICENSE"])["system"])
        self.assertTrue(classify([])["system"])


class CheckDocsTest(unittest.TestCase):
    def test_repository_has_no_broken_links(self):
        self.assertEqual(check_docs.broken_links(ROOT), [])


class WorkflowTest(unittest.TestCase):
    def test_jobs_after_skipped_jobs_are_not_skipped(self):
        # Um PR só de documentação pula build e tests. Sem !cancelled(), o GitHub
        # também pula o merge automático (aconteceu no PR #14).
        import yaml
        jobs = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))["jobs"]
        for name in ("automerge", "release"):
            self.assertTrue(jobs[name]["if"].lstrip().startswith("!cancelled()"), name)


if __name__ == "__main__":
    unittest.main()
