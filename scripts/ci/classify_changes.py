#!/usr/bin/env python3
"""Classifica os arquivos alterados num PR para a CI decidir o que rodar.

Uso: classify_changes.py <base_sha> <head_sha>  (ou lista de caminhos em stdin com "-")

Escreve em $GITHUB_OUTPUT (ou stdout) as chaves:
  system=true|false  algo que muda o comportamento do sistema ou dos testes
  docs=true|false    algum documento alterado

Regra (docs/ci-cd.md): um arquivo é "system" se casar com SYSTEM_PATTERNS. Os
documentos que os testes leem (DDL e catálogo de erros da spec) também contam
como "system", porque mudá-los pode quebrar testes. Um PR só com documentos que
não são "system" é "docs-only" e não roda a suíte de testes.
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
import sys

SYSTEM_PATTERNS = (
    "src/*",
    "tests/*",
    "scripts/*",
    ".github/*",
    "pyproject.toml",
    # Lidos por tests/unit/test_schema.py e tests/unit/test_errors.py.
    "docs/fase-0/02-modelo-de-dados.md",
    "docs/fase-0/03-contratos.md",
)
DOC_PATTERNS = ("*.md", "docs/*")


def classify(paths: list[str]) -> dict[str, bool]:
    system = any(fnmatch.fnmatch(p, pat) for p in paths for pat in SYSTEM_PATTERNS)
    docs = any(fnmatch.fnmatch(p, pat) for p in paths for pat in DOC_PATTERNS)
    # Sem arquivos (não deveria acontecer) ou com algo não classificado: roda tudo.
    unknown = [p for p in paths
               if not any(fnmatch.fnmatch(p, pat) for pat in SYSTEM_PATTERNS + DOC_PATTERNS)]
    if not paths or unknown:
        system = True
    return {"system": system, "docs": docs}


def changed_paths(base: str, head: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", "-z", f"{base}...{head}"],
        check=True, capture_output=True,
    ).stdout
    return [p.decode("utf-8", "surrogateescape") for p in out.split(b"\0") if p]


def main(argv: list[str]) -> int:
    if argv[1:] == ["-"]:
        paths = [line.strip() for line in sys.stdin if line.strip()]
    elif len(argv) == 3:
        paths = changed_paths(argv[1], argv[2])
    else:
        print(__doc__, file=sys.stderr)
        return 1
    result = classify(paths)
    lines = [f"{k}={'true' if v else 'false'}" for k, v in result.items()]
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"{len(paths)} arquivo(s) alterado(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
