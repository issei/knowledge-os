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
from kos import cite, discovery, ingest, rebuild, search
from kos.errors import EXIT_EXECUTION, EXIT_OK, EXIT_PARTIAL, EXIT_USAGE, KosError
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

    ing = sub.add_parser("ingest", help="indexa uma revisão do repositório (CTR-03)")
    ing.add_argument("repo", help="caminho do repositório Git")
    ing.add_argument("--rev", default="HEAD", help="revisão (padrão: HEAD)")
    ing.add_argument("--full", action="store_true", required=True,
                     help="ingestão completa da revisão (a incremental vem no BL-16)")
    ing.add_argument("--name", help="nome lógico do repositório (padrão: nome da pasta)")
    ing.add_argument("--policy", help="arquivo JSON da política (padrão: política empacotada)")
    ing.add_argument("--home", default=os.environ.get("KOS_HOME", DEFAULT_HOME),
                     help="diretório dos bancos (padrão: $KOS_HOME ou ./.kos)")
    ing.add_argument("--json", action="store_true", help="saída JSON kos.ingest.v1")
    ing.set_defaults(handler=_cmd_ingest)

    reb = sub.add_parser("rebuild", help="reconstrói index.sqlite a partir do Git (CTR-05)")
    reb.add_argument("--repo", action="append", required=True, metavar="NOME=CAMINHO",
                     help="repositório e o caminho do clone local (repetível)")
    reb.add_argument("--rev", action="append", metavar="NOME@COMMIT",
                     help="revisão a reconstruir (repetível; padrão: as retidas no índice atual)")
    reb.add_argument("--policy", help="arquivo JSON da política (padrão: política empacotada)")
    reb.add_argument("--home", default=os.environ.get("KOS_HOME", DEFAULT_HOME),
                     help="diretório dos bancos (padrão: $KOS_HOME ou ./.kos)")
    reb.add_argument("--json", action="store_true", help="saída JSON kos.rebuild.v1")
    reb.set_defaults(handler=_cmd_rebuild)

    sea = sub.add_parser("search", help="busca evidências numa revisão indexada (CTR-06)")
    sea.add_argument("query", help="texto da consulta")
    sea.add_argument("--repo", help="só este repositório")
    sea.add_argument("--rev", help="commit completo (padrão: última revisão consultável)")
    sea.add_argument("-k", type=int, default=10, help="quantos resultados (padrão: 10)")
    sea.add_argument("--path", help="filtro de caminho no estilo gitignore, ex.: 'docs/**'")
    sea.add_argument("--kind", action="append", help="tipo de artefato (repetível)")
    sea.add_argument("--include-generated", action="store_true", help="inclui arquivos gerados, marcados")
    sea.add_argument("--home", default=os.environ.get("KOS_HOME", DEFAULT_HOME),
                     help="diretório dos bancos (padrão: $KOS_HOME ou ./.kos)")
    sea.add_argument("--json", action="store_true", help="saída JSON kos.search.v1")
    sea.set_defaults(handler=_cmd_search)

    cit = sub.add_parser("cite", help="monta citações verificadas contra o Git (CTR-07)")
    cit.add_argument("fragment_key", nargs="+", help="chave(s) de fragmento, como as de `kos search`")
    cit.add_argument("--rev", help="commit completo (padrão: a última revisão que contém o fragmento)")
    cit.add_argument("--lines", metavar="A-B", help="sub-intervalo de linhas dentro do fragmento")
    cit.add_argument("--repo", action="append", default=[], metavar="NOME=CAMINHO",
                     help="onde está o clone (padrão: o caminho da última ingestão)")
    cit.add_argument("--home", default=os.environ.get("KOS_HOME", DEFAULT_HOME),
                     help="diretório dos bancos (padrão: $KOS_HOME ou ./.kos)")
    cit.add_argument("--json", action="store_true", help="saída JSON kos.cite.v1")
    cit.set_defaults(handler=_cmd_cite)
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


def _cmd_ingest(args: argparse.Namespace) -> int:
    policy = discovery.Policy.load(Path(args.policy)) if args.policy else discovery.Policy.default()
    result = ingest.ingest_full(Path(args.home), Path(args.repo), rev=args.rev, policy=policy,
                                repo_name=args.name)
    if args.json:
        print(json.dumps({
            "schema": "kos.ingest.v1", "run_uuid": result.run_uuid, "mode": "full",
            "repo": result.repo_name, "commit_oid": result.commit_oid, "status": result.status,
            "policy_sha256": policy.sha256, "counts": result.counts, "errors": result.errors,
        }, ensure_ascii=False, indent=2))
    else:
        for e in result.errors:
            print(f"{e['severity']}: {e['path']}: {e['code']}: {e['message']}", file=sys.stderr)
        c = result.counts
        print(f"{result.repo_name}@{result.commit_oid}: {result.status}; {c['eligible']} elegível(is),"
              f" {c['processed']} processado(s), {c['reused']} reaproveitado(s), {c['failed']} com falha,"
              f" {c['fragments']} fragmento(s) novo(s)")
    return EXIT_PARTIAL if result.status == "partial" else EXIT_OK


