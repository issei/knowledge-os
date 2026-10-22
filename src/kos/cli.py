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


def _emit_error(err: KosError, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(
            {"schema": "kos.error.v1", "code": err.code, "message": err.message},
            ensure_ascii=False,
        ))
    else:
        print(f"kos: {err.code}: {err.message}", file=sys.stderr)
