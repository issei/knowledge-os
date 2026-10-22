"""Descoberta de arquivos elegíveis numa revisão Git (CTR-01, BL-03).

Lê só os objetos do commit (`git ls-tree` e `git cat-file`): a cópia de
trabalho, o índice do Git e arquivos não rastreados nunca entram. Todo arquivo
da árvore aparece no resultado, elegível ou excluído com a regra que o excluiu.
"""

from __future__ import annotations

import codecs
import posixpath
import subprocess
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

from kos.discovery.glob import matches
from kos.discovery.policy import Policy
from kos.errors import KosError

__all__ = ["DiscoveredFile", "Policy", "discover", "media_type_for", "read_blobs", "resolve_commit"]

LFS_PREFIX = b"version https://git-lfs.github.com/spec/v1"
BINARY_SNIFF_BYTES = 8000

# Tipo de mídia por extensão; o conteúdo (bytes nulos) decide se é binário.
MEDIA_TYPES = {
    ".md": "text/markdown", ".markdown": "text/markdown",
    ".yaml": "application/yaml", ".yml": "application/yaml",
    ".json": "application/json", ".html": "text/html", ".htm": "text/html",
    ".js": "text/javascript", ".mjs": "text/javascript", ".cjs": "text/javascript",
    ".py": "text/x-python", ".sh": "text/x-shellscript", ".css": "text/css",
    ".txt": "text/plain", ".csv": "text/csv", ".xml": "application/xml",
    ".toml": "application/toml", ".sql": "application/sql",
}


@dataclass(frozen=True)
class DiscoveredFile:
    path_bytes: bytes
    path_text: str
    path_is_utf8: bool
    blob_oid: str
    file_mode: str
    byte_size: int | None
    media_type: str
    eligibility: str  # "eligible" | "excluded"
    exclusion_rule: str | None
    artifact_kind: str
    kind_rule: str
    is_generated: bool

    def to_json(self) -> dict:
        data = asdict(self)
        data["path_bytes"] = self.path_bytes.hex()
        return data


def _git(repo: Path, *args: str, input: bytes | None = None) -> bytes:
    try:
        proc = subprocess.run(["git", "-C", str(repo), *args], input=input,
                              capture_output=True, check=False)
    except FileNotFoundError as exc:
        raise KosError("E_GIT_UNAVAILABLE", "o executável git não foi encontrado") from exc
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, args, proc.stdout, proc.stderr)
    return proc.stdout


def resolve_commit(repo: Path, rev: str) -> str:
    """Resolve `rev` para o OID completo de um commit."""
    if not Path(repo).is_dir():
        raise KosError("E_REPO_NOT_FOUND", f"{repo} não existe")
    try:
        _git(repo, "rev-parse", "--git-dir")
    except subprocess.CalledProcessError as exc:
        raise KosError("E_REPO_NOT_FOUND", f"{repo} não é um repositório Git") from exc
    try:
        return _git(repo, "rev-parse", "--verify", "--quiet", "--end-of-options",
                    f"{rev}^{{commit}}").decode().strip()
    except subprocess.CalledProcessError as exc:
        raise KosError("E_COMMIT_NOT_FOUND", f"revisão {rev!r} não encontrada em {repo}") from exc


def _decode_path(raw: bytes) -> tuple[str, bool]:
    try:
        return unicodedata.normalize("NFC", raw.decode("utf-8")), True
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace"), False


def media_type_for(path_text: str) -> str:
    """Tipo de mídia pela extensão; o mesmo da ingestão, usado também pela auditoria."""
    return MEDIA_TYPES.get(posixpath.splitext(path_text)[1].lower(), "application/octet-stream")


def _classify_kind(path_text: str, generated: bool, policy: Policy) -> tuple[str, str]:
    if generated:
        rule = next(p for p in policy.generated if matches(path_text, p))
        return "generated", f"generated:{rule}"
    for rule in policy.kind_rules:
        if matches(path_text, rule.pattern):
            return rule.kind, f"kind:{rule.pattern}"
    return "other", "kind:default"


