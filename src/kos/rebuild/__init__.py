"""Reconstrução integral de `index.sqlite` (BL-09; CTR-05, ADR-kos-001).

O índice novo é montado num diretório temporário dentro de `home`, a partir só
do Git e das entradas declaradas: (repositório, commits) e política. Só depois
de pronto ele substitui o antigo, com `os.replace`. Se qualquer passo falhar
antes da troca, o índice antigo continua intacto (inv. 4). `audit.sqlite` não é
aberto (inv. 3).

As revisões vêm de `--rev` ou, na falta, do próprio índice antigo: as revisões
retidas com alguma ingestão `succeeded` ou `partial`. Commit que sumiu do Git
(ex.: após force-push) não interrompe o resto: entra no relatório e deixa o
resultado `partial` (TC-REB-03).
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from kos.discovery import Policy
from kos.errors import KosError
from kos.ingest import ingest_full
from kos.store import schema
from kos.store.dump import digest, logical_dump


@dataclass
class RebuildResult:
    status: str  # succeeded | partial
    revisions: list[dict] = field(default_factory=list)
    missing: list[dict] = field(default_factory=list)
    old_digest: str | None = None
    new_digest: str | None = None
    fragments_added: dict = field(default_factory=dict)  # por perfil
    fragments_removed: dict = field(default_factory=dict)


def retained_revisions(index_path: Path) -> list[tuple[str, str]]:
    """(repositório, commit) retidos no índice existente, em ordem estável."""
    if not index_path.exists():
        return []
    conn = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
    try:
        return conn.execute(
            "SELECT DISTINCT r.name, s.commit_oid FROM source_revision s JOIN repository r USING (repo_id)"
            " JOIN ingest_run i ON i.target_revision_id = s.revision_id"
            " WHERE s.retained = 1 AND i.status IN ('succeeded', 'partial')"
            " ORDER BY r.name, s.committed_at, s.commit_oid").fetchall()
    finally:
        conn.close()


def rebuild(home: Path, repos: dict[str, Path], *, policy: Policy,
            revisions: list[tuple[str, str]] | None = None) -> RebuildResult:
    home = Path(home)
    index_path = home / "index.sqlite"
    targets = revisions if revisions is not None else retained_revisions(index_path)
    if not targets:
        raise KosError("E_NO_INDEXED_REVISION",
                       "nenhuma revisão para reconstruir: o índice não tem revisões retidas e nenhum --rev foi dado")
    schema.require_fts5()
    home.mkdir(parents=True, exist_ok=True)
    work = home / f".rebuild-{os.getpid()}"
    shutil.rmtree(work, ignore_errors=True)
    result = RebuildResult(status="succeeded")
    try:
        for name, commit in targets:
            if name not in repos:
                result.missing.append({"repo": name, "commit_oid": commit, "code": "E_REPO_NOT_FOUND",
                                       "message": f"caminho do repositório {name!r} não informado"})
                continue
            try:
                run = ingest_full(work, repos[name], rev=commit, policy=policy, repo_name=name, mode="rebuild")
            except KosError as err:
                if err.code not in ("E_COMMIT_NOT_FOUND", "E_REPO_NOT_FOUND"):
                    raise
                result.missing.append({"repo": name, "commit_oid": commit, "code": err.code,
                                       "message": err.message})
                continue
            result.revisions.append({"repo": name, "commit_oid": run.commit_oid, "status": run.status,
                                     "counts": run.counts})
        if not result.revisions:
            raise KosError("E_COMMIT_NOT_FOUND", "nenhuma das revisões pôde ser reconstruída")
        _compare(index_path, work / "index.sqlite", result)
        _swap(work / "index.sqlite", index_path)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if result.missing or any(r["status"] == "partial" for r in result.revisions):
        result.status = "partial"
    return result


def _compare(old_path: Path, new_path: Path, result: RebuildResult) -> None:
    new = _open_dump(new_path)
    try:
        old = _open_dump(old_path) if old_path.exists() else None
    except sqlite3.DatabaseError:
        old = None  # índice de outro esquema (Q-07: mudança de esquema = rebuild) ou corrompido
    result.new_digest = digest(new)
    if old is None:
        return
    result.old_digest = digest(old)
    old_keys = {row[0]: row[4] for row in old["fragment"]}  # fragment_key → impressão digital do perfil
    new_keys = {row[0]: row[4] for row in new["fragment"]}
    result.fragments_added = dict(Counter(new_keys[k] for k in new_keys.keys() - old_keys.keys()))
    result.fragments_removed = dict(Counter(old_keys[k] for k in old_keys.keys() - new_keys.keys()))


def _open_dump(path: Path) -> dict:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return logical_dump(conn)
    finally:
        conn.close()


def _swap(new_path: Path, index_path: Path) -> None:
    """Troca atômica. Os dois bancos saem do modo WAL antes, para não sobrar -wal do antigo."""
    _leave_wal(new_path)
    if index_path.exists():
        try:
            _leave_wal(index_path)
        except sqlite3.DatabaseError:
            pass  # não é um banco deste esquema; será substituído do mesmo jeito
        for suffix in ("-wal", "-shm"):
            Path(f"{index_path}{suffix}").unlink(missing_ok=True)
    os.replace(new_path, index_path)
    conn = sqlite3.connect(index_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    finally:
        conn.close()


def _leave_wal(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode = DELETE")
    finally:
        conn.close()
