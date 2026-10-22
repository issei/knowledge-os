"""Parser Markdown com posições no original (BL-05; CTR-02, ADR-kos-003).

Recorte: uma seção por cabeçalho, com `heading_path` ("H1 > H2"). Seções mais
longas que `max_section_lines` são divididas entre blocos de nível superior,
nunca no meio de um bloco (bloco de código, tabela e lista ficam inteiros).
Front matter YAML no início vira um fragmento `yaml_node`.

O texto de cada fragmento é sempre `normalize(blob[start_byte:end_byte])`, o que
torna toda citação verificável por bytes (TC-PRS-01).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

import markdown_it

from kos.errors import KosError
from kos.parsing.lines import LineTable
from kos.parsing.normalize import NORMALIZER_VERSION, decode, normalize
from kos.parsing.profile import Locator, Profile
from kos.parsing.types import Fragment, ParseResult

PROFILE = Profile(
    profile_name="md-native",
    parser_name="markdown-it-py",
    parser_version=markdown_it.__version__,
    normalizer_version=NORMALIZER_VERSION,
    config={"preset": "commonmark", "tables": True, "front_matter": True, "max_section_lines": 60},
)


@dataclass
class _Block:
    start: int  # linha 0-based, inclusiva
    end: int  # linha 0-based, exclusiva
    heading_level: int | None = None
    title: str | None = None


def parse(blob: bytes, profile: Profile = PROFILE) -> ParseResult:
    try:
        text = decode(blob)
    except KosError as err:
        return ParseResult(status="failed", reason_code=err.code)
    lines = LineTable(blob)
    if not text.strip():
        return ParseResult(status="parsed")

    fragments: list[Fragment] = []
    md_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    fm_end = _front_matter_end(md_lines) if profile.config.get("front_matter") else None
    if fm_end is not None:
        fragments.append(_fragment(blob, lines, len(fragments), "yaml_node", None, 0, fm_end + 1))
        # Linhas em branco no lugar do front matter preservam a numeração para o markdown-it.
        md_lines = [""] * (fm_end + 1) + md_lines[fm_end + 1:]

    md = markdown_it.MarkdownIt(profile.config.get("preset", "commonmark"))
    if profile.config.get("tables"):
        md.enable("table")
    tokens = md.parse("\n".join(md_lines))
    blocks = _top_level_blocks(tokens)

    max_lines = profile.config["max_section_lines"]
    stack: list[tuple[int, str]] = []
    for section in _sections(blocks):
        head = section[0]
        if head.heading_level is not None:
            stack = [s for s in stack if s[0] < head.heading_level] + [(head.heading_level, head.title)]
        heading_path = " > ".join(t for _, t in stack) or None
        for chunk in _split(section, max_lines):
            frag = _fragment(blob, lines, len(fragments), "section", heading_path,
                             chunk[0].start, chunk[-1].end)
            if frag is not None:
                fragments.append(frag)
    return ParseResult(status="parsed", fragments=tuple(fragments))


def _front_matter_end(md_lines: list[str]) -> int | None:
    if not md_lines or md_lines[0].lstrip("﻿").rstrip() != "---":
        return None
    for i in range(1, len(md_lines)):
        if md_lines[i].rstrip() in ("---", "..."):
            return i
    return None


def _top_level_blocks(tokens) -> list[_Block]:
    blocks = []
    for i, tok in enumerate(tokens):
        if tok.level != 0 or tok.map is None or tok.nesting == -1:
            continue
        block = _Block(tok.map[0], tok.map[1])
        if tok.type == "heading_open":
            block.heading_level = int(tok.tag[1])
            block.title = unicodedata.normalize("NFC", tokens[i + 1].content.strip())
        blocks.append(block)
    return blocks


def _sections(blocks: list[_Block]) -> list[list[_Block]]:
    sections: list[list[_Block]] = []
    for block in blocks:
        if block.heading_level is not None or not sections:
            sections.append([block])
        else:
            sections[-1].append(block)
    return sections


def _split(section: list[_Block], max_lines: int) -> list[list[_Block]]:
    chunks, current = [], []
    for block in section:
        if current and block.end - current[0].start > max_lines:
            chunks.append(current)
            current = []
        current.append(block)
    if current:
        chunks.append(current)
    return chunks


def _fragment(blob, lines: LineTable, ordinal, kind, heading_path, start, end) -> Fragment | None:
    end = min(end, len(lines))
    while end > start and lines.is_blank(end - 1):
        end -= 1
    while start < end and lines.is_blank(start):
        start += 1
    if start >= end:
        return None
    start_byte, end_byte = lines.start(start), lines.end(end - 1)
    return Fragment(
        ordinal=ordinal, fragment_kind=kind, heading_path=heading_path,
        text=normalize(blob[start_byte:end_byte]),
        locator=Locator("text", start_byte=start_byte, end_byte=end_byte,
                        start_line=start + 1, end_line=end),
    )
