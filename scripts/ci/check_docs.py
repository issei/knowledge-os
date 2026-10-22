#!/usr/bin/env python3
"""Verificação leve de documentação, sem dependências.

Confere que todo link relativo em arquivos .md aponta para um arquivo que
existe no repositório. Links externos (http/https/mailto) e âncoras puras são
ignorados.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
SKIP_DIRS = {".git", "node_modules", ".kos", "build", "dist"}


def broken_links(root: Path) -> list[str]:
    problems = []
    for md in sorted(root.rglob("*.md")):
        if SKIP_DIRS.intersection(md.relative_to(root).parts):
            continue
        text = md.read_text(encoding="utf-8")
        # Ignora blocos de código cercados.
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        for target in LINK.findall(text):
            if re.match(r"^(https?:|mailto:|#)", target):
                continue
            path = target.split("#", 1)[0]
            if path and not (md.parent / path).exists():
                problems.append(f"{md.relative_to(root)}: link quebrado -> {target}")
    return problems


def main() -> int:
    problems = broken_links(ROOT)
    for p in problems:
        print(p, file=sys.stderr)
    print(f"check_docs: {len(problems)} problema(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