def _cmd_rebuild(args: argparse.Namespace) -> int:
    repos = dict(_split_arg(item, "=", "--repo") for item in args.repo)
    revisions = [_split_arg(item, "@", "--rev") for item in args.rev] if args.rev else None
    policy = discovery.Policy.load(Path(args.policy)) if args.policy else discovery.Policy.default()
    result = rebuild.rebuild(Path(args.home), {k: Path(v) for k, v in repos.items()},
                             policy=policy, revisions=revisions)
    if args.json:
        print(json.dumps({
            "schema": "kos.rebuild.v1", "status": result.status, "policy_sha256": policy.sha256,
            "revisions": result.revisions, "missing": result.missing,
            "old_digest": result.old_digest, "new_digest": result.new_digest,
            "fragments_added": result.fragments_added, "fragments_removed": result.fragments_removed,
        }, ensure_ascii=False, indent=2))
    else:
        for m in result.missing:
            print(f"erro: {m['repo']}@{m['commit_oid']}: {m['code']}: {m['message']}", file=sys.stderr)
        for r in result.revisions:
            print(f"{r['repo']}@{r['commit_oid']}: {r['status']}")
        same = "igual ao anterior" if result.old_digest == result.new_digest else "diferente do anterior"
        print(f"rebuild {result.status}; conteúdo lógico {same} ({result.new_digest[:12]})")
    return EXIT_PARTIAL if result.status == "partial" else EXIT_OK


def _cmd_search(args: argparse.Namespace) -> int:
    result = search.search(Path(args.home), args.query, repo=args.repo, commit=args.rev, k=args.k,
                           path_glob=args.path, kinds=args.kind, include_generated=args.include_generated)
    if args.json:
        print(json.dumps({
            "schema": "kos.search.v1", "revisions": result.revisions,
            "results": [h.to_json() for h in result.results], "diagnostics": result.diagnostics,
        }, ensure_ascii=False, indent=2))
    else:
        for h in result.results:
            lines = f"#L{h.locator.start_line}-L{h.locator.end_line}" if h.locator.start_line else ""
            mark = " (gerado)" if h.is_generated else ""
            print(f"{h.rank:>3}. {h.path_text}{lines}{mark}  [{h.score:.3f}]")
            print("     " + h.snippet.replace("\n", " "))
        revs = ", ".join(f"{r['repo']}@{r['commit_oid'][:12]}" for r in result.revisions)
        d = result.diagnostics
        print(f"{d['total_hits']} resultado(s) em {revs}; {d['latency_ms']} ms", file=sys.stderr)
    return EXIT_OK


def _cmd_cite(args: argparse.Namespace) -> int:
    repos = {k: Path(v) for k, v in (_split_arg(item, "=", "--repo") for item in args.repo)}
    lines = None
    if args.lines:
        first, _, last = args.lines.partition("-")
        if not first.isdigit() or not (last or first).isdigit():
            raise SystemExit(f"kos: erro de uso: --lines espera A-B, recebeu {args.lines!r}")
        lines = (int(first), int(last or first))
    citations = cite.cite(Path(args.home), args.fragment_key, commit=args.rev, repos=repos, lines=lines)
    if args.json:
        print(json.dumps({"schema": "kos.cite.v1", "citations": [c.to_json() for c in citations]},
                         ensure_ascii=False, indent=2))
    else:
        print("\n".join(c.human() for c in citations))
    return EXIT_OK


def _split_arg(value: str, sep: str, flag: str) -> tuple[str, str]:
    left, found, right = value.partition(sep)
    if not found or not left or not right:
        raise SystemExit(f"kos: erro de uso: {flag} espera NOME{sep}VALOR, recebeu {value!r}")
    return left, right


def _emit_error(err: KosError, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(
            {"schema": "kos.error.v1", "code": err.code, "message": err.message},
            ensure_ascii=False,
        ))
    else:
        print(f"kos: {err.code}: {err.message}", file=sys.stderr)