def read_blobs(repo: Path, oids: list[str]) -> dict[str, bytes]:
    """Conteúdo completo de cada blob, numa única chamada `git cat-file --batch`."""
    if not oids:
        return {}
    unique = sorted(set(oids))
    out = _git(repo, "cat-file", "--batch", input=("\n".join(unique) + "\n").encode())
    blobs, pos = {}, 0
    for _ in unique:
        header_end = out.index(b"\n", pos)
        header = out[pos:header_end].decode().split(" ")
        if len(header) != 3:  # "<oid> missing"
            raise KosError("E_BLOB_UNREADABLE", f"blob {header[0]} não pôde ser lido")
        oid, _type, size = header
        start = header_end + 1
        blobs[oid] = out[start:start + int(size)]
        pos = start + int(size) + 1
    return blobs


def _sniff_heads(repo: Path, oids: list[str]) -> dict[str, bytes]:
    """Primeiros bytes de cada blob candidato."""
    return {oid: data[:BINARY_SNIFF_BYTES] for oid, data in read_blobs(repo, oids).items()}


def discover(repo: Path, rev: str, policy: Policy) -> tuple[str, list[DiscoveredFile]]:
    """Lista todos os arquivos da árvore de `rev`, com elegibilidade e tipo.

    Devolve o OID completo do commit e a lista ordenada por `path_bytes`.
    """
    commit = resolve_commit(repo, rev)
    raw = _git(repo, "ls-tree", "-r", "-l", "-z", "--full-tree", commit)
    entries = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        meta, path = record.split(b"\t", 1)
        mode, _type, oid, size = meta.decode().split()
        entries.append((path, mode, oid, None if size == "-" else int(size)))
    entries.sort(key=lambda e: e[0])

    # Só lê conteúdo dos blobs regulares que ainda podem ser elegíveis.
    candidates = []
    for path, mode, oid, size in entries:
        text, _ = _decode_path(path)
        if (mode in ("100644", "100755") and size is not None and size <= policy.max_bytes
                and any(matches(text, p) for p in policy.include)
                and not any(matches(text, p) for p in policy.exclude)):
            candidates.append(oid)
    heads = _sniff_heads(repo, candidates)

    files = []
    for path, mode, oid, size in entries:
        text, is_utf8 = _decode_path(path)
        generated = any(matches(text, p) for p in policy.generated)
        kind, kind_rule = _classify_kind(text, generated, policy)
        rule = _exclusion_rule(text, mode, oid, size, policy, heads)
        files.append(DiscoveredFile(
            path_bytes=path, path_text=text, path_is_utf8=is_utf8, blob_oid=oid,
            file_mode=mode, byte_size=size, media_type=media_type_for(text),
            eligibility="excluded" if rule else "eligible", exclusion_rule=rule,
            artifact_kind=kind, kind_rule=kind_rule, is_generated=generated,
        ))
    return commit, files


def _exclusion_rule(text, mode, oid, size, policy, heads) -> str | None:
    if mode == "120000":
        return "symlink_not_followed"
    if mode == "160000":
        return "submodule_not_followed"
    if not any(matches(text, p) for p in policy.include):
        return "not_included"
    for pattern in policy.exclude:
        if matches(text, pattern):
            return f"excluded:{pattern}"
    if size is not None and size > policy.max_bytes:
        return "too_large"
    head = heads.get(oid, b"")
    if head.startswith(LFS_PREFIX):
        return "lfs_pointer"
    if looks_binary(head):
        return "binary_unsupported"
    return None


def looks_binary(head: bytes) -> bool:
    """Heurística de binário sobre os primeiros bytes do blob.

    Um byte nulo sozinho não basta: o corpus real tem texto com NUL de propósito
    (ex.: `scripts/optimize-critical-path.mjs` no mauricio-site usa um byte NUL como
    sentinela). É binário se tiver NUL e não for UTF-8 válido, ou se mais de 10%
    dos bytes forem de controle.
    """
    if b"\0" not in head:
        return False
    decoder = codecs.getincrementaldecoder("utf-8")()
    try:
        decoder.decode(head, final=False)  # tolera caractere cortado no fim
    except UnicodeDecodeError:
        return True
    control = sum(1 for b in head if b < 9 or 13 < b < 32)
    return control > len(head) * 0.10
