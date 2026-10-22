"""Benchmark próprio: golden set, auto-verificação, métricas e relatório B0 (BL-14; 04-benchmark.md).

- `load_suite`: lê e valida o YAML do golden set (TC-BEN-01).
- `self_check`: confere no Git que cada fonte e cada trecho esperado existem na
  revisão do caso (TC-BEN-02). O golden set se auto-verifica antes de medir.
- `retrieval_metrics` e `answer_metrics`: métricas de §5, separadas por nível (TC-BEN-03).
- `run`: executa as configurações e devolve o relatório `kos.bench.v1` com
  fingerprint do índice, versões e hardware (TC-BEN-04).

Configurações:

- `B0` (§6.1): `bm25()` com pesos de coluna iguais, resposta extrativa, abstenção só
  pelos casos estruturais (`no_hits`, `unverifiable_evidence`, `revision_unavailable`).
- `atual`: os padrões desta versão (pesos de `search.COLUMN_WEIGHTS`, limiares de
  `answer.Thresholds`). Mostra o que mudou desde B0, não substitui B0.
- `B0-grep` e `B0-path`: só recuperação, para saber o que o FTS5 agrega sobre
  `git grep` e sobre o nome do arquivo.

Afirmações obrigatórias e proibidas são texto livre: o relatório as lista com as
afirmações produzidas para revisão humana, sem nota automática (§5.3).
"""

from __future__ import annotations

import datetime
import html
import platform
import re
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

import yaml

from kos import __version__, audit, discovery
from kos.answer import STOPWORDS, Answer, Thresholds, ask, essential_terms, fold
from kos.errors import KosError
from kos.ingest import ingest_full
from kos.parsing.normalize import normalize
from kos.search import COLUMN_WEIGHTS

CLASSES = ("lexical", "spec_fact", "code", "conflict", "no_answer")
OUTCOMES = ("answered", "answered_with_conflict", "abstained")
K_VALUES = (1, 3, 5, 10)
MRR_CLASSES = ("lexical", "spec_fact", "code")
_LINES = re.compile(r"(\d+)(?:-(\d+))?")
_WORD = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class Source:
    path: str
    first: int
    last: int
    relevance: int = 0
    excerpt: str | None = None


@dataclass(frozen=True)
class Case:
    id: str
    classe: str
    question: str
    revision: str
    sources: tuple[Source, ...]
    evidence: tuple[Source, ...]
    outcome: str
    abstention_codes: tuple[str, ...]
    required: tuple[str, ...]
    forbidden: tuple[str, ...]


@dataclass(frozen=True)
class Suite:
    name: str
    repo: str
    revision: str
    cases: tuple[Case, ...]


@dataclass(frozen=True)
class Unit:
    """Unidade recuperada: caminho e intervalo de linhas (inclusivo)."""
    path: str
    first: int
    last: int


# ---------------------------------------------------------------- golden set

def _lines(value, where: str) -> tuple[int, int]:
    m = _LINES.fullmatch(str(value))
    if not m:
        raise KosError("E_SUITE_INVALID", f"{where}: linhas {value!r} não estão no formato a ou a-b")
    first, last = int(m.group(1)), int(m.group(2) or m.group(1))
    if not 1 <= first <= last:
        raise KosError("E_SUITE_INVALID", f"{where}: intervalo de linhas {value!r} inválido")
    return first, last


def _require(data: dict, key: str, kind, where: str):
    if not isinstance(data.get(key), kind):
        raise KosError("E_SUITE_INVALID", f"{where}: campo {key!r} ausente ou com tipo errado")
    return data[key]


