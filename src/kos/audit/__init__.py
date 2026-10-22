"""Auditoria de consultas, resultados e citações em audit.sqlite (BL-12; CTR-10).

- Toda consulta grava `query_event` e confirma a transação antes de buscar (inv. 1):
  uma busca que falha deixa o evento sem resultados, nunca resultado sem evento.
- `retrieval_result` guarda a ordem devolvida; `citation_record` guarda o trecho
  citado e os identificadores Git, nunca o arquivo inteiro (inv. 2).
- `reverify` reconfere citações auditadas relendo o blob no Git, sem abrir o
  índice: a auditoria sobrevive ao `rm index.sqlite` (TC-AUD-05).

O `index.sqlite` é só lido aqui; o rebuild nunca toca este banco (TC-AUD-02).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

from kos import __version__
from kos.cite import Citation, read_blob, verify
from kos.discovery import media_type_for
from kos.errors import KosError
from kos.parsing.profile import Locator, canonical_json
from kos.search import SearchResult, search
from kos.store import schema

INTERFACES = ("cli", "mcp", "bench")


@dataclass
class Reverification:
    citation_no: int
    repo_name: str
    path_text: str
    commit_oid: str
    recorded: str
    verification: str
    note: str | None

    def to_json(self) -> dict:
        return dict(self.__dict__)


def index_fingerprint(home: Path) -> str:
    """Hash de (versão de esquema, perfis, revisões consultáveis) do índice consultado.

    Depende do conteúdo, não da execução: um rebuild das mesmas revisões mantém o valor.
    """
    index = Path(home) / "index.sqlite"
    if not index.exists():
        return hashlib.sha256(b"no-index").hexdigest()
    conn = sqlite3.connect(f"file:{index}?mode=ro", uri=True)
    try:
        version = conn.execute("SELECT value FROM index_meta WHERE key = 'schema_version'").fetchone()
        profiles = [r[0] for r in conn.execute(
            "SELECT profile_fingerprint FROM processing_profile ORDER BY profile_fingerprint")]
        revisions = [list(r) for r in conn.execute(
            "SELECT r.name, s.commit_oid FROM ingest_run i"
            " JOIN source_revision s ON s.revision_id = i.target_revision_id"
            " JOIN repository r ON r.repo_id = s.repo_id"
            " WHERE i.run_id IN (SELECT max(run_id) FROM ingest_run"
            "   WHERE status IN ('succeeded', 'partial') GROUP BY repo_id)"
            " ORDER BY r.name")]
    finally:
        conn.close()
    payload = {"schema_version": version[0] if version else None, "profiles": profiles,
               "revisions": revisions}
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def _connect(home: Path) -> sqlite3.Connection:
    schema.initialize_audit(Path(home))
    conn = sqlite3.connect(Path(home) / "audit.sqlite", timeout=5)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def start_query(home: Path, *, interface: str, question: str, params: dict) -> str:
    """Grava o `query_event` e devolve o `query_id`; confirmado antes de qualquer resposta."""
    if interface not in INTERFACES:
        raise ValueError(f"interface desconhecida: {interface}")
    query_id = str(uuid.uuid4())
    asked_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")
    conn = _connect(home)
    try:
        with conn:
            conn.execute(
                "INSERT INTO query_event(query_id, asked_at, interface, question, params_json,"
                " index_fingerprint, tool_version) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (query_id, asked_at, interface, question, canonical_json(params),
                 index_fingerprint(home), __version__))
    finally:
        conn.close()
    return query_id


def record_retrieval(home: Path, query_id: str, result: SearchResult) -> None:
    conn = _connect(home)
    try:
        with conn:
            conn.executemany(
                "INSERT INTO retrieval_result(query_id, rank, fragment_key, score) VALUES (?, ?, ?, ?)",
                [(query_id, h.rank, h.fragment_key, h.score) for h in result.results])
    finally:
        conn.close()


def record_citations(home: Path, query_id: str, citations: list[Citation],
                     claim_ids: dict[int, list[str]] | None = None) -> None:
    """Grava as citações de uma resposta; `claim_ids` liga cada citação às afirmações que sustenta."""
    rows = []
    for c in citations:
        c.to_json()  # valida o esquema antes de gravar (TC-CIT-05, 06)
        rows.append((query_id, c.citation_no, json.dumps((claim_ids or {}).get(c.citation_no, [])),
                     c.repo_name, c.path_text, c.commit_oid, c.blob_oid,
                     canonical_json(c.locator.canonical()), c.quoted_text, c.quoted_sha256, c.verification))
    conn = _connect(home)
    try:
        with conn:
            conn.executemany(
                "INSERT INTO citation_record(query_id, citation_no, claim_ids, repo_name, path_text,"
                " commit_oid, blob_oid, locator_json, quoted_text, quoted_sha256, verification)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    finally:
        conn.close()


def record_answer(home: Path, query_id: str, *, outcome: str, mode: str, abstention_code: str | None = None,
                  answer_text: str | None = None) -> None:
    """Grava o `answer_record`; no modo extrativo não há adaptador de LLM a registrar."""
    conn = _connect(home)
    try:
        with conn:
            conn.execute(
                "INSERT INTO answer_record(query_id, outcome, mode, abstention_code, answer_text, llm_adapter_json)"
                " VALUES (?, ?, ?, ?, ?, NULL)", (query_id, outcome, mode, abstention_code, answer_text))
    finally:
        conn.close()


def audited_search(home: Path, query: str, *, interface: str = "cli", **filters) -> tuple[str, SearchResult]:
    """`search` com o evento gravado antes e os resultados gravados depois (TC-AUD-01)."""
    params = {"command": "search", **{k: v for k, v in filters.items() if v not in (None, False, [])}}
    query_id = start_query(home, interface=interface, question=query, params=params)
    result = search(home, query, **filters)
    record_retrieval(home, query_id, result)
    return query_id, result


def reverify(home: Path, query_id: str, repos: dict[str, Path]) -> list[Reverification]:
    """Reconfere as citações auditadas de uma consulta relendo os blobs, sem o índice."""
    conn = _connect(home)
    try:
        if conn.execute("SELECT 1 FROM query_event WHERE query_id = ?", (query_id,)).fetchone() is None:
            raise KosError("E_FILTER_INVALID", f"consulta {query_id} não está na auditoria")
        rows = conn.execute(
            "SELECT citation_no, repo_name, path_text, commit_oid, blob_oid, locator_json, quoted_sha256,"
            " verification FROM citation_record WHERE query_id = ? ORDER BY citation_no", (query_id,)).fetchall()
    finally:
        conn.close()
    out, blobs = [], {}
    for no, repo, path, commit, blob_oid, loc_json, sha, recorded in rows:
        if (repo, blob_oid) not in blobs:
            blobs[repo, blob_oid] = read_blob(repos.get(repo), blob_oid)
        state, note = verify(blobs[repo, blob_oid], Locator(**json.loads(loc_json)), sha, media_type_for(path))
        out.append(Reverification(no, repo, path, commit, recorded, state, note))
    return out
