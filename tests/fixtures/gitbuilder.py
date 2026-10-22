"""Construtor determinístico de repositórios Git para testes (BL-02).

Um roteiro é uma lista de commits. Cada commit descreve o que muda na árvore:

    Commit(
        message="primeiro",
        files={"docs/a.md": "texto", b"bin\\xff.txt": b"bytes", "velho.md": None},  # None apaga
        renames=[("a.md", "b.md")],
        symlinks={"link.md": "docs/a.md"},
        submodules={"vendor/lib": "0" * 40},
        lfs={"grande.bin": 12345},
    )

Autor, committer e datas são fixos, então o mesmo roteiro gera os mesmos OIDs
em qualquer máquina. Caminhos podem ser `str` (UTF-8) ou `bytes` (qualquer
sequência, inclusive não UTF-8), escritos sem normalização Unicode.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

Path_ = str | bytes

_BASE_EPOCH = 1_700_000_000  # 2023-11-14T22:13:20Z; cada commit soma 60 s.


@dataclass
class Commit:
    message: str
    files: dict[Path_, str | bytes | None] = field(default_factory=dict)
    renames: list[tuple[Path_, Path_]] = field(default_factory=list)
    symlinks: dict[Path_, str] = field(default_factory=dict)
    submodules: dict[Path_, str] = field(default_factory=dict)
    lfs: dict[Path_, int] = field(default_factory=dict)


def _b(path: Path_) -> bytes:
    return path if isinstance(path, bytes) else path.encode("utf-8")


def lfs_pointer(path: Path_, size: int) -> bytes:
    oid = hashlib.sha256(_b(path)).hexdigest()
    return (f"version https://git-lfs.github.com/spec/v1\n"
            f"oid sha256:{oid}\nsize {size}\n").encode()


class GitRepo:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._count = 0

    def git(self, *args: str | bytes, input: bytes | None = None) -> bytes:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(self.root),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
            "GIT_AUTHOR_DATE": f"@{_BASE_EPOCH + 60 * self._count} +0000",
            "GIT_COMMITTER_DATE": f"@{_BASE_EPOCH + 60 * self._count} +0000",
        }
        return subprocess.run(
            ["git", *args], cwd=self.root, env=env, input=input,
            check=True, capture_output=True,
        ).stdout

    def init(self) -> "GitRepo":
        self.root.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", "main")
        for key, value in (("core.autocrlf", "false"), ("core.quotepath", "false"),
                           ("commit.gpgsign", "false"), ("core.symlinks", "true")):
            self.git("config", key, value)
        return self

    def _abs(self, path: Path_) -> bytes:
        return os.path.join(os.fsencode(self.root), _b(path))

    def apply(self, commit: Commit) -> str:
        for path, content in commit.files.items():
            target = self._abs(path)
            if content is None:
                self.git("rm", "-q", "--", _b(path))
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as fh:
                fh.write(content.encode("utf-8") if isinstance(content, str) else content)
            self.git("add", "--", _b(path))
        for old, new in commit.renames:
            os.makedirs(os.path.dirname(self._abs(new)), exist_ok=True)
            self.git("mv", "--", _b(old), _b(new))
        for path, target in commit.symlinks.items():
            link = self._abs(path)
            os.makedirs(os.path.dirname(link), exist_ok=True)
            os.symlink(target, link)
            self.git("add", "--", _b(path))
        for path, sha in commit.submodules.items():
            self.git("update-index", "--add", "--cacheinfo", f"160000,{sha},{_b(path).decode()}")
        for path, size in commit.lfs.items():
            target = self._abs(path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as fh:
                fh.write(lfs_pointer(path, size))
            self.git("add", "--", _b(path))
        self.git("commit", "-q", "--allow-empty", "-m", commit.message)
        self._count += 1
        return self.head()

    def head(self) -> str:
        return self.git("rev-parse", "HEAD").decode().strip()


def build_repo(root: Path, script: list[Commit]) -> tuple[GitRepo, list[str]]:
    """Cria o repositório em `root` e aplica o roteiro. Devolve o repo e os OIDs."""
    repo = GitRepo(root).init()
    return repo, [repo.apply(c) for c in script]
