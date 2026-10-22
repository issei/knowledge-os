"""Perfis de processamento, localizadores e chave de fragmento (BL-04).

Um perfil fixa tudo o que muda o resultado do parsing: parser, versão, gramática,
versão do normalizador e configuração. Sua impressão digital entra na chave de
cada fragmento, então trocar qualquer um desses campos gera chaves novas e
invalida o cache de forma explícita (docs/fase-0/02-modelo-de-dados.md §1).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field

LOCATOR_TYPES = ("text", "structured", "code", "page")


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Profile:
    profile_name: str
    parser_name: str
    parser_version: str
    normalizer_version: str
    config: dict = field(default_factory=dict)
    grammar_version: str | None = None

    def as_dict(self) -> dict:
        return {
            "profile_name": self.profile_name, "parser_name": self.parser_name,
            "parser_version": self.parser_version, "grammar_version": self.grammar_version,
            "normalizer_version": self.normalizer_version, "config": self.config,
        }

    @property
    def fingerprint(self) -> str:
        return _sha256(canonical_json(self.as_dict()))


@dataclass(frozen=True)
class Locator:
    """Localizador polimórfico. Bytes são [start, end) no blob; linhas são 1-based e inclusivas."""

    type: str
    start_byte: int | None = None
    end_byte: int | None = None
    start_line: int | None = None
    end_line: int | None = None
    start_col: int | None = None
    end_col: int | None = None
    struct_path: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    symbol: str | None = None  # nome qualificado; o symbol_id do banco não é estável

    def __post_init__(self) -> None:
        if self.type not in LOCATOR_TYPES:
            raise ValueError(f"tipo de localizador inválido: {self.type!r}")
        if self.type == "page":
            if self.page_start is None or self.page_end is None or self.page_end < self.page_start:
                raise ValueError("localizador de página exige page_start <= page_end")
        else:
            if self.start_byte is None or self.end_byte is None or not 0 <= self.start_byte <= self.end_byte:
                raise ValueError("localizador textual exige 0 <= start_byte <= end_byte")
        if self.start_line is not None and (self.end_line is None or self.end_line < self.start_line):
            raise ValueError("end_line precisa ser >= start_line")

    def canonical(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


def fragment_key(repo_name: str, path_bytes: bytes, blob_oid: str, profile_fingerprint: str,
                 locator: Locator) -> str:
    """Identidade estável do fragmento: SHA-256 de repositório ‖ caminho ‖ blob ‖ perfil ‖ localizador.

    O caminho entra porque o mesmo blob pode estar em dois arquivos (cópias, páginas
    geradas iguais à fonte); sem ele, os dois fragmentos teriam a mesma chave e a
    citação não saberia qual arquivo apontar.
    """
    return _sha256("\x1f".join((repo_name, path_bytes.hex(), blob_oid, profile_fingerprint,
                                 canonical_json(locator.canonical()))))


def register_profile(conn: sqlite3.Connection, profile: Profile) -> int:
    """Grava o perfil em processing_profile (idempotente) e devolve o profile_id."""
    conn.execute(
        "INSERT OR IGNORE INTO processing_profile(profile_name, parser_name, parser_version,"
        " grammar_version, normalizer_version, config_json, profile_fingerprint)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (profile.profile_name, profile.parser_name, profile.parser_version,
         profile.grammar_version, profile.normalizer_version,
         canonical_json(profile.config), profile.fingerprint),
    )
    return conn.execute(
        "SELECT profile_id FROM processing_profile WHERE profile_fingerprint = ?",
        (profile.fingerprint,),
    ).fetchone()[0]
