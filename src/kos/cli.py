"""Interface de linha de comando `kos` (ADR-kos-005).

A CLI é uma casca fina sobre a biblioteca. Toda saída tem uma forma humana e uma
forma JSON (`--json`) com esquema versionado `kos.<comando>.v1`. Códigos de
saída seguem CTR-10.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from kos import __version__
from kos import discovery
from kos.errors import EXIT_EXECUTION, EXIT_OK, EXIT_USAGE, KosError
from kos.store import schema

DEFAULT_HOME = ".kos"


class _Parser(argparse.ArgumentParser):
    """argparse sai com 2 em erro de uso; CTR-10 reserva 2 para erro de execução."""

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: erro de uso: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="kos", description="Knowledge OS Enterprise")
    parser.add_argument("--version", action="version", version=f"kos {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    init = sub.add_parser("init", help="cria index.sqlite e audit.sqlite")
    init.add_argument(
        "--home",
        default=os.environ.get("KOS_HOME", DEFAULT_HOME),
        help="diretório dos bancos (padrão: $KOS_HOME ou ./.kos)",
    )
    init.add_argument("--json", action="store_true", help="saída JSON kos.init.v1")
    init.set_defaults(handler=_cmd_init)

    disc = sub.add_parser("discover", help="lista os arquivos elegíveis de uma revisão (CTR-01)")
    disc.add_argument("repo", help="caminho do repositório Git")
    disc.add_argument("--rev", default="HEAD", help="revisão (padrão: HEAD)")
    disc.add_argument("--policy", help="arquivo JSON da política (padrão: política empacotada)")
    disc.add_argument("--json", action="store_true", help="saída JSON kos.discover.v1")
    disc.set_defaults(handler=_cmd_discover)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except KosError as err:
        _emit_error(err, as_json=getattr(args, "json", False))
        return EXIT_EXECUTION


def _cmd_init(args: argparse.Namespace) -> int:
    home = Path(args.home)
    results = schema.initialize(home)
    if args.json:
        payload = {
            "schema": "kos.init.v1",
            "home": str(home.resolve()),
            "schema_version": schema.SCHEMA_VERSION,
            "sqlite_version": sqlite3.sqlite_version,
            "tool_version": __version__,
            "databases": [
                {"name": r.name, "path": str(r.path.resolve()), "status": r.status}
                for r in results
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for r in results:
            verb = "criado" if r.status == "created" else "já existia"
            print(f"{r.path}: {verb} (esquema {schema.SCHEMA_VERSION})")
    return EXIT_OK


def _cmd_discover(args: argparse.Namespace) -> int:
    policy = discovery.Policy.load(Path(args.policy)) if args.policy else discovery.Policy.default()
    commit, files = discovery.discover(Path(args.repo), args.rev, policy)
    eligible = [f for f in files if f.eligibility == "eligible"]
    if args.json:
        payload = {
            "schema": "kos.discover.v1",
            "commit_oid": commit,
            "policy": {"policy_id": policy.policy_id, "version": policy.version,
                       "sha256": policy.sha256},
            "counts": {"total": len(files), "eligible": len(eligible),
                       "excluded": len(files) - len(eligible)},
            "files": [f.to_json() for f in files],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for f in files:
            status = f.artifact_kind if f.eligibility == "eligible" else f"excluído: {f.exclusion_rule}"
            print(f"{f.path_text}\t{status}")
        print(f"{commit}: {len(files)} arquivo(s), {len(eligible)} elegível(is)", file=sys.stderr)
    return EXIT_OK


def _emit_error(err: KosError, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(
            {"schema": "kos.error.v1", "code": err.code, "message": err.message},
            ensure_ascii=False,
        ))
    else:
        print(f"kos: {err.code}: {err.message}", file=sys.stderr)
