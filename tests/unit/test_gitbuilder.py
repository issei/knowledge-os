"""O construtor de repositórios-fixture é determinístico e cobre os casos da spec (BL-02)."""

import tempfile
import unittest
from pathlib import Path

from tests.fixtures.gitbuilder import Commit, build_repo

SCRIPT = [
    Commit("base", files={
        "docs/a.md": "# A\n",
        "crlf.txt": b"linha 1\r\nlinha 2\r\n",
        "apresentação/ADR.md": "nfc\n",
        "apresentação/ADR.md": "nfd\n",
        b"bin\xff.txt": b"nome nao utf-8\n",
    }, symlinks={"link.md": "docs/a.md"},
       submodules={"vendor/lib": "1" * 40},
       lfs={"grande.bin": 10_000}),
    Commit("rename e delete", renames=[("docs/a.md", "docs/b.md")], files={"crlf.txt": None}),
]


class GitBuilderTest(unittest.TestCase):
    def test_same_script_same_oids(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            _, oids_a = build_repo(Path(a) / "r", SCRIPT)
            _, oids_b = build_repo(Path(b) / "r", SCRIPT)
        self.assertEqual(oids_a, oids_b)
        self.assertEqual(len(oids_a), 2)

    def test_tree_has_every_kind_of_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, oids = build_repo(Path(tmp) / "r", SCRIPT)
            first = repo.git("ls-tree", "-r", "-z", oids[0]).split(b"\0")
            modes = {line.split(b"\t")[1]: line.split(b" ")[0] for line in first if line}
            self.assertEqual(modes[b"link.md"], b"120000")
            self.assertEqual(modes[b"vendor/lib"], b"160000")
            self.assertIn(b"bin\xff.txt", modes)
            self.assertIn("apresentação/ADR.md".encode(), modes)
            self.assertIn("apresentação/ADR.md".encode(), modes)
            crlf = repo.git("show", f"{oids[0]}:crlf.txt")
            self.assertEqual(crlf, b"linha 1\r\nlinha 2\r\n")
            second = repo.git("ls-tree", "-r", "--name-only", "-z", oids[1]).split(b"\0")
            self.assertIn(b"docs/b.md", second)
            self.assertNotIn(b"docs/a.md", second)
            self.assertNotIn(b"crlf.txt", second)


if __name__ == "__main__":
    unittest.main()
