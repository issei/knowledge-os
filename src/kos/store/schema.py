"""Criação dos bancos do Knowledge OS (BL-01).

Dois arquivos, conforme docs/fase-0/02-modelo-de-dados.md §2:

- index.sqlite: tudo que é derivado do Git; pode ser apagado e reconstruído.
- audit.sqlite: consultas, respostas e citações; nunca tocado pelo rebuild.

A criação é atômica por arquivo: o banco é montado num arquivo temporário e só
então movido para o nome final, para que uma falha no meio não deixe um banco
pela metade. Rodar `initialize` de novo sobre bancos da mesma versão não altera
nada (idempotência).
"""

from __future__ import annotations

import datetime
import os
import sqlite3
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from kos import __version__
from kos.errors import KosError

SCHEMA_VERSION = "1"

# (nome do arquivo, DDL empacotada, tabela de metadados)
DATABASES = (
    ("index.sqlite", "index.sql", "index_meta"),
    ("audit.sqlite", "audit.sql", "audit_meta"),
)


@dataclass(frozen=True)
class DatabaseStatus:
    name: str
    path: Path
    status: str  # "created" | "existing"


def load_ddl(filename: str) -> str:
    return resources.files("kos.store").joinpath(filename).read_text(encoding="utf-8")


def require_fts5() -> None:
    """Falha com E_FTS5_UNAVAILABLE se o SQLite desta instalação não tiver FTS5 (Q-06)."""
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE probe USING fts5(x)")
    except sqlite3.OperationalError as exc:
        raise KosError(
            "E_FTS5_UNAVAILABLE",
            f"o SQLite {sqlite3.sqlite_version} desta instalação não tem FTS5: {exc}",
        ) from exc
    finally:
        conn.close()


def initialize(home: Path) -> list[DatabaseStatus]:
    """Cria (ou reconhece) index.sqlite e audit.sqlite em `home`."""
    require_fts5()
    _ensure_writable_dir(home)
    return [_initialize_one(home, *db) for db in DATABASES]


def initialize_audit(home: Path) -> DatabaseStatus:
    """Cria (ou reconhece) só o audit.sqlite: consultar não pode criar um índice vazio."""
    _ensure_writable_dir(home)
    return _initialize_one(home, *DATABASES[1])


def _ensure_writable_dir(home: Path) -> None:
    try:
        home.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise KosError("E_STORE_UNWRITABLE", f"não foi possível criar {home}: {exc}") from exc
    if not home.is_dir() or not os.access(home, os.W_OK):
        raise KosError("E_STORE_UNWRITABLE", f"{home} não é um diretório com permissão de escrita")


def _initialize_one(home: Path, filename: str, ddl_name: str, meta_table: str) -> DatabaseStatus:
    path = home / filename
    if path.exists():
        found = _read_schema_version(path, meta_table)
        if found != SCHEMA_VERSION:
            raise KosError(
                "E_SCHEMA_MISMATCH",
                f"{path} tem esquema {found!r}; esta versão usa {SCHEMA_VERSION!r}. "
                "Para o índice, apague o arquivo e reconstrua (ADR-kos-001); "
                "a auditoria nunca é apagada automaticamente.",
            )
        return DatabaseStatus(filename, path, "existing")

    tmp = home / f".{filename}.tmp-{os.getpid()}"
    _remove_sqlite_files(tmp)
    try:
        conn = sqlite3.connect(tmp)
        try:
            conn.executescript(load_ddl(ddl_name))
            now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
            conn.executemany(
                f"INSERT INTO {meta_table}(key, value) VALUES (?, ?)",
                [
                    ("schema_version", SCHEMA_VERSION),
                    ("created_by_tool_version", __version__),
                    ("created_at", now),
                ],
            )
            conn.commit()
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(f"foreign_key_check falhou em {filename}: {violations}")
            # Volta ao modo de journal padrão antes de mover o arquivo, para não
            # deixar -wal/-shm órfãos com o nome temporário.
            conn.execute("PRAGMA journal_mode = DELETE")
        finally:
            conn.close()
        os.replace(tmp, path)
    except OSError as exc:
        raise KosError("E_STORE_UNWRITABLE", f"falha ao gravar {path}: {exc}") from exc
    finally:
        _remove_sqlite_files(tmp)
    _enable_wal(path)
    return DatabaseStatus(filename, path, "created")


def _enable_wal(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    finally:
        conn.close()


def _read_schema_version(path: Path, meta_table: str) -> str | None:
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                f"SELECT value FROM {meta_table} WHERE key = 'schema_version'"
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return None
    return row[0] if row else None


def _remove_sqlite_files(path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        try:
            os.remove(f"{path}{suffix}")
        except FileNotFoundError:
            pass
