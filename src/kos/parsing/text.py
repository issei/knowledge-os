"""Texto puro e código como texto, em janelas por parágrafo (BL-06, BL-07; CTR-02).

Parágrafo = sequência de linhas não vazias. Parágrafos vizinhos são agrupados
enquanto a janela couber em `max_window_lines`; um parágrafo maior que isso é
cortado em janelas de linhas inteiras. O perfil de código é provisório até o
Tree-sitter (BL-15): mesmas janelas, `fragment_kind = code_block`.

Também é o recurso dos parsers estruturados quando a sintaxe está quebrada.
"""

from __future__ import annotations

from kos.errors import KosError
from kos.parsing.lines import LineTable
from kos.parsing.normalize import NORMALIZER_VERSION, decode
from kos.parsing.profile import Profile
from kos.parsing.spans import fragment
from kos.parsing.types import Fragment, ParseResult

PARSER_VERSION = "1"

PROFILE = Profile(
    profile_name="text-windows", parser_name="kos.parsing.text",
    parser_version=PARSER_VERSION, normalizer_version=NORMALIZER_VERSION,
    config={"max_window_lines": 40, "fragment_kind": "paragraph"},
)

CODE_PROFILE = Profile(
    profile_name="code-as-text", parser_name="kos.parsing.text",
    parser_version=PARSER_VERSION, normalizer_version=NORMALIZER_VERSION,
    config={"max_window_lines": 60, "fragment_kind": "code_block"},
)


def parse(blob: bytes, profile: Profile = PROFILE) -> ParseResult:
    try:
        decode(blob)
    except KosError as err:
        return ParseResult(status="failed", reason_code=err.code)
    return ParseResult(status="parsed", fragments=tuple(
        windows(blob, profile.config["max_window_lines"], profile.config["fragment_kind"])))


def windows(blob: bytes, max_lines: int, kind: str) -> list[Fragment]:
    lines = LineTable(blob)
    paragraphs, start = [], None
    for i in range(len(lines)):
        blank = lines.is_blank(i)
        if not blank and start is None:
            start = i
        elif blank and start is not None:
            paragraphs.append((start, i))
            start = None
    if start is not None:
        paragraphs.append((start, len(lines)))

    spans, current = [], None
    for p_start, p_end in paragraphs:
        while p_end - p_start > max_lines:  # parágrafo longo: janelas de linhas inteiras
            if current:
                spans.append(current)
                current = None
            spans.append((p_start, p_start + max_lines))
            p_start += max_lines
        if current and p_end - current[0] <= max_lines:
            current = (current[0], p_end)
        else:
            if current:
                spans.append(current)
            current = (p_start, p_end)
    if current:
        spans.append(current)

    fragments: list[Fragment] = []
    for first, last in spans:
        frag = fragment(blob, lines, len(fragments), kind, lines.start(first), lines.end(last - 1))
        if frag is not None:
            fragments.append(frag)
    return fragments


def fallback(blob: bytes, reason: str) -> ParseResult:
    """Sintaxe quebrada: o arquivo continua citável por janelas de texto, com aviso."""
    return ParseResult(status="parsed_with_warnings", reason_code="E_PARSE_SYNTAX",
                       fragments=tuple(windows(blob, PROFILE.config["max_window_lines"], "paragraph")),
                       warnings=(f"E_PARSE_SYNTAX: {reason}",))
