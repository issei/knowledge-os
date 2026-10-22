"""HTML com texto visível e posições no original (BL-22; CTR-02, ADR-kos-003 item 5).

Recorte: uma seção por cabeçalho `h1`..`h6`, com `heading_path` como no
Markdown; o que vem antes do primeiro cabeçalho (título da página, descrição,
navegação) é a seção sem `heading_path`. Seções longas são divididas no início
de um elemento de bloco.

Diferente dos outros formatos, o texto do fragmento não é o recorte de bytes: é
o texto visível do recorte, `visible_text(normalize(blob[start:end]))` — sem
marcação, com entidades decodificadas e espaços colapsados. A função só depende
do recorte, então a citação continua reconferível relendo o blob, mas como
`verified_normalized` (CTR-07), nunca `verified_exact`.

Usa `html.parser` da biblioteca padrão. Conteúdo de `script`, `style`,
`template`, `noscript`, `svg`, `math`, `iframe`, `object` e `canvas` não é texto
visível. A descrição em `<meta name="description">` entra como uma linha.
"""

from __future__ import annotations

import platform
import unicodedata
from html.parser import HTMLParser

from kos.errors import KosError
from kos.parsing.lines import LineTable
from kos.parsing.normalize import NORMALIZER_VERSION, decode, normalize
from kos.parsing.profile import Locator, Profile
from kos.parsing.spans import CharMap
from kos.parsing.types import Fragment, ParseResult

PROFILE = Profile(
    # html.parser muda entre versões de correção do Python; a versão entra no perfil.
    profile_name="html-visible-text", parser_name="kos.parsing.html_doc",
    parser_version=f"1+py{platform.python_version()}",
    normalizer_version=NORMALIZER_VERSION, config={"max_section_lines": 80, "meta_description": True},
)

SKIP_TAGS = frozenset({"script", "style", "template", "noscript", "svg", "math", "iframe", "object", "canvas"})
BLOCK_TAGS = frozenset({
    "address", "article", "aside", "blockquote", "body", "br", "caption", "dd", "details", "dialog",
    "div", "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4",
    "h5", "h6", "head", "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section", "summary",
    "table", "tbody", "tfoot", "thead", "title", "tr", "ul",
})
HEADINGS = {f"h{i}": i for i in range(1, 7)}


def visible_text(source: str) -> str:
    """Texto visível de um trecho HTML: uma linha por bloco, espaços colapsados, NFC."""
    extractor = _Extractor()
    extractor.feed(source)
    extractor.close()
    lines = (" ".join(line.split()) for line in "".join(extractor.pieces).split("\n"))
    return unicodedata.normalize("NFC", "\n".join(line for line in lines if line))


def parse(blob: bytes, profile: Profile = PROFILE) -> ParseResult:
    try:
        text = decode(blob)
    except KosError as err:
        return ParseResult(status="failed", reason_code=err.code)
    scanner = _Scanner(text)
    scanner.feed(text)
    scanner.close()
    cmap, lines = CharMap(blob, text), LineTable(blob)
    max_lines = profile.config["max_section_lines"]

    fragments: list[Fragment] = []
    stack: list[tuple[int, str]] = []
    for section in _sections(scanner.events):
        head = section[0]
        if head[0] == "heading":
            level, title = head[3], " ".join(visible_text(text[head[1]:head[2]]).split())
            stack = [s for s in stack if s[0] < level] + [(level, title)]
        heading_path = " > ".join(t for _, t in stack if t) or None
        for start, end in _chunks(section, lines, cmap, max_lines):
            frag = _fragment(blob, lines, len(fragments), heading_path, cmap.byte(start), cmap.byte(end))
            if frag is not None:
                fragments.append(frag)
    return ParseResult(status="parsed", fragments=tuple(fragments))


def _sections(events: list[tuple]) -> list[list[tuple]]:
    sections: list[list[tuple]] = []
    for event in events:
        if event[0] == "heading" or not sections:
            sections.append([event])
        else:
            sections[-1].append(event)
    return sections


def _chunks(section, lines: LineTable, cmap: CharMap, max_lines: int) -> list[tuple[int, int]]:
    """Intervalos [início, fim) em caracteres: do primeiro conteúdo ao fim do último texto visível."""
    chunks, start, end = [], None, None
    for event in section:
        kind, pos = event[0], event[1]
        if kind == "block" and start is not None and end is not None:
            if lines.line_of(cmap.byte(pos)) - lines.line_of(cmap.byte(start)) >= max_lines:
                chunks.append((start, end))
                start, end = None, None
        if kind == "heading":
            start = pos
        elif kind == "run":
            start = pos if start is None else start
            end = event[2]
    if start is not None and end is not None:
        chunks.append((start, end))
    return chunks


def _fragment(blob, lines: LineTable, ordinal, heading_path, start, end) -> Fragment | None:
    text = visible_text(normalize(blob[start:end]))
    if not text:
        return None
    return Fragment(
        ordinal=ordinal, fragment_kind="section", heading_path=heading_path, text=text,
        locator=Locator("text", start_byte=start, end_byte=end,
                        start_line=lines.line_of(start) + 1, end_line=lines.line_of(end - 1) + 1),
    )


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pieces: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip += 1
        elif self.skip:
            return
        elif tag in BLOCK_TAGS:
            self.pieces.append("\n")
        elif tag == "meta" and _is_description(attrs):
            self.pieces.append("\n" + (dict(attrs).get("content") or "") + "\n")
        elif tag in ("td", "th"):
            self.pieces.append(" ")

    def handle_startendtag(self, tag, attrs):
        if tag not in SKIP_TAGS:  # <svg/> não abre contexto
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip = max(self.skip - 1, 0)
        elif not self.skip and tag in BLOCK_TAGS:
            self.pieces.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.pieces.append(data)


