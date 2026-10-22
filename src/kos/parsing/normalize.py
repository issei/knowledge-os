"""Normalizador único de texto (CTR-02 inv. 2; RSK-05).

A mesma função é usada ao indexar e ao verificar citações: o texto de um
fragmento é sempre `normalize(blob[start_byte:end_byte])`. Mudar o
comportamento exige subir NORMALIZER_VERSION, o que muda a impressão digital
de todos os perfis.
"""

from __future__ import annotations

import unicodedata

from kos.errors import KosError

NORMALIZER_VERSION = "1"


def decode(raw: bytes) -> str:
    """UTF-8 estrito, sem BOM. Falha com E_DECODE."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise KosError("E_DECODE", f"conteúdo não é UTF-8 válido (byte {exc.start})") from exc
    return text[1:] if text.startswith("﻿") else text


def normalize(raw: bytes) -> str:
    """Bytes de um trecho → texto indexado: UTF-8, quebras de linha LF, Unicode NFC."""
    text = decode(raw).replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", text)
