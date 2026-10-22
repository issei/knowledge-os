"""Tabela de linhas sobre os bytes originais do blob.

As quebras reconhecidas são as mesmas do markdown-it (`\\r\\n`, `\\r`, `\\n`),
para que o número de linha de um token corresponda à mesma linha nos bytes.
Linhas são indexadas a partir de 0 aqui; os localizadores expõem 1-based.
"""

from __future__ import annotations

import re
from bisect import bisect_right

_BREAK = re.compile(rb"\r\n|\r|\n")


class LineTable:
    def __init__(self, blob: bytes):
        self.blob = blob
        self._starts = [0]
        self._ends = []  # fim do conteúdo da linha, sem o terminador
        for m in _BREAK.finditer(blob):
            self._ends.append(m.start())
            self._starts.append(m.end())
        self._ends.append(len(blob))
        # Um arquivo terminado em quebra não tem uma última linha vazia "real".
        if len(self._starts) > 1 and self._starts[-1] == len(blob):
            self._starts.pop()
            self._ends.pop()

    def __len__(self) -> int:
        return len(self._starts)

    def start(self, line: int) -> int:
        return self._starts[line]

    def end(self, line: int) -> int:
        return self._ends[line]

    def is_blank(self, line: int) -> bool:
        return not self.blob[self._starts[line]:self._ends[line]].strip()

    def line_of(self, byte: int) -> int:
        """Linha (0-based) que contém o byte; um offset no fim do blob cai na última linha."""
        return max(bisect_right(self._starts, byte) - 1, 0)