def load_suite(path: Path) -> Suite:
    """Lê o golden set e valida o esquema de 04-benchmark.md §2 (TC-BEN-01)."""
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise KosError("E_SUITE_INVALID", f"{path}: {exc}") from exc
    if not isinstance(data, dict):
        raise KosError("E_SUITE_INVALID", f"{path}: esperado um mapa com suite, repo, revisao e casos")
    name = _require(data, "suite", str, str(path))
    repo = _require(data, "repo", str, str(path))
    revision = _require(data, "revisao", str, str(path))
    cases, seen = [], set()
    for raw in _require(data, "casos", list, str(path)):
        where = f"{path}: caso {raw.get('id', '?') if isinstance(raw, dict) else '?'}"
        if not isinstance(raw, dict):
            raise KosError("E_SUITE_INVALID", f"{where}: caso precisa ser um mapa")
        case_id = _require(raw, "id", str, where)
        if case_id in seen:
            raise KosError("E_SUITE_INVALID", f"{where}: id repetido")
        seen.add(case_id)
        classe = _require(raw, "classe", str, where)
        if classe not in CLASSES:
            raise KosError("E_SUITE_INVALID", f"{where}: classe {classe!r} desconhecida")
        expected = _require(raw, "resultado_esperado", dict, where)
        outcome = _require(expected, "outcome", str, where)
        if outcome not in OUTCOMES:
            raise KosError("E_SUITE_INVALID", f"{where}: outcome {outcome!r} desconhecido")
        codes = tuple(expected.get("abstention_codes_aceitos") or ())
        if (outcome == "abstained") != bool(codes):
            raise KosError("E_SUITE_INVALID", f"{where}: abstention_codes_aceitos só (e sempre) com abstained")
        sources = []
        for s in raw.get("fontes_relevantes") or []:
            if s.get("relevancia") not in (1, 2):
                raise KosError("E_SUITE_INVALID", f"{where}: relevancia precisa ser 1 ou 2")
            sources.append(Source(_require(s, "caminho", str, where), *_lines(s.get("linhas"), where),
                                  relevance=s["relevancia"]))
        evidence = [Source(_require(e, "caminho", str, where), *_lines(e.get("linhas"), where),
                           excerpt=_require(e, "trecho", str, where))
                    for e in raw.get("evidencia_esperada") or []]
        cases.append(Case(case_id, classe, _require(raw, "pergunta", str, where),
                          _require(raw, "revisao_esperada", str, where), tuple(sources), tuple(evidence),
                          outcome, codes, tuple(expected.get("afirmacoes_obrigatorias") or ()),
                          tuple(expected.get("afirmacoes_proibidas") or ())))
    if not cases:
        raise KosError("E_SUITE_INVALID", f"{path}: nenhum caso")
    return Suite(name, repo, revision, tuple(cases))


def _show(repo_dir: Path, revision: str, path: str) -> bytes | None:
    proc = subprocess.run(["git", "-C", str(repo_dir), "show", f"{revision}:{path}"],
                          capture_output=True, check=False)
    return proc.stdout if proc.returncode == 0 else None


def self_check(suite: Suite, repo_dir: Path) -> list[str]:
    """Problemas do golden set contra o Git; lista vazia = auto-verificado (TC-BEN-02)."""
    problems = []
    for case in suite.cases:
        for s in (*case.sources, *case.evidence):
            blob = _show(repo_dir, case.revision, s.path)
            if blob is None:
                problems.append(f"{case.id}: {s.path} não existe em {case.revision[:12]}")
                continue
            lines = normalize(blob).split("\n")
            if s.last > len(lines):
                problems.append(f"{case.id}: {s.path} tem {len(lines)} linhas, o caso pede {s.first}-{s.last}")
                continue
            if s.excerpt is not None and s.excerpt not in "\n".join(lines[s.first - 1:s.last]):
                problems.append(f"{case.id}: trecho esperado não está em {s.path}#L{s.first}-L{s.last}")
    return problems


# ---------------------------------------------------------------- métricas

def _overlaps(unit: Unit, source: Source) -> bool:
    return unit.path == source.path and unit.first <= source.last and source.first <= unit.last


def relevance_of(unit: Unit, case: Case) -> int:
    return max((s.relevance for s in case.sources if _overlaps(unit, s)), default=0)


def retrieval_metrics(case: Case, units: list[Unit]) -> dict:
    """Recall@k, Precision@k e MRR de um caso (04-benchmark.md §5.1)."""
    if not case.sources:
        return {"applicable": False, "returned": len(units)}
    out: dict = {"applicable": True, "returned": len(units)}
    for k in K_VALUES:
        top = units[:k]
        covered = sum(1 for s in case.sources if any(_overlaps(u, s) for u in top))
        out[f"recall@{k}"] = covered / len(case.sources)
        out[f"precision@{k}"] = sum(1 for u in top if relevance_of(u, case)) / k
    if case.classe in MRR_CLASSES:
        first = next((i for i, u in enumerate(units, 1) if relevance_of(u, case) == 2), None)
        out["mrr"] = 1 / first if first else 0.0
        out["first_essential_rank"] = first
    return out


