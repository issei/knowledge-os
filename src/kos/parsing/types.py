"""Tipos de saída dos parsers (CTR-02)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from kos.parsing.profile import Locator


@dataclass(frozen=True)
class Fragment:
    ordinal: int
    fragment_kind: str
    heading_path: str | None
    text: str
    locator: Locator
    ident_terms: str | None = None

    @property
    def text_sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ParseResult:
    status: str  # parsed | parsed_with_warnings | skipped | failed
    fragments: tuple[Fragment, ...] = ()
    reason_code: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
