"""Política de elegibilidade versionada (CTR-01).

A política é um JSON:

    {
      "policy_id": "mauricio-site", "version": 1,
      "include": ["**"], "exclude": ["node_modules/**"],
      "max_bytes": 1000000,
      "generated": ["src/en/**"],
      "kind_rules": [{"pattern": "**/ADR-*.md", "kind": "adr"}, ...]
    }

`policy_sha256` é o SHA-256 do JSON canônico (chaves ordenadas, sem espaços)
e entra em `ingest_run.policy_sha256`: mudar a política muda a impressão digital.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from kos.discovery.glob import compile_pattern
from kos.errors import KosError

ARTIFACT_KINDS = ("doc", "spec", "adr", "code", "test", "config", "data", "generated", "other")
_REQUIRED = {"policy_id": str, "version": int, "include": list, "exclude": list,
             "max_bytes": int, "generated": list, "kind_rules": list}


@dataclass(frozen=True)
class KindRule:
    pattern: str
    kind: str


@dataclass(frozen=True)
class Policy:
    policy_id: str
    version: int
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    max_bytes: int
    generated: tuple[str, ...]
    kind_rules: tuple[KindRule, ...]
    sha256: str

    @classmethod
    def from_dict(cls, data: object) -> "Policy":
        def invalid(msg: str) -> KosError:
            return KosError("E_POLICY_INVALID", msg)

        if not isinstance(data, dict):
            raise invalid("a política precisa ser um objeto JSON")
        unknown = set(data) - set(_REQUIRED)
        if unknown:
            raise invalid(f"campos desconhecidos: {sorted(unknown)}")
        for key, typ in _REQUIRED.items():
            if key not in data:
                raise invalid(f"campo obrigatório ausente: {key}")
            if not isinstance(data[key], typ) or (typ is int and isinstance(data[key], bool)):
                raise invalid(f"{key} deve ser {typ.__name__}")
        if data["max_bytes"] <= 0:
            raise invalid("max_bytes deve ser positivo")
        patterns = [*data["include"], *data["exclude"], *data["generated"]]
        rules = []
        for rule in data["kind_rules"]:
            if not isinstance(rule, dict) or set(rule) != {"pattern", "kind"}:
                raise invalid(f"kind_rule inválida: {rule!r}")
            if rule["kind"] not in ARTIFACT_KINDS:
                raise invalid(f"kind desconhecido: {rule['kind']!r}")
            rules.append(KindRule(rule["pattern"], rule["kind"]))
            patterns.append(rule["pattern"])
        for pattern in patterns:
            try:
                if not isinstance(pattern, str):
                    raise ValueError(pattern)
                compile_pattern(pattern)
            except ValueError:
                raise invalid(f"padrão inválido: {pattern!r}") from None
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return cls(
            policy_id=data["policy_id"], version=data["version"],
            include=tuple(data["include"]), exclude=tuple(data["exclude"]),
            max_bytes=data["max_bytes"], generated=tuple(data["generated"]),
            kind_rules=tuple(rules),
            sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )

    @classmethod
    def load(cls, path: Path) -> "Policy":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise KosError("E_POLICY_INVALID", f"não foi possível ler {path}: {exc}") from exc
        return cls.from_dict(data)

    @classmethod
    def default(cls) -> "Policy":
        """Política empacotada, usada quando nenhuma é informada."""
        text = resources.files("kos.discovery").joinpath("default_policy.json").read_text("utf-8")
        return cls.from_dict(json.loads(text))
