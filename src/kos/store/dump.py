"""Dump lógico de `index.sqlite`, sem IDs inteiros nem carimbos de tempo (CTR-05 inv. 2, TC-REB-02).

Cada tabela vira uma lista ordenada de tuplas cujas referências são trocadas
por identidades estáveis (nome do repositório, commit, caminho em bytes, blob,
impressão digital do perfil, `fragment_key`). Dois índices construídos das mesmas
entradas têm o mesmo dump e, portanto, o mesmo `digest`.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

QUERIES = {
    "repository": "SELECT name, object_format FROM repository",
    "source_revision": """
        SELECT r.name, s.commit_oid, s.tree_oid, s.committed_at, s.retained
        FROM source_revision s JOIN repository r USING (repo_id)""",
    "artifact": """
        SELECT r.name, hex(a.path_bytes), a.path_text, a.path_is_utf8, a.artifact_kind, a.kind_rule
        FROM artifact a JOIN repository r USING (repo_id)""",
    "artifact_version": """
        SELECT r.name, hex(a.path_bytes), v.blob_oid, v.content_sha256, v.byte_size, v.media_type,
               v.text_encoding, v.line_ending, v.is_generated
        FROM artifact_version v JOIN artifact a USING (artifact_id) JOIN repository r USING (repo_id)""",
    "revision_manifest": """
        SELECT r.name, s.commit_oid, hex(a.path_bytes), v.blob_oid, m.file_mode, m.eligibility,
               m.exclusion_rule
        FROM revision_manifest m JOIN source_revision s USING (revision_id)
        JOIN artifact a ON a.artifact_id = m.artifact_id JOIN artifact_version v ON v.version_id = m.version_id
        JOIN repository r ON r.repo_id = s.repo_id""",
    "processing_profile": """
        SELECT profile_name, parser_name, parser_version, grammar_version, normalizer_version,
               config_json, profile_fingerprint FROM processing_profile""",
    "version_processing": """
        SELECT r.name, hex(a.path_bytes), v.blob_oid, p.profile_fingerprint, vp.status, vp.reason_code,
               vp.fragment_count
        FROM version_processing vp JOIN artifact_version v USING (version_id)
        JOIN artifact a USING (artifact_id) JOIN repository r USING (repo_id)
        JOIN processing_profile p ON p.profile_id = vp.profile_id""",
    "fragment": """
        SELECT f.fragment_key, r.name, hex(a.path_bytes), v.blob_oid, p.profile_fingerprint, f.ordinal,
               f.fragment_kind, f.heading_path, f.text, f.ident_terms, f.text_sha256,
               l.locator_type, l.start_byte, l.end_byte, l.start_line, l.end_line, l.start_col, l.end_col,
               l.struct_path, l.page_start, l.page_end
        FROM fragment f JOIN fragment_locator l USING (fragment_id)
        JOIN artifact_version v USING (version_id) JOIN artifact a USING (artifact_id)
        JOIN repository r USING (repo_id) JOIN processing_profile p ON p.profile_id = f.profile_id""",
    # O FTS é de conteúdo externo; conferimos o que ele devolve para cada fragmento.
    "fragment_fts": """
        SELECT f.fragment_key, x.text, x.heading_path, x.ident_terms
        FROM fragment_fts x JOIN fragment f ON f.fragment_id = x.rowid""",
    "processing_error": """
        SELECT e.path_text, e.stage, e.error_code, e.severity, e.message, v.blob_oid
        FROM processing_error e LEFT JOIN artifact_version v USING (version_id)""",
}


def logical_dump(conn: sqlite3.Connection) -> dict[str, list[tuple]]:
    return {name: sorted(conn.execute(sql).fetchall(), key=_sort_key) for name, sql in QUERIES.items()}


def digest(dump: dict[str, list[tuple]]) -> str:
    h = hashlib.sha256()
    for name in sorted(dump):
        h.update(name.encode() + b"\n")
        for row in dump[name]:
            h.update(json.dumps(row, ensure_ascii=False).encode() + b"\n")
    return h.hexdigest()


def _sort_key(row: tuple) -> str:
    return json.dumps(row, ensure_ascii=False)
