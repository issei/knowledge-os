"""Etapa B da revisão independente do golden set (docs/fase-1/plano-revisao-multiagente.md).

Junta as saídas cegas de P1, P2 e P3 sem nenhum agente no meio:

1. confere o formato de cada saída;
2. confere cada evidência citada contra o corpus (linha existe e contém o trecho);
3. compara a resposta cega de P2 com a resposta esperada do golden set;
4. junta os defeitos de P3 que têm prova conferida;
5. mede o vazamento lexical da pergunta para o trecho esperado;
6. sorteia 3 casos concordantes para o árbitro humano conferir.

Uso:
    python3 scripts/review/consolidate.py --golden bench/golden/c0.yaml \
        --corpus DIR --out-dir DIR [--p1 P1.yaml] --p2 P2.yaml --p3 P3.yaml
"""

import argparse
import json
import random
import re
import sys
import unicodedata
from pathlib import Path

import yaml

SEED = 20261022
SAMPLE_SIZE = 3
LEAK_MIN_WORDS = 3

# outcome do golden set -> tipos de P2 aceitos como a mesma leitura.
TYPE_MATCH = {
    "answered": {"resposta"},
    "answered_with_conflict": {"conflito"},
    "abstained": {"sem_resposta", "resposta_parcial"},
}
P2_TYPES = {"resposta", "conflito", "sem_resposta", "resposta_parcial"}
P3_VERDICTS = {"defeito", "sem_defeito"}
P3_SEVERITIES = {"alta", "media", "baixa"}
P1_CLASSES = {"lexical", "spec_fact", "code", "conflict", "no_answer"}
STOPWORDS = {
    "qual", "quais", "que", "por", "para", "com", "sem", "uma", "uns", "umas", "como", "onde",
    "quando", "quantos", "quantas", "isso", "esta", "este", "essa", "esse", "dos", "das", "nos",
    "nas", "pela", "pelo", "pode", "tem", "the", "and", "mais", "sua", "seu", "ser", "sao",
}


class InvalidOutput(Exception):
    pass


def fold(text):
    text = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in text if not unicodedata.combining(c))


def words(text):
    return {w for w in re.findall(r"[a-z0-9]+", fold(text)) if len(w) >= 3 and w not in STOPWORDS}


def squash(text):
    return re.sub(r"\s+", " ", text).strip()


def parse_lines(spec):
    m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", str(spec))
    if not m:
        raise InvalidOutput(f"linhas inválidas: {spec!r}")
    start = int(m.group(1))
    end = int(m.group(2) or start)
    if end < start:
        raise InvalidOutput(f"linhas invertidas: {spec!r}")
    return start, end


def check_evidence(corpus, ev):
    """Devolve (ok, motivo). ok = a linha existe e contém o trecho, ignorando espaços."""
    path = corpus / ev["caminho"]
    try:
        resolved = path.resolve()
        resolved.relative_to(corpus.resolve())
    except ValueError:
        return False, "caminho fora do corpus"
    if not resolved.is_file():
        return False, "arquivo não existe"
    start, end = parse_lines(ev["linhas"])
    lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
    if end > len(lines):
        return False, f"linha {end} não existe (arquivo tem {len(lines)})"
    window = squash(" ".join(lines[start - 1:end]))
    quote = squash(ev.get("trecho", ""))
    if not quote:
        return False, "trecho vazio"
    if quote in window:
        return True, ""
    return False, "trecho não está nessas linhas"


def overlaps(a, b):
    if a["caminho"] != b["caminho"]:
        return False
    a0, a1 = parse_lines(a["linhas"])
    b0, b1 = parse_lines(b["linhas"])
    return a0 <= b1 and b0 <= a1


def _require(obj, keys, where):
    missing = [k for k in keys if k not in obj]
    if missing:
        raise InvalidOutput(f"{where}: faltam {missing}")


def load_p2(path, ids):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("papel") != "P2":
        raise InvalidOutput("P2: papel ausente ou errado")
    cases = {}
    for c in data.get("casos") or []:
        _require(c, ["id", "tipo", "resposta", "evidencias", "confianca"], f"P2 {c.get('id')}")
        if c["tipo"] not in P2_TYPES:
            raise InvalidOutput(f"P2 {c['id']}: tipo {c['tipo']!r}")
        for ev in c["evidencias"] or []:
            _require(ev, ["caminho", "linhas", "trecho"], f"P2 {c['id']} evidência")
        cases[c["id"]] = c
    if set(cases) != ids:
        raise InvalidOutput(f"P2: casos diferentes do golden set: {sorted(set(cases) ^ ids)}")
    return cases


def load_p3(path, ids):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("papel") != "P3":
        raise InvalidOutput("P3: papel ausente ou errado")
    cases = {}
    for c in data.get("casos") or []:
        _require(c, ["id", "veredito", "defeitos"], f"P3 {c.get('id')}")
        if c["veredito"] not in P3_VERDICTS:
            raise InvalidOutput(f"P3 {c['id']}: veredito {c['veredito']!r}")
        for d in c["defeitos"] or []:
            _require(d, ["tipo", "gravidade", "descricao", "prova"], f"P3 {c['id']} defeito")
            if d["gravidade"] not in P3_SEVERITIES:
                raise InvalidOutput(f"P3 {c['id']}: gravidade {d['gravidade']!r}")
        cases[c["id"]] = c
    if set(cases) != ids:
        raise InvalidOutput(f"P3: casos diferentes do golden set: {sorted(set(cases) ^ ids)}")
    return cases


