"""JSON com posições no original (BL-06; CTR-02, TC-PRS-04).

O módulo `json` da biblioteca padrão não informa posições, então a estrutura é
lida por um analisador descendente pequeno, e o conteúdo das strings fica a
cargo de `json.decoder.scanstring` (as mesmas regras de escape do `json`).
Sintaxe inválida (ex.: JSON com comentários) cai em janelas de texto com aviso.
"""

from __future__ import annotations

import re
from json.decoder import scanstring

from kos.errors import KosError
from kos.parsing import text as text_parser
from kos.parsing.normalize import NORMALIZER_VERSION, decode
from kos.parsing.profile import Profile
from kos.parsing.structured import Node, fragments
from kos.parsing.types import ParseResult

PROFILE = Profile(
    profile_name="json-native", parser_name="kos.parsing.json_doc", parser_version="1",
    normalizer_version=NORMALIZER_VERSION, config={"levels": 2, "struct_path": "json-pointer"},
)

_WS = re.compile(r"[ \t\n\r]*")
_NUMBER = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][-+]?\d+)?")
_LITERALS = ("true", "false", "null")


class _SyntaxError(Exception):
    pass


def parse(blob: bytes, profile: Profile = PROFILE) -> ParseResult:
    try:
        text = decode(blob)
    except KosError as err:
        return ParseResult(status="failed", reason_code=err.code)
    if not text.strip():
        return ParseResult(status="parsed")
    try:
        root = read_json(text)
    except (_SyntaxError, RecursionError) as exc:
        return text_parser.fallback(blob, str(exc) or "aninhamento profundo demais")
    return ParseResult(status="parsed", fragments=tuple(fragments(blob, text, [("", root)], "json_node")))


def read_json(text: str) -> Node:
    pos = _skip(text, 0)
    node, pos = _value(text, pos)
    if _skip(text, pos) != len(text):
        raise _SyntaxError(f"conteúdo depois do valor (caractere {pos})")
    return node


def _skip(text: str, pos: int) -> int:
    return _WS.match(text, pos).end()


def _value(text: str, pos: int) -> tuple[Node, int]:
    if pos >= len(text):
        raise _SyntaxError("fim inesperado")
    ch = text[pos]
    if ch == "{":
        return _container(text, pos, "}", keyed=True)
    if ch == "[":
        return _container(text, pos, "]", keyed=False)
    if ch == '"':
        _, end = _string(text, pos)
        return Node(pos, end), end
    m = _NUMBER.match(text, pos)
    if m:
        return Node(pos, m.end()), m.end()
    for lit in _LITERALS:
        if text.startswith(lit, pos):
            return Node(pos, pos + len(lit)), pos + len(lit)
    raise _SyntaxError(f"valor inválido no caractere {pos}")


def _string(text: str, pos: int) -> tuple[str, int]:
    try:
        return scanstring(text, pos + 1, True)
    except ValueError as exc:
        raise _SyntaxError(str(exc)) from exc


def _container(text: str, start: int, close: str, keyed: bool) -> tuple[Node, int]:
    node = Node(start, start)
    pos = _skip(text, start + 1)
    if text.startswith(close, pos):
        node.end = pos + 1
        return node, node.end
    index = 0
    while True:
        child_start = pos
        if keyed:
            if not text.startswith('"', pos):
                raise _SyntaxError(f"chave esperada no caractere {pos}")
            key, pos = _string(text, pos)
            pos = _skip(text, pos)
            if not text.startswith(":", pos):
                raise _SyntaxError(f"':' esperado no caractere {pos}")
            pos = _skip(text, pos + 1)
        else:
            key = index
        child, pos = _value(text, pos)
        node.children.append((key, child_start, child))
        index += 1
        pos = _skip(text, pos)
        if text.startswith(",", pos):
            pos = _skip(text, pos + 1)
        elif text.startswith(close, pos):
            node.end = pos + 1
            return node, node.end
        else:
            raise _SyntaxError(f"',' ou '{close}' esperado no caractere {pos}")
