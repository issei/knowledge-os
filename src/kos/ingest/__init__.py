"""Ingestão `full` de uma revisão (BL-08; CTR-03 modo full, CTR-10).

Fluxo: descoberta (CTR-01) → artefatos e versões → parsing por perfil
(CTR-02) → fragmentos, localizadores e FTS → manifesto completo da revisão →
`ingest_run` com status final.

Transações. A linha `ingest_run` nasce `running` numa transação curta; todo o
resto acontece numa única transação `BEGIN IMMEDIATE`, que também fecha a linha
com o status final. Assim:

- um processo morto no meio não deixa nada da revisão-alvo visível; a próxima
  execução encontra a linha `running` órfã e a marca `aborted` (CTR-03 inv. 5);
- outra ingestão no mesmo índice encontra o banco travado e falha com
  `E_LOCKED`, sem esperar.

Cache. O resultado de uma versão num perfil (`version_processing`) é reaproveitado
quando já existe com status diferente de `failed`: fragmentos são função pura de
(blob, perfil), então reprocessar daria o mesmo resultado (contagem `reused`).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import sqlite3
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from kos import __version__
from kos.discovery import DiscoveredFile, Policy, discover, read_blobs
from kos.errors import KosError
from kos.parsing import registry
from kos.parsing.profile import canonical_json, fragment_key, register_profile
from kos.parsing.types import ParseResult
from kos.store import schema

MAX_FRAGMENTS_PER_FILE = 10_000
BLOB_BATCH = 200
_IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_IDENT_PART = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
CODE_KINDS = frozenset({"code_block", "symbol", "test_case"})


@dataclass
class IngestResult:
    run_uuid: str
    repo_name: str
    commit_oid: str
    status: str
    counts: dict = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)


def ingest_full(home: Path, repo: Path, *, rev: str = "HEAD", policy: Policy | None = None,
                repo_name: str | None = None, mode: str = "full") -> IngestResult:
    """Indexa a árvore inteira de `rev`. `mode="rebuild"` é usado pelo `kos rebuild` (CTR-05)."""
    policy = policy or Policy.default()
    repo = Path(repo)
    commit, files = discover(repo, rev, policy)
    schema.initialize(home)
    conn = _connect(home / "index.sqlite")
    try:
        name = repo_name or repo.resolve().name
        run_id, run_uuid = _start_run(conn, repo, name, commit, policy, mode)
        return _run(conn, repo, name, commit, files, policy, run_id, run_uuid)
    finally:
        conn.close()


def split_identifiers(text: str) -> str | None:
    """Partes de identificadores compostos (camelCase, snake_case), para a coluna `ident_terms`."""
    parts: list[str] = []
    seen: set[str] = set()
    for ident in _IDENT.findall(text):
        pieces = [p.lower() for chunk in re.split(r"[_$]+", ident) for p in _IDENT_PART.findall(chunk)]
        if len(pieces) < 2:
            continue
        for piece in pieces:
            if piece not in seen:
                seen.add(piece)
                parts.append(piece)
    return " ".join(parts) or None


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, isolation_level=None, timeout=0)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _begin(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc) or "busy" in str(exc):
            raise KosError("E_LOCKED", "outra ingestão está gravando neste índice") from exc
        raise


def _start_run(conn, repo: Path, name: str, commit: str, policy: Policy, mode: str) -> tuple[int, str]:
    tree_oid, committed_at = _commit_info(repo, commit)
    object_format = _object_format(repo)
    _begin(conn)
    try:
        conn.execute("UPDATE ingest_run SET status = 'aborted', finished_at = ?"
                     " WHERE status = 'running'", (_now(),))
        conn.execute("INSERT OR IGNORE INTO repository(name, object_format, registered_at)"
                     " VALUES (?, ?, ?)", (name, object_format, _now()))
        repo_id = conn.execute("SELECT repo_id FROM repository WHERE name = ?", (name,)).fetchone()[0]
        # Onde o clone estava na última ingestão: só um palpite para reler blobs (kos cite),
        # nunca identidade.
        conn.execute("UPDATE repository SET origin_url = ? WHERE repo_id = ?", (repo.resolve().as_uri(), repo_id))
        conn.execute("INSERT OR IGNORE INTO source_revision(repo_id, commit_oid, tree_oid, committed_at)"
                     " VALUES (?, ?, ?, ?)", (repo_id, commit, tree_oid, committed_at))
        revision_id = conn.execute("SELECT revision_id FROM source_revision WHERE repo_id = ?"
                                   " AND commit_oid = ?", (repo_id, commit)).fetchone()[0]
        run_uuid = str(uuid.uuid4())
        cur = conn.execute(
            "INSERT INTO ingest_run(run_uuid, repo_id, mode, target_revision_id, policy_sha256,"
            " tool_version, started_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'running')",
            (run_uuid, repo_id, mode, revision_id, policy.sha256, __version__, _now()))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return cur.lastrowid, run_uuid


def _run(conn, repo, name, commit, files, policy, run_id, run_uuid) -> IngestResult:
    _begin(conn)
    try:
        repo_id, revision_id = conn.execute(
            "SELECT r.repo_id, s.revision_id FROM ingest_run i JOIN repository r USING (repo_id)"
            " JOIN source_revision s ON s.revision_id = i.target_revision_id WHERE i.run_id = ?",
            (run_id,)).fetchone()
        counts = {"discovered": len(files), "eligible": 0, "reused": 0, "processed": 0,
                  "failed": 0, "warnings": 0, "fragments": 0}
        errors: list[dict] = []
        conn.execute("DELETE FROM revision_manifest WHERE revision_id = ?", (revision_id,))
        readable = sorted({f.blob_oid for f in files if f.file_mode != "160000"})
        for start in range(0, len(readable), BLOB_BATCH):
            batch = readable[start:start + BLOB_BATCH]
            blobs = read_blobs(repo, batch)
            for f in files:
                if f.blob_oid in blobs and f.file_mode != "160000":
                    _ingest_file(conn, run_id, repo_id, name, revision_id, f, blobs[f.blob_oid], counts, errors)
        for f in files:
            if f.file_mode == "160000":
                _ingest_file(conn, run_id, repo_id, name, revision_id, f, None, counts, errors)
        status = "partial" if counts["failed"] else "succeeded"
        conn.execute("UPDATE ingest_run SET status = ?, finished_at = ?, counts_json = ? WHERE run_id = ?",
                     (status, _now(), canonical_json(counts), run_id))
        conn.execute("INSERT INTO index_meta(key, value) VALUES ('eligibility_policy_sha256', ?)"
                     " ON CONFLICT(key) DO UPDATE SET value = excluded.value", (policy.sha256,))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return IngestResult(run_uuid, name, commit, status, counts, errors)


def _ingest_file(conn, run_id, repo_id, repo_name, revision_id, f: DiscoveredFile, blob: bytes | None,
                 counts: dict, errors: list[dict]) -> None:
    if _already_in_manifest(conn, revision_id, repo_id, f):
        return  # mesmo blob em mais de um lote: o manifesto já tem este caminho
    conn.execute("INSERT OR IGNORE INTO artifact(repo_id, path_bytes, path_text, path_is_utf8,"
                 " artifact_kind, kind_rule) VALUES (?, ?, ?, ?, ?, ?)",
                 (repo_id, f.path_bytes, f.path_text, int(f.path_is_utf8), f.artifact_kind, f.kind_rule))
    artifact_id = conn.execute("SELECT artifact_id FROM artifact WHERE repo_id = ? AND path_bytes = ?",
                               (repo_id, f.path_bytes)).fetchone()[0]
    version_id = _version(conn, artifact_id, f, blob)
    conn.execute("INSERT INTO revision_manifest(revision_id, artifact_id, version_id, file_mode,"
                 " eligibility, exclusion_rule) VALUES (?, ?, ?, ?, ?, ?)",
                 (revision_id, artifact_id, version_id, f.file_mode, f.eligibility, f.exclusion_rule))
    if f.eligibility != "eligible":
        return
    counts["eligible"] += 1
    profile = registry.profile_for(f.media_type)
    if profile is None:
        _, result = registry.parse(blob, f.media_type)
        _record(conn, run_id, version_id, None, f, result, counts, errors, repo_name)
        return
    profile_id = register_profile(conn, profile)
    cached = conn.execute("SELECT status FROM version_processing WHERE version_id = ? AND profile_id = ?",
                          (version_id, profile_id)).fetchone()
    if cached and cached[0] != "failed":
        conn.execute("UPDATE version_processing SET last_run_id = ? WHERE version_id = ? AND profile_id = ?",
                     (run_id, version_id, profile_id))
        counts["reused"] += 1
        return
    if cached:
        conn.execute("DELETE FROM version_processing WHERE version_id = ? AND profile_id = ?",
                     (version_id, profile_id))
    try:
        _, result = registry.parse(blob, f.media_type)
    except Exception as exc:  # noqa: BLE001 — erro de um arquivo não interrompe os demais (CTR-02 inv. 7)
        result = ParseResult(status="failed", reason_code="E_PARSE_SYNTAX",
                             warnings=(f"{type(exc).__name__}: {exc}"[:200],))
    if len(result.fragments) > MAX_FRAGMENTS_PER_FILE:
        result = ParseResult(status="failed", reason_code="E_TOO_MANY_FRAGMENTS",
                             warnings=(f"{len(result.fragments)} fragmentos; limite {MAX_FRAGMENTS_PER_FILE}",))
    _record(conn, run_id, version_id, profile_id, f, result, counts, errors, repo_name, profile)


def _record(conn, run_id, version_id, profile_id, f, result: ParseResult, counts, errors, repo_name,
            profile=None):
    artifact_id = conn.execute("SELECT artifact_id FROM artifact_version WHERE version_id = ?",
                               (version_id,)).fetchone()[0]
    if result.status != "parsed":
        severity = "error" if result.status == "failed" else "warning"
        counts["failed" if severity == "error" else "warnings"] += 1
        code = result.reason_code or "E_PARSE_SYNTAX"
        stage = "decode" if code == "E_DECODE" else "parse"
        _error(conn, run_id, artifact_id, version_id, f, stage, code, severity,
               "; ".join(result.warnings) or code, errors)
    if profile_id is None:
        return
    fragments = result.fragments if result.status in ("parsed", "parsed_with_warnings") else ()
    conn.execute("INSERT INTO version_processing(version_id, profile_id, status, reason_code,"
                 " first_run_id, last_run_id, fragment_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (version_id, profile_id, result.status, result.reason_code, run_id, run_id, len(fragments)))
    if result.status != "failed":
        counts["processed"] += 1
    for frag in fragments:
        ident = frag.ident_terms or (split_identifiers(frag.text) if frag.fragment_kind in CODE_KINDS else None)
        loc = frag.locator
        cur = conn.execute(
            "INSERT INTO fragment(fragment_key, version_id, profile_id, ordinal, fragment_kind,"
            " heading_path, text, ident_terms, text_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (fragment_key(repo_name, f.path_bytes, f.blob_oid, profile.fingerprint, loc), version_id, profile_id, frag.ordinal,
             frag.fragment_kind, frag.heading_path, frag.text, ident, frag.text_sha256))
        fragment_id = cur.lastrowid
        conn.execute(
            "INSERT INTO fragment_locator(fragment_id, locator_type, start_byte, end_byte, start_line,"
            " end_line, start_col, end_col, struct_path, page_start, page_end)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (fragment_id, loc.type, loc.start_byte, loc.end_byte, loc.start_line, loc.end_line,
             loc.start_col, loc.end_col, loc.struct_path, loc.page_start, loc.page_end))
        conn.execute("INSERT INTO fragment_fts(rowid, text, heading_path, ident_terms) VALUES (?, ?, ?, ?)",
                     (fragment_id, frag.text, frag.heading_path, ident))
    counts["fragments"] += len(fragments)


def _error(conn, run_id, artifact_id, version_id, f, stage, code, severity, message, errors):
    conn.execute("INSERT INTO processing_error(run_id, stage, artifact_id, version_id, path_text,"
                 " error_code, severity, message, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (run_id, stage, artifact_id, version_id, f.path_text, code, severity, message[:200], _now()))
    errors.append({"path": f.path_text, "stage": stage, "code": code, "severity": severity,
                   "message": message[:200]})


def _already_in_manifest(conn, revision_id, repo_id, f) -> bool:
    return conn.execute(
        "SELECT 1 FROM revision_manifest m JOIN artifact a USING (artifact_id)"
        " WHERE m.revision_id = ? AND a.repo_id = ? AND a.path_bytes = ?",
        (revision_id, repo_id, f.path_bytes)).fetchone() is not None


def _version(conn, artifact_id: int, f: DiscoveredFile, blob: bytes | None) -> int:
    if blob is None:  # submódulo: o objeto é um commit de outro repositório, sem conteúdo aqui
        sha, size, encoding, ending = f"gitlink:{f.blob_oid}", 0, None, None
    else:
        sha, size = hashlib.sha256(blob).hexdigest(), len(blob)
        encoding, ending = _text_info(blob)
    conn.execute("INSERT OR IGNORE INTO artifact_version(artifact_id, blob_oid, content_sha256, byte_size,"
                 " media_type, text_encoding, line_ending, is_generated) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (artifact_id, f.blob_oid, sha, size, f.media_type, encoding, ending, int(f.is_generated)))
    return conn.execute("SELECT version_id FROM artifact_version WHERE artifact_id = ? AND blob_oid = ?",
                        (artifact_id, f.blob_oid)).fetchone()[0]


def _text_info(blob: bytes) -> tuple[str | None, str | None]:
    try:
        blob.decode("utf-8")
    except UnicodeDecodeError:
        return None, None
    crlf = blob.count(b"\r\n")
    lf = blob.count(b"\n") - crlf
    if not crlf and not lf:
        return "utf-8", "none"
    return "utf-8", "crlf" if crlf and not lf else "lf" if lf and not crlf else "mixed"


def _commit_info(repo: Path, commit: str) -> tuple[str, str]:
    out = subprocess.run(["git", "-C", str(repo), "show", "-s", "--format=%T %ct", commit],
                         capture_output=True, check=True, text=True).stdout.split()
    when = datetime.datetime.fromtimestamp(int(out[1]), datetime.timezone.utc)
    return out[0], when.isoformat(timespec="seconds")


def _object_format(repo: Path) -> str:
    proc = subprocess.run(["git", "-C", str(repo), "rev-parse", "--show-object-format"],
                          capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else "sha1"
