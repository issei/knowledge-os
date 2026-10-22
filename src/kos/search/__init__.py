"""Recuperação de evidências por FTS5, presa a uma revisão (BL-10; CTR-06, ADR-kos-002).

- Revisão: a pedida (`commit`) ou, por repositório, a alvo da última ingestão
  `succeeded`/`partial`. Só entram versões elegíveis do manifesto dessa revisão
  (inv. 1), processadas pelos perfis ativos desta instalação.
- Consulta: cada palavra vira um termo FTS5 entre aspas, ligados por `OR`; a
  sintaxe do FTS5 digitada pelo usuário (`NEAR`, `*`, `:`, aspas) nunca vira
  operador (inv. 3). Palavras compostas (`genPortfolio`, `pf_block`) também
  entram divididas, para casar com `ident_terms`.
- Ordem: `bm25()` com os pesos de `COLUMN_WEIGHTS`; empate por `fragment_key` (inv. 2).
- Gerados (`is_generated`) ficam fora por padrão; com `include_generated`, vêm marcados (inv. 6).
"""

from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from kos.discovery.glob import compile_pattern, matches
from kos.discovery.policy import ARTIFACT_KINDS
from kos.errors import KosError
from kos.parsing import registry
from kos.parsing.profile import Locator

# Pesos de bm25 por coluna do FTS (text, heading_path, ident_terms). Valores iniciais
# declarados, sem calibração: o benchmark (BL-14) é quem diz se mudam.
COLUMN_WEIGHTS = (1.0, 2.0, 1.0)
MAX_K = 200
_WORD = re.compile(r"\w+", re.UNICODE)
_PART = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


@dataclass
class Hit:
    rank: int
    fragment_key: str
    score: float
    repo: str
    commit_oid: str
    path_text: str
    artifact_kind: str
    is_generated: bool
    heading_path: str | None
    locator: Locator
    snippet: str
    text_sha256: str

    def to_json(self) -> dict:
        data = asdict(self)
        data["locator"] = self.locator.canonical()
        return data


@dataclass
class SearchResult:
    revisions: list[dict]
    results: list[Hit]
    diagnostics: dict = field(default_factory=dict)


def fts_query(text: str) -> str:
    """Texto livre → expressão FTS5 segura: termos entre aspas ligados por OR."""
    terms: list[str] = []
    for word in _WORD.findall(text):
        candidates = [word.lower()]
        parts = [p.lower() for chunk in word.split("_") for p in _PART.findall(chunk)] if word.isascii() else []
        if len(parts) > 1:
            candidates += parts
        for term in candidates:
            if term not in terms:
                terms.append(term)
    return " OR ".join('"' + t.replace('"', '""') + '"' for t in terms)


def search(home: Path, query: str, *, repo: str | None = None, commit: str | None = None, k: int = 10,
           path_glob: str | None = None, kinds: list[str] | None = None,
           include_generated: bool = False, weights: tuple[float, float, float] = COLUMN_WEIGHTS) -> SearchResult:
    started = time.perf_counter()
    expression = fts_query(query)
    if not expression:
        raise KosError("E_QUERY_EMPTY", "a consulta não tem nenhuma palavra pesquisável")
    _validate_filters(k, path_glob, kinds, commit, repo)
    index = Path(home) / "index.sqlite"
    if not index.exists():
        raise KosError("E_NO_INDEXED_REVISION", f"{index} não existe; rode `kos ingest` antes")
    conn = sqlite3.connect(f"file:{index}?mode=ro", uri=True)
    try:
        conn.create_function("kos_glob", 2, lambda path, pat: matches(path, pat), deterministic=True)
        revisions = _revisions(conn, repo, commit)
        fingerprints = sorted({registry.profile_for(m).fingerprint for m in _media_types(conn, revisions)
                               if registry.profile_for(m) is not None})
        hits, total = _query(conn, expression, revisions, fingerprints, k, path_glob, kinds, include_generated,
                             weights)
        stale = _stale_versions(conn, revisions, fingerprints)
    finally:
        conn.close()
    return SearchResult(
        revisions=[{"repo": r, "commit_oid": c} for _, r, c in revisions],
        results=hits,
        diagnostics={"parsed_query": expression, "total_hits": total, "column_weights": list(weights),
                     "stale_versions": stale,
                     "latency_ms": round((time.perf_counter() - started) * 1000, 1)},
    )


def _validate_filters(k, path_glob, kinds, commit, repo) -> None:
    if not 1 <= k <= MAX_K:
        raise KosError("E_FILTER_INVALID", f"k precisa estar entre 1 e {MAX_K}")
    if path_glob is not None:
        try:
            compile_pattern(path_glob)
        except ValueError as exc:
            raise KosError("E_FILTER_INVALID", str(exc)) from exc
    bad = sorted(set(kinds or ()) - set(ARTIFACT_KINDS))
    if bad:
        raise KosError("E_FILTER_INVALID", f"tipo de artefato desconhecido: {', '.join(bad)}")
    if commit is not None and not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
        raise KosError("E_FILTER_INVALID", "o commit precisa ser o OID completo em hexadecimal")


