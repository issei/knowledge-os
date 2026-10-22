"""Padrões de caminho no estilo gitignore, sobre caminhos relativos com `/`.

- `*` casa qualquer sequência sem `/`
- `?` casa um caractere que não é `/`
- `**/` casa zero ou mais diretórios; `/**` no fim casa tudo abaixo; `**` sozinho casa tudo
"""

from __future__ import annotations

import re
from functools import lru_cache


@lru_cache(maxsize=1024)
def compile_pattern(pattern: str) -> re.Pattern[str]:
    if not pattern or pattern.startswith("/"):
        raise ValueError(f"padrão inválido: {pattern!r}")
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z", re.S)


def matches(path: str, pattern: str) -> bool:
    return compile_pattern(pattern).match(path) is not None
