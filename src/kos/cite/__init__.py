"""Montagem de citações verificáveis (BL-11; CTR-07, ADR-kos-004).

A citação sai do índice (caminho, blob, localizador, texto), mas a verificação
não confia nele: o blob é relido do Git pelo `blob_oid` e o trecho é reconstruído
a partir do recorte de bytes.

- `verified_exact`: `sha256(normalize(recorte)) == quoted_sha256`.
- `verified_normalized`: o texto reconstruído confere, mas não é o recorte literal
  (HTML: texto visível do recorte).
- `unverified`: o blob não pôde ser lido ou o texto não confere; a nota diz por quê.

O clone é procurado no caminho informado (`repos`) ou no que a última ingestão
registrou em `repository.origin_url`.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from kos.errors import KosError
from kos.parsing import registry
from kos.parsing.lines import LineTable
from kos.parsing.normalize import normalize
from kos.parsing.profile import Locator

VERIFICATIONS = ("verified_exact", "verified_normalized", "derived", "unverified")
HUMAN_LABEL = {"unverified": "não verificada"}
_OID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


@dataclass
class Citation:
    citation_no: int
    fragment_key: str
    repo_name: str
    path_text: str
    commit_oid: str
    blob_oid: str
    locator: Locator
    quoted_text: str
    quoted_sha256: str
    verification: str
    is_generated: bool = False
    verification_note: str | None = None

    def to_json(self) -> dict:
        data = asdict(self)
        data["locator"] = self.locator.canonical()
        validate_citation(data)
        return data

    def human(self, max_chars: int = 240) -> str:
        loc = self.locator
        anchor = ""
        if loc.start_line is not None:
            anchor = f"#L{loc.start_line}" + (f"-L{loc.end_line}" if loc.end_line != loc.start_line else "")
        if loc.struct_path:
            anchor += f" {loc.struct_path}"
        label = HUMAN_LABEL.get(self.verification, self.verification)
        head = f"[{self.citation_no}] {self.repo_name}:{self.path_text}{anchor} @{self.commit_oid[:12]} ({label})"
        if self.is_generated:
            head += " [gerado]"
        quote = self.quoted_text if len(self.quoted_text) <= max_chars else self.quoted_text[:max_chars] + "…"
        lines = [head, '    "' + quote.replace("\n", "\n     ") + '"']
        if self.verification_note:
            lines.append(f"    nota: {self.verification_note}")
        return "\n".join(lines)


def validate_citation(data: dict) -> None:
    """Esquema mínimo de uma citação em JSON (TC-CIT-05, TC-CIT-06)."""
    problems = []
    for name in ("repo_name", "path_text", "quoted_text"):
        if not isinstance(data.get(name), str):
            problems.append(f"{name} ausente")
    for name in ("commit_oid", "blob_oid"):
        if not isinstance(data.get(name), str) or not _OID.fullmatch(data[name]):
            problems.append(f"{name} precisa ser o OID completo em hexadecimal")
    if data.get("verification") not in VERIFICATIONS:
        problems.append("verification ausente ou inválida")
    if not isinstance(data.get("quoted_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", data["quoted_sha256"]):
        problems.append("quoted_sha256 inválido")
    if problems:
        raise ValueError("; ".join(problems))


def cite(home: Path, fragment_keys: list[str], *, commit: str | None = None,
         repos: dict[str, Path] | None = None, lines: tuple[int, int] | None = None) -> list[Citation]:
    index = Path(home) / "index.sqlite"
    if not index.exists():
        raise KosError("E_NO_INDEXED_REVISION", f"{index} não existe; rode `kos ingest` antes")
    conn = sqlite3.connect(f"file:{index}?mode=ro", uri=True)
    try:
        rows = [_lookup(conn, key, commit) for key in fragment_keys]
    finally:
        conn.close()
    blobs: dict[tuple[str, str], bytes | str] = {}
    out = []
    for no, row in enumerate(rows, start=1):
        repo_dir = (repos or {}).get(row["repo"]) or _local_path(row["origin_url"])
        cache_key = (row["repo"], row["blob_oid"])
        if cache_key not in blobs:
            blobs[cache_key] = read_blob(repo_dir, row["blob_oid"])
        out.append(_build(no, row, blobs[cache_key], lines))
    return out


def _lookup(conn, key: str, commit: str | None) -> dict:
    sql = (
        "SELECT f.fragment_key, f.text, f.text_sha256, r.name, r.origin_url, a.path_text, v.blob_oid,"
        " v.media_type, v.is_generated, s.commit_oid,"
        " l.locator_type, l.start_byte, l.end_byte, l.start_line, l.end_line, l.start_col, l.end_col,"
        " l.struct_path, l.page_start, l.page_end"
        " FROM fragment f JOIN fragment_locator l USING (fragment_id)"
        " JOIN artifact_version v USING (version_id) JOIN artifact a USING (artifact_id)"
        " JOIN repository r USING (repo_id)"
        " JOIN revision_manifest m ON m.version_id = f.version_id AND m.artifact_id = a.artifact_id"
        " JOIN source_revision s ON s.revision_id = m.revision_id"
        " JOIN ingest_run i ON i.target_revision_id = s.revision_id AND i.status IN ('succeeded', 'partial')"
        " WHERE f.fragment_key = ? AND (? IS NULL OR s.commit_oid = ?)"
        " ORDER BY i.run_id DESC LIMIT 1")
    row = conn.execute(sql, (key, commit, commit)).fetchone()
    if row is None:
        where = f" na revisão {commit}" if commit else " em nenhuma revisão indexada"
        raise KosError("E_FRAGMENT_GONE", f"fragmento {key} não existe{where}")
    (key, text, sha, repo, origin, path, blob, media, generated, commit_oid, *loc) = row
    return {"key": key, "text": text, "sha": sha, "repo": repo, "origin_url": origin, "path": path,
            "blob_oid": blob, "media_type": media, "is_generated": bool(generated), "commit": commit_oid,
            "locator": Locator(loc[0], start_byte=loc[1], end_byte=loc[2], start_line=loc[3], end_line=loc[4],
                               start_col=loc[5], end_col=loc[6], struct_path=loc[7], page_start=loc[8],
                               page_end=loc[9])}


def _local_path(origin_url: str | None) -> Path | None:
    if not origin_url:
        return None
    parsed = urlparse(origin_url)
    return Path(unquote(parsed.path)) if parsed.scheme == "file" else None


def read_blob(repo_dir: Path | None, blob_oid: str) -> bytes | str:
    """Conteúdo do blob, ou a nota E_BLOB_UNREADABLE explicando por que não foi lido."""
    if repo_dir is None:
        return "E_BLOB_UNREADABLE: caminho do repositório desconhecido"
    try:
        proc = subprocess.run(["git", "-C", str(repo_dir), "cat-file", "blob", blob_oid],
                              capture_output=True, check=False)
    except FileNotFoundError:
        return "E_BLOB_UNREADABLE: o executável git não foi encontrado"
    if proc.returncode != 0:
        return f"E_BLOB_UNREADABLE: blob {blob_oid[:12]} não está em {repo_dir}"
    return proc.stdout


def _build(no: int, row: dict, blob: bytes | str, lines: tuple[int, int] | None) -> Citation:
    loc: Locator = row["locator"]
    quoted, expected_sha = row["text"], row["sha"]
    if lines is not None:
        loc, quoted = _subrange(row, blob, lines)
        expected_sha = hashlib.sha256(quoted.encode("utf-8")).hexdigest()
    base = dict(citation_no=no, fragment_key=row["key"], repo_name=row["repo"], path_text=row["path"],
                commit_oid=row["commit"], blob_oid=row["blob_oid"], locator=loc, quoted_text=quoted,
                quoted_sha256=expected_sha, is_generated=row["is_generated"])
    verification, note = verify(blob, loc, expected_sha, row["media_type"])
    return Citation(**base, verification=verification, verification_note=note)


def verify(blob: bytes | str, loc: Locator, expected_sha: str, media_type: str) -> tuple[str, str | None]:
    """Estado de verificação de um trecho contra o blob relido: (estado, nota).

    `blob` em texto é a nota de falha de leitura de `read_blob`. Usada pela citação
    e pela reconferência da auditoria, que não tem índice (TC-AUD-05).
    """
    if isinstance(blob, str):
        return "unverified", blob
    if loc.start_byte is None or loc.end_byte is None or loc.end_byte > len(blob):
        return "unverified", "o intervalo de bytes não cabe no blob relido"
    raw = blob[loc.start_byte:loc.end_byte]
    literal = normalize(raw)
    if hashlib.sha256(literal.encode("utf-8")).hexdigest() == expected_sha:
        return "verified_exact", None
    rebuilt = registry.expected_text(media_type, raw)
    if rebuilt != literal and hashlib.sha256(rebuilt.encode("utf-8")).hexdigest() == expected_sha:
        return "verified_normalized", "texto visível do recorte HTML, sem marcação"
    return "unverified", "o texto relido do blob não confere com o trecho indexado"


def _subrange(row: dict, blob: bytes | str, lines: tuple[int, int]) -> tuple[Locator, str]:
    loc: Locator = row["locator"]
    first, last = lines
    if loc.start_line is None or not (loc.start_line <= first <= last <= loc.end_line):
        raise KosError("E_SUBRANGE_OUT_OF_BOUNDS",
                       f"linhas {first}-{last} fora do fragmento (L{loc.start_line}-L{loc.end_line})")
    if row["media_type"] in registry.VISIBLE_TEXT_MEDIA_TYPES:
        raise KosError("E_SUBRANGE_OUT_OF_BOUNDS", "sub-intervalo não é suportado em fragmentos HTML")
    if isinstance(blob, str):
        raise KosError("E_BLOB_UNREADABLE", f"o sub-intervalo exige reler o blob: {blob}")
    table = LineTable(blob)
    start = max(table.start(first - 1), loc.start_byte)
    end = min(table.end(last - 1), loc.end_byte)
    sub = Locator(loc.type, start_byte=start, end_byte=end, start_line=first, end_line=last,
                  struct_path=loc.struct_path)
    return sub, normalize(blob[start:end])