def _comparable(text: str) -> str:
    return " ".join(html.unescape(normalize(text.encode())).split())


def answer_metrics(case: Case, answer: Answer) -> dict:
    """Métricas de resposta de §5.3 que são automáticas; o resto vai para revisão humana."""
    abstained = answer.outcome == "abstained"
    code = answer.abstention["code"] if abstained else None
    out = {
        "outcome": answer.outcome, "expected_outcome": case.outcome, "abstention_code": code,
        "outcome_ok": answer.outcome == case.outcome and (not abstained or code in case.abstention_codes),
        "improper_abstention": abstained and case.outcome != "abstained",
    }
    if case.classe == "no_answer":
        out["gap_recognized"] = abstained and code in case.abstention_codes
    if case.outcome == "answered_with_conflict":
        out["conflict_detected"] = (answer.outcome == "answered_with_conflict"
                                    and any(len(c["sides"]) >= 2 for c in answer.conflicts))
    if case.evidence:
        quoted = [_comparable(c.quoted_text) for c in answer.citations]
        out["expected_evidence_hit"] = any(_comparable(e.excerpt) in q for e in case.evidence for q in quoted)
    return out


def recheck_citations(answer: Answer, repo_dir: Path) -> dict:
    """Conferência independente das citações: relê `commit:caminho` (não o blob do índice)."""
    states: dict[str, int] = {}
    false_exact = []
    for c in answer.citations:
        states[c.verification] = states.get(c.verification, 0) + 1
        if c.verification != "verified_exact":
            continue
        blob = _show(repo_dir, c.commit_oid, c.path_text)
        literal = None if blob is None else normalize(blob[c.locator.start_byte:c.locator.end_byte])
        if literal != c.quoted_text:
            false_exact.append(f"{c.path_text}#{c.locator.start_byte}-{c.locator.end_byte}")
    return {"states": states, "false_verified_exact": false_exact}


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 4) if values else None


def _aggregate(per_case: dict[str, dict], keys: list[str]) -> dict:
    out = {}
    for key in keys:
        values = [m[key] for m in per_case.values() if key in m and m.get("applicable", True)]
        out[key] = _mean([float(v) for v in values])
        out[f"{key}__n"] = len(values)
    return out


def _percentiles(samples: list[float]) -> dict:
    if not samples:
        return {}
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
    return {"p50_ms": round(statistics.median(ordered), 1), "p95_ms": round(p95, 1), "samples": len(ordered)}


# ---------------------------------------------------------------- linhas de base

def _baseline_terms(question: str) -> list[str]:
    """Palavras da pergunta como escritas (com acento), menos as vazias; para git grep."""
    words = dict.fromkeys(w.lower() for w in _WORD.findall(question))
    return [w for w in words if fold(w) not in STOPWORDS]


def grep_units(repo_dir: Path, revision: str, question: str, paths: list[str], k: int) -> list[Unit]:
    """B0-grep: linhas de `git grep -i -F` ordenadas pelo número de termos distintos na linha."""
    terms = _baseline_terms(question)
    if not terms or not paths:
        return []
    args = ["git", "-C", str(repo_dir), "grep", "-n", "-i", "-I", "-F", "--full-name"]
    for t in terms:
        args += ["-e", t]
    proc = subprocess.run([*args, revision, "--", *paths], capture_output=True, check=False)
    folded_terms = [fold(t) for t in terms]
    scored = []
    prefix = f"{revision}:".encode()
    for raw in proc.stdout.split(b"\n"):
        if not raw.startswith(prefix):
            continue
        path, line, text = raw[len(prefix):].decode("utf-8", "replace").split(":", 2)
        score = sum(1 for t in folded_terms if t in fold(text))
        scored.append((-score, path, int(line)))
    scored.sort()
    return [Unit(p, n, n) for _, p, n in scored[:k]]