class _Scanner(HTMLParser):
    """Eventos com posição em caracteres: ("run", início, fim), ("block", pos), ("heading", início, fim, nível).

    Sem `convert_charrefs`, cada dado e cada entidade chega com sua posição no
    fonte; um trecho de texto termina onde começa o próximo evento.
    """

    def __init__(self, text: str):
        super().__init__(convert_charrefs=False)
        self._text = text
        self._line_starts = [0] + [i + 1 for i, ch in enumerate(text) if ch == "\n"]
        self._text_len = len(text)
        self.events: list[tuple] = []
        self._skip = 0
        self._run: int | None = None
        self._heading: tuple[int, int] | None = None  # (início, nível)

    def _pos(self) -> int:
        line, col = self.getpos()
        return self._line_starts[line - 1] + col

    def _close_run(self, pos: int) -> None:
        if self._run is not None:
            self.events.append(("run", self._run, pos))
            self._run = None

    def handle_starttag(self, tag, attrs):
        pos = self._pos()
        self._close_run(pos)
        if tag in SKIP_TAGS:
            self._skip += 1
            return
        if self._skip:
            return
        if tag in HEADINGS and self._heading is None:
            self._heading = (pos, HEADINGS[tag])
        elif tag in BLOCK_TAGS:
            self.events.append(("block", pos))
        elif tag == "meta" and _is_description(attrs) and (dict(attrs).get("content") or "").strip():
            end = pos + len(self.get_starttag_text() or "")
            self.events.append(("run", pos, end))

    def handle_startendtag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._close_run(self._pos())
        else:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        pos = self._pos()
        self._close_run(pos)
        if tag in SKIP_TAGS:
            self._skip = max(self._skip - 1, 0)
        elif not self._skip and self._heading and HEADINGS.get(tag) == self._heading[1]:
            end = self._end_of_tag(pos)
            self.events.append(("heading", self._heading[0], end, self._heading[1]))
            self.events.append(("run", self._heading[0], end))
            self._heading = None

    def _end_of_tag(self, pos: int) -> int:
        close = self._text.find(">", pos)
        return close + 1 if close != -1 else self._text_len

    def handle_data(self, data):
        if not self.skip:
            self.pieces.append(data)


class _Scanner(HTMLParser):
    """Eventos com posição em caracteres: ("run", início, fim), ("block", pos), ("heading", início, fim, nível).

    Sem `convert_charrefs`, cada dado e cada entidade chega com sua posição no
    fonte; um trecho de texto termina onde começa o próximo evento.
    """

    def __init__(self, text: str):
        super().__init__(convert_charrefs=False)
        self._text = text
        self._line_starts = [0] + [i + 1 for i, ch in enumerate(text) if ch == "\n"]
        self._text_len = len(text)
        self.events: list[tuple] = []
        self._skip = 0
        self._run: int | None = None
        self._heading: tuple[int, int] | None = None  # (início, nível)

    def _pos(self) -> int:
        line, col = self.getpos()
        return self._line_starts[line - 1] + col

    def _close_run(self, pos: int) -> None:
        if self._run is not None:
            self.events.append(("run", self._run, pos))
            self._run = None

    def handle_starttag(self, tag, attrs):
        pos = self._pos()
        self._close_run(pos)
        if tag in SKIP_TAGS:
            self._skip += 1
            return
        if self._skip:
            return
        if tag in HEADINGS and self._heading is None:
            self._heading = (pos, HEADINGS[tag])
        elif tag in BLOCK_TAGS:
            self.events.append(("block", pos))
        elif tag == "meta" and _is_description(attrs) and (dict(attrs).get("content") or "").strip():
            end = pos + len(self.get_starttag_text() or "")
            self.events.append(("run", pos, end))

    def handle_startendtag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._close_run(self._pos())
        else:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        pos = self._pos()
        self._close_run(pos)
        if tag in SKIP_TAGS:
            self._skip = max(self._skip - 1, 0)
        elif not self._skip and self._heading and HEADINGS.get(tag) == self._heading[1]:
            end = self._end_of_tag(pos)
            self.events.append(("heading", self._heading[0], end, self._heading[1]))
            self.events.append(("run", self._heading[0], end))
            self._heading = None

    def _end_of_tag(self, pos: int) -> int:
        # rawdata ainda contém o fonte a partir da posição atual do parser
        rel = pos - self._consumed()
        close = self.rawdata.find(">", rel)
        return pos + (close - rel + 1 if close != -1 else 0)

    def _consumed(self) -> int:
        return self._text_len - len(self.rawdata)

    def handle_data(self, data):
        pos = self._pos()
        if self._skip or self._heading or not data.strip():
            self._close_run(pos)
            return
        if self._run is None:
            self._run = pos

    def handle_entityref(self, name):
        self._entity(self._pos())

    def handle_charref(self, name):
        self._entity(self._pos())

    def _entity(self, pos):
        if not self._skip and not self._heading and self._run is None:
            self._run = pos

    def handle_comment(self, data):
        self._close_run(self._pos())

    def handle_decl(self, decl):
        self._close_run(self._pos())

    def handle_pi(self, data):
        self._close_run(self._pos())

    def unknown_decl(self, data):
        self._close_run(self._pos())

    def close(self):
        super().close()
        self._close_run(self._text_len)
        if self._heading is not None:  # cabeçalho sem fechamento
            self.events.append(("heading", self._heading[0], self._text_len, self._heading[1]))
            self._heading = None


def _is_description(attrs) -> bool:
    return any(k == "name" and (v or "").lower() == "description" for k, v in attrs)