def _revisions(conn, repo, commit) -> list[tuple[int, str, str]]:
    """(revision_id, repo, commit) consultáveis."""
    consultable = ("SELECT s.revision_id, r.name, s.commit_oid, max(i.run_id) AS last_run"
                   " FROM source_revision s JOIN repository r USING (repo_id)"
                   " JOIN ingest_run i ON i.target_revision_id = s.revision_id"
                   " WHERE i.status IN ('succeeded', 'partial')")
    if commit is not None:
        rows = conn.execute(consultable + " AND s.commit_oid = ? AND (? IS NULL OR r.name = ?)"
                            " GROUP BY s.revision_id ORDER BY r.name", (commit, repo, repo)).fetchall()
        if not rows:
            raise KosError("E_REVISION_NOT_INDEXED", f"a revisão {commit} não tem ingestão concluída")
    else:
        rows = conn.execute(
            "SELECT revision_id, name, commit_oid, last_run FROM (" + consultable +
            " AND (? IS NULL OR r.name = ?) GROUP BY s.revision_id)"
            " WHERE last_run IN (SELECT max(i.run_id) FROM ingest_run i JOIN source_revision s"
            "   ON s.revision_id = i.target_revision_id WHERE i.status IN ('succeeded', 'partial')"
            "   GROUP BY s.repo_id) ORDER BY name", (repo, repo)).fetchall()
        if not rows:
            raise KosError("E_NO_INDEXED_REVISION", "nenhuma revisão consultável"
                           + (f" para {repo!r}" if repo else ""))
    return [(rid, name, oid) for rid, name, oid, _ in rows]


def _media_types(conn, revisions) -> set[str]:
    ids = [r[0] for r in revisions]
    sql = ("SELECT DISTINCT v.media_type FROM revision_manifest m JOIN artifact_version v USING (version_id)"
           f" WHERE m.eligibility = 'eligible' AND m.revision_id IN ({','.join('?' * len(ids))})")
    return {row[0] for row in conn.execute(sql, ids)}


def _query(conn, expression, revisions, fingerprints, k, path_glob, kinds, include_generated, weights):
    rev_ids = [r[0] for r in revisions]
    where = [f"m.revision_id IN ({','.join('?' * len(rev_ids))})",
             f"p.profile_fingerprint IN ({','.join('?' * len(fingerprints))})"]
    params: list = [expression, *rev_ids, *fingerprints]
    if not include_generated:
        where.append("v.is_generated = 0")
    if path_glob:
        where.append("kos_glob(a.path_text, ?)")
        params.append(path_glob)
    if kinds:
        where.append(f"a.artifact_kind IN ({','.join('?' * len(kinds))})")
        params += list(kinds)
    w = ", ".join(str(float(x)) for x in weights)
    base = (
        " FROM fragment_fts x JOIN fragment f ON f.fragment_id = x.rowid"
        " JOIN processing_profile p ON p.profile_id = f.profile_id"
        " JOIN revision_manifest m ON m.version_id = f.version_id AND m.eligibility = 'eligible'"
        " JOIN artifact a ON a.artifact_id = m.artifact_id"
        " JOIN artifact_version v ON v.version_id = f.version_id"
        " JOIN source_revision s ON s.revision_id = m.revision_id"
        " JOIN repository r ON r.repo_id = s.repo_id"
        " JOIN fragment_locator l ON l.fragment_id = f.fragment_id"
        " WHERE fragment_fts MATCH ? AND " + " AND ".join(where))
    try:
        total = conn.execute("SELECT count(*)" + base, params).fetchone()[0]
        rows = conn.execute(
            f"SELECT f.fragment_key, -bm25(fragment_fts, {w}) AS score, r.name, s.commit_oid, a.path_text,"
            " a.artifact_kind, v.is_generated, f.heading_path, f.text_sha256,"
            " snippet(fragment_fts, 0, '[', ']', '…', 16),"
            " l.locator_type, l.start_byte, l.end_byte, l.start_line, l.end_line, l.start_col, l.end_col,"
            " l.struct_path, l.page_start, l.page_end"
            + base + " ORDER BY score DESC, f.fragment_key LIMIT ?", [*params, k]).fetchall()
    except sqlite3.OperationalError as exc:  # não deveria acontecer com a expressão escapada
        raise KosError("E_FILTER_INVALID", f"consulta rejeitada pelo FTS5: {exc}") from exc
    hits = []
    for rank, row in enumerate(rows, start=1):
        (key, score, repo, commit, path, kind, generated, heading, sha, snip, *loc) = row
        hits.append(Hit(rank, key, round(score, 6), repo, commit, path, kind, bool(generated), heading,
                        Locator(loc[0], start_byte=loc[1], end_byte=loc[2], start_line=loc[3], end_line=loc[4],
                                start_col=loc[5], end_col=loc[6], struct_path=loc[7], page_start=loc[8],
                                page_end=loc[9]),
                        snip, sha))
    return hits, total


def _stale_versions(conn, revisions, fingerprints) -> int:
    """Versões elegíveis sem processamento por nenhum perfil ativo: pedem nova ingestão."""
    rev_ids = [r[0] for r in revisions]
    sql = ("SELECT count(DISTINCT m.version_id) FROM revision_manifest m"
           f" WHERE m.eligibility = 'eligible' AND m.revision_id IN ({','.join('?' * len(rev_ids))})"
           " AND NOT EXISTS (SELECT 1 FROM version_processing vp JOIN processing_profile p USING (profile_id)"
           f"   WHERE vp.version_id = m.version_id AND p.profile_fingerprint IN ({','.join('?' * len(fingerprints))}))")
    return conn.execute(sql, [*rev_ids, *fingerprints]).fetchone()[0]