def path_units(question: str, paths: list[str], k: int) -> list[Unit]:
    """B0-path: arquivos cujo caminho contém termos da pergunta, por número de termos."""
    terms = set(essential_terms(question))
    scored = []
    for p in paths:
        score = len(terms & set(_WORD.findall(fold(p))))
        if score:
            scored.append((-score, p))
    scored.sort()
    return [Unit(p, 1, 10**9) for _, p in scored[:k]]


# ---------------------------------------------------------------- execução

CONFIGS = {
    "B0": {"description": "bm25 com pesos iguais; abstenção só estrutural (no_hits, unverifiable_evidence)",
           "weights": (1.0, 1.0, 1.0), "thresholds": Thresholds(require_terms_in_corpus=False)},
    "atual": {"description": "padrões desta versão",
              "weights": COLUMN_WEIGHTS, "thresholds": Thresholds()},
}


def _versions() -> dict:
    out = {"kos": __version__, "python": platform.python_version(), "sqlite": __import__("sqlite3").sqlite_version}
    for dist in ("markdown-it-py", "PyYAML"):
        try:
            out[dist] = metadata.version(dist)
        except metadata.PackageNotFoundError:
            out[dist] = None
    git = subprocess.run(["git", "--version"], capture_output=True, text=True, check=False)
    out["git"] = git.stdout.strip()
    return out


def _hardware() -> dict:
    import os
    return {"platform": platform.platform(), "machine": platform.machine(),
            "processor": platform.processor() or None, "cpu_count": os.cpu_count()}


def _peak_rss_kib() -> int | None:
    try:
        import resource
    except ImportError:  # Windows
        return None
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss // 1024 if sys.platform == "darwin" else rss


def _units_from_hits(hits) -> list[Unit]:
    return [Unit(h.path_text, h.locator.start_line or 1, h.locator.end_line or 10**9) for h in hits]


