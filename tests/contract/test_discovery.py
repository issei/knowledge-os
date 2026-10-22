"""Testes de contrato da descoberta (CTR-01, TC-DSC-01..07; BL-03)."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from kos.discovery import Policy, discover, looks_binary
from kos.errors import KosError
from tests.fixtures.gitbuilder import Commit, build_repo
from tests.helpers import run_kos

POLICY = {
    "policy_id": "teste", "version": 1,
    "include": ["**"], "exclude": ["ignorado/**"],
    "max_bytes": 1000, "generated": ["src/en/**"],
    "kind_rules": [
        {"pattern": "**/ADR-*.md", "kind": "adr"},
        {"pattern": "tests/**", "kind": "test"},
        {"pattern": "**/*.md", "kind": "doc"},
        {"pattern": "**/*.mjs", "kind": "code"},
    ],
}


def _serialize(files):
    return json.dumps([f.to_json() for f in files], sort_keys=True).encode()


class DiscoveryTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "repo"
        self.policy = Policy.from_dict(POLICY)

    def tearDown(self):
        self._tmp.cleanup()

    def _build(self, *commits):
        self.repo, self.oids = build_repo(self.root, list(commits))
        return self.oids[-1]

    def test_dsc01_ten_files_stable_order(self):
        names = [f"d{i % 3}/f{i}.md" for i in range(10)]
        commit = self._build(Commit("dez", files={n: f"# {n}\n" for n in names}))
        oid, files = discover(self.root, commit, self.policy)
        self.assertEqual(oid, commit)
        self.assertEqual([f.path_text for f in files], sorted(names))
        self.assertTrue(all(f.eligibility == "eligible" for f in files))

    def test_dsc02_working_copy_is_ignored(self):
        commit = self._build(Commit("base", files={"a.md": "original\n"}))
        _, before = discover(self.root, commit, self.policy)
        (self.root / "a.md").write_text("alterado só na cópia\n")
        (self.root / "novo.md").write_text("não rastreado\n")
        _, after = discover(self.root, commit, self.policy)
        self.assertEqual(_serialize(before), _serialize(after))

    def test_dsc03_deterministic(self):
        commit = self._build(Commit("base", files={"a.md": "a\n", "b.mjs": "x\n"}))
        runs = [hashlib.sha256(_serialize(discover(self.root, commit, self.policy)[1])).hexdigest()
                for _ in range(2)]
        self.assertEqual(runs[0], runs[1])

    def test_dsc04_non_ascii_and_non_utf8_paths(self):
        nfc = "apresentação/ADR-001.md"
        nfd = "apresentac\u0327a\u0303o/ADR-001.md"
        latin1 = b"latin1-\xe7.md"
        commit = self._build(Commit("nomes", files={nfc: "nfc\n", nfd: "nfd\n", latin1: "x\n"}))
        _, files = discover(self.root, commit, self.policy)
        by_bytes = {f.path_bytes: f for f in files}
        self.assertEqual(set(by_bytes), {nfc.encode(), nfd.encode(), latin1})
        self.assertTrue(by_bytes[nfc.encode()].path_is_utf8)
        # NFD é UTF-8 válido; o texto de exibição é normalizado em NFC, os bytes não.
        self.assertEqual(by_bytes[nfd.encode()].path_text, nfc)
        self.assertFalse(by_bytes[latin1].path_is_utf8)
        self.assertIn("�", by_bytes[latin1].path_text)
        self.assertEqual(by_bytes[nfc.encode()].artifact_kind, "adr")

    def test_dsc05_symlink_submodule_lfs(self):
        commit = self._build(Commit(
            "especiais", files={"a.md": "a\n"}, symlinks={"link.md": "a.md"},
            submodules={"vendor/lib": "2" * 40}, lfs={"modelo.bin": 50_000}))
        _, files = discover(self.root, commit, self.policy)
        rules = {f.path_text: f.exclusion_rule for f in files}
        self.assertEqual(rules, {
            "a.md": None, "link.md": "symlink_not_followed",
            "vendor/lib": "submodule_not_followed", "modelo.bin": "lfs_pointer",
        })

    def test_dsc06_generated(self):
        commit = self._build(Commit("i18n", files={"src/en/pagina.md": "en\n", "src/pagina.md": "pt\n"}))
        _, files = discover(self.root, commit, self.policy)
        by = {f.path_text: f for f in files}
        self.assertTrue(by["src/en/pagina.md"].is_generated)
        self.assertEqual(by["src/en/pagina.md"].artifact_kind, "generated")
        self.assertEqual(by["src/en/pagina.md"].kind_rule, "generated:src/en/**")
        self.assertFalse(by["src/pagina.md"].is_generated)
        self.assertEqual(by["src/pagina.md"].artifact_kind, "doc")

    def test_dsc07_invalid_policy(self):
        for bad in ({}, {**POLICY, "max_bytes": 0}, {**POLICY, "extra": 1},
                    {**POLICY, "kind_rules": [{"pattern": "**", "kind": "inventado"}]},
                    {**POLICY, "include": ["/absoluto"]}, {**POLICY, "version": True}):
            with self.subTest(bad=bad), self.assertRaises(KosError) as ctx:
                Policy.from_dict(bad)
            self.assertEqual(ctx.exception.code, "E_POLICY_INVALID")

    def test_nothing_disappears_silently(self):
        commit = self._build(Commit("mistura", files={
            "a.md": "a\n", "ignorado/x.md": "x\n", "grande.md": "g" * 2000,
            "foto.png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\xff\xfe",
            "sentinela.mjs": "const s = `\x00MARCA`;\n",
        }, symlinks={"l.md": "a.md"}))
        _, files = discover(self.root, commit, self.policy)
        tree = self.repo.git("ls-tree", "-r", "--name-only", "-z", commit).split(b"\0")
        self.assertEqual(len(files), len([p for p in tree if p]))
        rules = {f.path_text: f.exclusion_rule for f in files}
        self.assertEqual(rules["ignorado/x.md"], "excluded:ignorado/**")
        self.assertEqual(rules["grande.md"], "too_large")
        self.assertEqual(rules["foto.png"], "binary_unsupported")
        # Texto com NUL de propósito continua elegível (caso real do mauricio-site).
        self.assertIsNone(rules["sentinela.mjs"])
        for f in files:
            self.assertEqual(f.eligibility == "excluded", f.exclusion_rule is not None)

    def test_policy_hash_changes_with_policy(self):
        other = Policy.from_dict({**POLICY, "max_bytes": 999})
        self.assertNotEqual(self.policy.sha256, other.sha256)
        self.assertEqual(self.policy.sha256, Policy.from_dict(dict(reversed(POLICY.items()))).sha256)

    def test_errors_for_missing_repo_and_commit(self):
        commit = self._build(Commit("base", files={"a.md": "a\n"}))
        with self.assertRaises(KosError) as ctx:
            discover(self.root.parent / "nao-existe", commit, self.policy)
        self.assertEqual(ctx.exception.code, "E_REPO_NOT_FOUND")
        plain = self.root.parent / "pasta"
        plain.mkdir()
        with self.assertRaises(KosError) as ctx:
            discover(plain, "HEAD", self.policy)
        self.assertEqual(ctx.exception.code, "E_REPO_NOT_FOUND")
        for rev in ("f" * 40, "--output=/tmp/x", "inexistente"):
            with self.subTest(rev=rev), self.assertRaises(KosError) as ctx:
                discover(self.root, rev, self.policy)
            self.assertEqual(ctx.exception.code, "E_COMMIT_NOT_FOUND")

    def test_cli_discover_json(self):
        commit = self._build(Commit("base", files={"a.md": "a\n", "b.png": b"\x00\xff\x00"}))
        policy_file = self.root.parent / "p.json"
        policy_file.write_text(json.dumps(POLICY))
        proc = run_kos("discover", str(self.root), "--rev", commit, "--policy", str(policy_file), "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out["schema"], "kos.discover.v1")
        self.assertEqual(out["commit_oid"], commit)
        self.assertEqual(out["counts"], {"total": 2, "eligible": 1, "excluded": 1})
        self.assertEqual(out["policy"]["sha256"], self.policy.sha256)

    def test_cli_invalid_policy_exit_2(self):
        commit = self._build(Commit("base", files={"a.md": "a\n"}))
        bad = self.root.parent / "ruim.json"
        bad.write_text("{nao é json")
        proc = run_kos("discover", str(self.root), "--rev", commit, "--policy", str(bad), "--json")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["code"], "E_POLICY_INVALID")


class LooksBinaryTest(unittest.TestCase):
    def test_cases(self):
        self.assertFalse(looks_binary(b"texto simples\n"))
        self.assertFalse(looks_binary("texto com NUL \x00 no meio".encode()))
        self.assertTrue(looks_binary(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\xff"))
        self.assertTrue(looks_binary(b"\x00\x01\x02\x03\x04abc"))
        # Caractere multibyte cortado no fim da amostra não vira binário.
        self.assertFalse(looks_binary(("texto comum com um NUL \x00 e acentuação ç").encode()[:-1]))


class PackagedPoliciesTest(unittest.TestCase):
    def test_default_and_mauricio_site_policies_are_valid(self):
        Policy.default()
        site = Policy.load(Path(__file__).resolve().parents[2] / "policies" / "mauricio-site.json")
        self.assertEqual(site.generated, ("src/en/**", "public/en/**"))


if __name__ == "__main__":
    unittest.main()