def load_p1(path):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("papel") != "P1":
        raise InvalidOutput("P1: papel ausente ou errado")
    out = []
    for q in data.get("perguntas") or []:
        _require(q, ["pergunta", "classe"], "P1 pergunta")
        if q["classe"] not in P1_CLASSES:
            raise InvalidOutput(f"P1: classe {q['classe']!r}")
        out.append(q)
    return out


def _check_p3_proof(corpus, golden_path, proof):
    """A prova pode vir do corpus ou do próprio golden set (defeito interno)."""
    if Path(proof.get("caminho", "")).name == Path(golden_path).name:
        text = squash(Path(golden_path).read_text(encoding="utf-8"))
        quote = squash(proof.get("trecho", ""))
        return (bool(quote) and quote in text), "prova no golden set"
    return check_evidence(corpus, proof)


def consolidate(golden_path, corpus, p2_path, p3_path, p1_path=None):
    golden = yaml.safe_load(Path(golden_path).read_text(encoding="utf-8"))
    gcases = {c["id"]: c for c in golden["casos"]}
    ids = set(gcases)
    p2 = load_p2(p2_path, ids)
    p3 = load_p3(p3_path, ids)
    p1 = load_p1(p1_path) if p1_path else []

    rows = []
    for cid, g in gcases.items():
        outcome = g["resultado_esperado"]["outcome"]
        expected = list(g.get("evidencia_esperada") or [])
        strong = [s for s in g.get("fontes_relevantes") or [] if s.get("relevancia") == 2]
        targets = expected + strong

        a = p2[cid]
        p2_checks = []
        for ev in a["evidencias"] or []:
            ok, why = check_evidence(corpus, ev)
            p2_checks.append({**ev, "verificada": ok, "motivo": why})
        verified = [e for e in p2_checks if e["verificada"]]
        type_ok = a["tipo"] in TYPE_MATCH[outcome]
        if targets:
            overlap = any(overlaps(e, t) for e in verified for t in targets)
        else:
            overlap = None  # caso sem evidência esperada: só o tipo conta.

        defects = []
        for d in p3[cid]["defeitos"] or []:
            ok, why = _check_p3_proof(corpus, golden_path, d["prova"])
            defects.append({**d, "prova_verificada": ok, "motivo": why})
        blocking = [d for d in defects if d["prova_verificada"] and d["gravidade"] == "alta"]

        reasons = []
        if not type_ok:
            reasons.append(f"tipo: golden={outcome}, P2={a['tipo']}")
        if overlap is False:
            reasons.append("evidência de P2 não cobre a evidência esperada")
        if any(not e["verificada"] for e in p2_checks):
            reasons.append("P2 citou evidência que não confere com o corpus")
        for d in blocking:
            reasons.append(f"P3 defeito alto ({d['tipo']})")

        leak = None
        if expected:
            qw = words(g["pergunta"])
            shared = sorted(qw & set().union(*(words(e.get("trecho", "")) for e in expected)))
            leak = {"palavras": shared, "vazamento": len(shared) >= LEAK_MIN_WORDS}

        rows.append({
            "id": cid,
            "classe": g["classe"],
            "pergunta": g["pergunta"],
            "outcome_esperado": outcome,
            "p2": {"tipo": a["tipo"], "resposta": a["resposta"], "confianca": a["confianca"],
                   "evidencias": p2_checks, "nota": a.get("nota")},
            "tipo_concorda": type_ok,
            "evidencia_concorda": overlap,
            "p3": {"veredito": p3[cid]["veredito"], "defeitos": defects},
            "vazamento_lexical": leak,
            "concordante": not reasons,
            "motivos_divergencia": reasons,
        })

    concordant = [r["id"] for r in rows if r["concordante"]]
    sample = sorted(random.Random(SEED).sample(concordant, min(SAMPLE_SIZE, len(concordant))))
    p3_confirmed = [r["id"] for r in rows if any(d["prova_verificada"] for d in r["p3"]["defeitos"])]
    summary = {
        "casos": len(rows),
        "concordantes": len(concordant),
        "divergentes": len(rows) - len(concordant),
        "concordancia_tipo": sum(r["tipo_concorda"] for r in rows),
        "concordancia_evidencia": sum(1 for r in rows if r["evidencia_concorda"]),
        "casos_com_evidencia_esperada": sum(1 for r in rows if r["evidencia_concorda"] is not None),
        "casos_com_defeito_p3_provado": len(p3_confirmed),
        "evidencias_p2_nao_conferidas": sum(1 for r in rows for e in r["p2"]["evidencias"] if not e["verificada"]),
        "vazamento_lexical": sum(1 for r in rows if r["vazamento_lexical"] and r["vazamento_lexical"]["vazamento"]),
        "amostra_para_o_arbitro": sample,
        "semente_da_amostra": SEED,
        "perguntas_p1": len(p1),
    }
    return {"schema": "kos.review.v1", "golden": str(golden_path), "revisao": golden.get("revisao"),
            "resumo": summary, "casos": rows, "perguntas_p1": p1}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--golden", required=True)
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--p1")
    ap.add_argument("--p2", required=True)
    ap.add_argument("--p3", required=True)
    ap.add_argument("--out", required=True, type=Path, help="arquivo JSON de saída")
    args = ap.parse_args(argv)
    try:
        report = consolidate(args.golden, args.corpus, args.p2, args.p3, args.p1)
    except InvalidOutput as exc:
        print(f"E_REVIEW_INVALID: {exc}", file=sys.stderr)
        return 2
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["resumo"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