def run(suite: Suite, *, home: Path, repo_dir: Path, policy: discovery.Policy, k: int = 10,
        repetitions: int = 3) -> dict:
    """Executa B0, a configuração atual e as linhas de base; devolve o relatório kos.bench.v1."""
    problems = self_check(suite, repo_dir)
    if problems:
        raise KosError("E_SUITE_INVALID", "o golden set não se auto-verifica: " + "; ".join(problems[:5]))
    home = Path(home)
    started = time.perf_counter()
    ingest = ingest_full(home, repo_dir, rev=suite.revision, policy=policy, repo_name=suite.repo)
    ingest_seconds = round(time.perf_counter() - started, 2)
    _, files = discovery.discover(repo_dir, suite.revision, policy)
    eligible = [f.path_text for f in files if f.eligibility == "eligible" and not f.is_generated]

    report: dict = {
        "schema": "kos.bench.v1", "suite": suite.name, "repo": suite.repo, "revision": suite.revision,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "k": k, "repetitions": repetitions, "versions": _versions(), "hardware": _hardware(),
        "index": {"fingerprint": audit.index_fingerprint(home), "ingest_status": ingest.status,
                  "ingest_seconds": ingest_seconds, "ingest_counts": ingest.counts,
                  "index_bytes": (home / "index.sqlite").stat().st_size,
                  "fragments": _count_fragments(home), "eligible_files": len(eligible)},
        "configs": {}, "human_review": [],
    }
    retrieval_keys = [f"{m}@{k_}" for k_ in K_VALUES for m in ("recall", "precision")] + ["mrr"]
    answer_keys = ["outcome_ok", "improper_abstention", "gap_recognized", "conflict_detected",
                   "expected_evidence_hit"]

    for name, cfg in CONFIGS.items():
        per_retrieval, per_answer, citations, search_ms, ask_ms = {}, {}, [], [], []
        for case in suite.cases:
            for _ in range(repetitions):
                t = time.perf_counter()
                _, result = audit.audited_search(home, case.question, interface="bench", repo=suite.repo,
                                                 commit=case.revision, k=k, weights=cfg["weights"])
                search_ms.append((time.perf_counter() - t) * 1000)
            per_retrieval[case.id] = retrieval_metrics(case, _units_from_hits(result.results))
            for _ in range(repetitions):
                t = time.perf_counter()
                answer = ask(home, case.question, repo=suite.repo, commit=case.revision, k=k,
                             thresholds=cfg["thresholds"], repos={suite.repo: repo_dir}, interface="bench",
                             weights=cfg["weights"])
                ask_ms.append((time.perf_counter() - t) * 1000)
            per_answer[case.id] = answer_metrics(case, answer)
            check = recheck_citations(answer, repo_dir)
            per_answer[case.id]["citation_states"] = check["states"]
            citations.append(check)
            if name == "B0" and (case.required or case.forbidden):
                report["human_review"].append({
                    "case": case.id, "outcome": answer.outcome, "required": list(case.required),
                    "forbidden": list(case.forbidden),
                    "claims": [{"text": c.text[:300], "citations": [
                        f"{answer.citations[n - 1].path_text}#L{answer.citations[n - 1].locator.start_line}"
                        for n in c.citation_nos]} for c in answer.claims]})
        total = sum(sum(c["states"].values()) for c in citations)
        verified = sum(c["states"].get(s, 0) for c in citations for s in ("verified_exact", "verified_normalized"))
        report["configs"][name] = {
            "description": cfg["description"], "weights": list(cfg["weights"]),
            "thresholds": cfg["thresholds"].to_json(),
            "retrieval": {"aggregate": _aggregate(per_retrieval, retrieval_keys), "per_case": per_retrieval},
            "answer": {"aggregate": _aggregate(per_answer, answer_keys), "per_case": per_answer},
            "citations": {"total": total, "verified": verified,
                          "exactness": round(verified / total, 4) if total else None,
                          "false_verified_exact": [f for c in citations for f in c["false_verified_exact"]]},
            "latency": {"search": _percentiles(search_ms), "ask": _percentiles(ask_ms)},
        }

    for name, fn in (("B0-grep", lambda c: grep_units(repo_dir, c.revision, c.question, eligible, k)),
                     ("B0-path", lambda c: path_units(c.question, eligible, k))):
        per, ms = {}, []
        for case in suite.cases:
            for _ in range(repetitions):
                t = time.perf_counter()
                units = fn(case)
                ms.append((time.perf_counter() - t) * 1000)
            per[case.id] = retrieval_metrics(case, units)
        report["configs"][name] = {"description": "só recuperação",
                                   "retrieval": {"aggregate": _aggregate(per, retrieval_keys), "per_case": per},
                                   "latency": {"search": _percentiles(ms)}}
    report["resources"] = {"peak_rss_kib": _peak_rss_kib()}
    return report


def summary(report: dict) -> str:
    """Tabela curta do relatório para o terminal."""
    lines = [f"{report['suite']} @ {report['revision'][:12]}, k={report['k']}, "
             f"índice {report['index']['fingerprint'][:12]}"]
    for name, cfg in report["configs"].items():
        r = cfg["retrieval"]["aggregate"]
        parts = [f"R@10={r.get('recall@10')}", f"P@10={r.get('precision@10')}", f"MRR={r.get('mrr')}"]
        if "answer" in cfg:
            a = cfg["answer"]["aggregate"]
            parts += [f"outcome_ok={a.get('outcome_ok')}", f"lacunas={a.get('gap_recognized')}",
                      f"abst_indevida={a.get('improper_abstention')}", f"conflito={a.get('conflict_detected')}",
                      f"evidência={a.get('expected_evidence_hit')}",
                      f"citações={cfg['citations']['exactness']}",
                      f"exatas_falsas={len(cfg['citations']['false_verified_exact'])}"]
        lat = cfg["latency"]["search"]
        parts.append(f"busca p50/p95={lat.get('p50_ms')}/{lat.get('p95_ms')} ms")
        lines.append(f"{name:8} " + "  ".join(parts))
    return "\n".join(lines)


def _count_fragments(home: Path) -> int:
    import sqlite3
    conn = sqlite3.connect(f"file:{home / 'index.sqlite'}?mode=ro", uri=True)
    try:
        return conn.execute("SELECT count(*) FROM fragment").fetchone()[0]
    finally:
        conn.close()
