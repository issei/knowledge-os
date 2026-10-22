"""Escolha do parser e do perfil pelo tipo de mídia da descoberta (CTR-02).

`expected_text` diz como o texto de um fragmento se reconstrói a partir do
recorte de bytes: igual ao recorte normalizado em todos os formatos, menos HTML,
cujo texto é o visível do recorte (`verified_normalized`).
"""

from __future__ import annotations

from kos.parsing import html_doc, json_doc, markdown, text, yaml_doc
from kos.parsing.normalize import normalize
from kos.parsing.profile import Profile
from kos.parsing.types import ParseResult

CODE_MEDIA_TYPES = frozenset({"text/javascript", "text/x-python", "text/x-shellscript", "text/css"})
PENDING_MEDIA_TYPES: frozenset[str] = frozenset()
VISIBLE_TEXT_MEDIA_TYPES = frozenset({"text/html"})

_BY_MEDIA_TYPE = {
    "text/markdown": (markdown.parse, markdown.PROFILE),
    "application/json": (json_doc.parse, json_doc.PROFILE),
    "application/yaml": (yaml_doc.parse, yaml_doc.PROFILE),
    "text/html": (html_doc.parse, html_doc.PROFILE),
    **{m: (text.parse, text.CODE_PROFILE) for m in CODE_MEDIA_TYPES},
}


def profile_for(media_type: str) -> Profile | None:
    if media_type in PENDING_MEDIA_TYPES:
        return None
    return _BY_MEDIA_TYPE.get(media_type, (text.parse, text.PROFILE))[1]


def parse(blob: bytes, media_type: str) -> tuple[Profile | None, ParseResult]:
    if media_type in PENDING_MEDIA_TYPES:
        return None, ParseResult(status="skipped", reason_code="E_PARSER_UNAVAILABLE")
    fn, profile = _BY_MEDIA_TYPE.get(media_type, (text.parse, text.PROFILE))
    return profile, fn(blob, profile)


def expected_text(media_type: str, raw: bytes) -> str:
    """Texto que um fragmento sobre `raw` deve ter; base da verificação da citação."""
    if media_type in VISIBLE_TEXT_MEDIA_TYPES:
        return html_doc.visible_text(normalize(raw))
    return normalize(raw)
