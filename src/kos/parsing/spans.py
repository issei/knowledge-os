"""Utilitários comuns aos parsers: mapa caractere → byte e fragmento a partir de um recorte.

Parsers de terceiros (PyYAML) e o leitor de JSON trabalham sobre o texto
decodificado e devolvem posições em caracteres; o localizador guarda bytes do
blob original. `CharMap` faz a conversão exata, contando o BOM retirado por
`decode`.
"""

from __future__ import annotations

from itertools import accumulate

from kos.parsing.lines import LineTable
from kos.parsing.normalize import normalize
from kos.parsing.profile import Locator
from kos.parsing.types import Fragment

_BOM = "﻿".encode("utf-8")
_SPACE = b" \t\r\n"


class CharMap:
    def __init__(self, blob: bytes, text: str):
        self._base = len(_BOM) if blob.startswith(_BOM) else 0
        self._ascii = len(text) == len(blob) - self._base
        self._offsets = None if self._ascii else [0, *accumulate(len(c.encode("utf-8")) for c in text)]

    def byte(self, char_index: int) -> int:
        return self._base + (char_index if self._ascii else self._offsets[char_index])


def fragment(blob: bytes, lines: LineTable, ordinal: int, kind: str, start: int, end: int,
             *, locator_type: str = "text", heading_path: str | None = None,
             struct_path: str | None = None) -> Fragment | None:
    """Fragmento sobre blob[start:end], sem espaços nas pontas; None se o recorte for vazio."""
    while end > start and blob[end - 1] in _SPACE:
        end -= 1
    while start < end and blob[start] in _SPACE:
        start += 1
    if start >= end:
        return None
    return Fragment(
        ordinal=ordinal, fragment_kind=kind, heading_path=heading_path,
        text=normalize(blob[start:end]),
        locator=Locator(locator_type, start_byte=start, end_byte=end,
                        start_line=lines.line_of(start) + 1, end_line=lines.line_of(end - 1) + 1,
                        struct_path=struct_path),
    )


def pointer_token(key: object) -> str:
    """Um segmento de JSON Pointer (RFC 6901)."""
    return str(key).replace("~", "~0").replace("/", "~1")
