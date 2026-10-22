"""Resposta fundamentada, modo extrativo, com conflitos e abstenção (BL-13; CTR-08, CTR-09).

Fluxo de `ask`:

1. Grava o `query_event` (CTR-08 inv. 5) antes de tudo.
2. Busca (CTR-06) e cita (CTR-07) os resultados; só citação `verified_*` sustenta afirmação (inv. 1).
3. Divide a pergunta em partes (`split_parts`) e decide, por parte, se há evidência.
   Regras de abstenção, todas declaradas e provisórias até a calibração (BL-18):
   - `revision_unavailable`: a revisão pedida não está indexada;
   - `no_hits`: a busca não trouxe nada;
   - `unverifiable_evidence`: nenhuma citação passou na verificação;
   - `insufficient_evidence`: algum termo essencial da parte não ocorre em nenhum
     fragmento da revisão (o corpus não fala daquilo) ou, se `min_term_coverage`
     estiver ligado, a cobertura dos termos pelos trechos recuperados fica abaixo dele.
   Uma pergunta com parte sustentada e parte não é respondida em parte, e a parte
   sem suporte vem em `gaps` (CTR-09 inv. 4).
4. Afirmações extrativas (inv. 2): um trecho por artefato, na ordem do rank; a linha
   do fragmento que mais cobre os termos vira o trecho, citado por sub-intervalo.
   HTML não tem sub-intervalo literal, então cita o fragmento inteiro.
5. Conflito (inv. 4), regra simples: o mesmo termo essencial aparece com números
   diferentes (`18 KPIs` × `22 KPIs`) nos trechos verificados. Nenhum lado é escolhido.

O modo `llm` exige o adaptador do BL-21; até lá devolve `E_LLM_DISABLED` (inv. 6).
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from kos import audit
from kos.cite import Citation, cite
from kos.discovery import media_type_for
from kos.errors import KosError
from kos.parsing import registry
from kos.search import SearchResult, search

ABSTENTION_CODES = ("no_hits", "insufficient_evidence", "unverifiable_evidence", "revision_unavailable",
                    "out_of_scope", "llm_unsupported_output")
VERIFIED = ("verified_exact", "verified_normalized")
MODES = ("extractive", "llm")

# Palavras sem conteúdo próprio numa pergunta (PT-BR e inglês), já sem acento.
STOPWORDS = frozenset("""
a o as os um uma uns umas e ou de da do das dos em no na nos nas por para pra com sem que qual quais
quanto quantos quantas onde quando como quem porque se e ser sao foi esta esse essa este isso isto ao aos
mais menos seu sua seus suas lhe me te ja nao sim the of and or is are to in on for what which how where
when who why does do did an at by it be was
""".split())
_WORD = re.compile(r"\w+", re.UNICODE)
_PART_BREAK = re.compile(
    r"[?;]+|\s+e\s+(?=(?:qual|quais|quanto|quantos|quantas|onde|quando|como|quem|por\s+que|o\s+que)\b)",
    re.IGNORECASE)
_NUMBER_TERM = re.compile(r"(\d+(?:[.,]\d+)?)\s+(\w+)")


@dataclass(frozen=True)
class Thresholds:
    """Limiares de CTR-09. Provisórios: valores só mudam pela calibração do BL-18."""
    min_hits: int = 1
    min_verified_citations: int = 1
    require_terms_in_corpus: bool = True
    min_term_coverage: float | None = None  # desligado na linha de base

    def to_json(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Claim:
    claim_id: str
    text: str
    citation_nos: list[int]


@dataclass
class Answer:
    query_id: str
    outcome: str
    mode: str
    revisions: list[dict]
    claims: list[Claim] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    gaps: list[dict] = field(default_factory=list)
    abstention: dict | None = None
    removed_claims: list[dict] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "query_id": self.query_id, "outcome": self.outcome, "mode": self.mode, "revisions": self.revisions,
            "claims": [c.__dict__ for c in self.claims], "citations": [c.to_json() for c in self.citations],
            "conflicts": self.conflicts, "gaps": self.gaps, "abstention": self.abstention,
            "removed_claims": self.removed_claims,
        }


def fold(text: str) -> str:
    """Minúsculas sem acento, como o tokenizador do FTS compara."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


def essential_terms(text: str) -> list[str]:
    return [t for t in dict.fromkeys(_WORD.findall(fold(text))) if t not in STOPWORDS]


def split_parts(question: str) -> list[str]:
    """Partes de uma pergunta composta: separa em `?`, `;` e em "e" seguido de interrogativo."""
    parts = [p.strip(" ,.") for p in _PART_BREAK.split(question)]
    parts = [p for p in parts if p and essential_terms(p)]
    return parts or [question]


def ask(home: Path, question: str, *, mode: str = "extractive", repo: str | None = None,
        commit: str | None = None, k: int = 10, thresholds: Thresholds = Thresholds(),
        repos: dict[str, Path] | None = None, interface: str = "cli", max_claims: int = 5) -> Answer:
    home = Path(home)
    params = {"command": "ask", "mode": mode, "k": k, "thresholds": thresholds.to_json(),
              **{n: v for n, v in (("repo", repo), ("commit", commit)) if v is not None}}
    query_id = audit.start_query(home, interface=interface, question=question, params=params)
    if mode not in MODES:
        raise KosError("E_FILTER_INVALID", f"modo desconhecido: {mode}")
    if mode == "llm":
        audit.record_answer(home, query_id, outcome="error", mode="llm")
        raise KosError("E_LLM_DISABLED", "o adaptador de LLM está desligado; use --mode extractive")

    try:
        result = search(home, question, repo=repo, commit=commit, k=k)
    except KosError as err:
        if err.code not in ("E_REVISION_NOT_INDEXED", "E_NO_INDEXED_REVISION"):
            audit.record_answer(home, query_id, outcome="error", mode=mode)
            raise
        return _abstain(home, query_id, mode, [], "revision_unavailable", err.message, question, None, [])
    audit.record_retrieval(home, query_id, result)
    revisions = result.revisions

    if len(result.results) < thresholds.min_hits:
        return _abstain(home, query_id, mode, revisions, "no_hits",
                        "a busca não encontrou nenhum fragmento", question, result, [])
    citations = cite(home, [h.fragment_key for h in result.results],
                     commit=None if len(revisions) > 1 else revisions[0]["commit_oid"], repos=repos)
    verified = [(h, c) for h, c in zip(result.results, citations) if c.verification in VERIFIED]
    if len(verified) < thresholds.min_verified_citations:
        return _abstain(home, query_id, mode, revisions, "unverifiable_evidence",
                        "nenhuma citação passou na verificação contra o Git", question, result, citations)

    supported, gaps = [], []
    for part in split_parts(question):
        missing = _missing_terms(home, part, verified, revisions, repo, thresholds)
        (gaps if missing else supported).append({"part": part, "missing_terms": missing})
    if not supported:
        missing = sorted({t for g in gaps for t in g["missing_terms"]})
        return _abstain(home, query_id, mode, revisions, "insufficient_evidence",
                        "sem evidência para: " + ", ".join(missing), question, result,
                        [c for _, c in verified])

    terms = [t for s in supported for t in essential_terms(s["part"])]
    answer = Answer(query_id, "answered", mode, revisions, gaps=gaps)
    _extract_claims(home, answer, verified, terms, repos, max_claims)
    answer.conflicts = _conflicts(answer, verified, terms)
    if answer.conflicts:
        answer.outcome = "answered_with_conflict"
    _enforce_support(answer)
    if not answer.claims:
        return _abstain(home, query_id, mode, revisions, "unverifiable_evidence",
                        "nenhuma afirmação ficou com citação verificada", question, result, citations)
    audit.record_answer(home, query_id, outcome=answer.outcome, mode=mode,
                        answer_text=json.dumps(answer.to_json(), ensure_ascii=False))
    audit.record_citations(home, query_id, answer.citations,
                           claim_ids=_claims_by_citation(answer))
    return answer


def _missing_terms(home, part, verified, revisions, repo, thresholds) -> list[str]:
    terms = essential_terms(part)
    missing = []
    if thresholds.require_terms_in_corpus:
        commit = revisions[0]["commit_oid"] if len(revisions) == 1 else None
        for term in terms:
            if search(home, term, repo=repo, commit=commit, k=1).diagnostics["total_hits"] == 0:
                missing.append(term)
    if thresholds.min_term_coverage is not None:
        seen = set()
        for _, c in verified:
            seen |= set(_WORD.findall(fold(c.quoted_text + " " + c.path_text)))
        uncovered = [t for t in terms if t not in seen]
        if terms and 1 - len(uncovered) / len(terms) < thresholds.min_term_coverage:
            missing += [t for t in uncovered if t not in missing]
    return missing


def _best_line(text: str, terms: list[str]) -> int | None:
    """Índice (0-based) da linha do trecho que mais cobre os termos; None se nenhuma cobre."""
    best, best_score = None, 0
    wanted = set(terms)
    for i, line in enumerate(text.split("\n")):
        score = len(wanted & set(_WORD.findall(fold(line))))
        if score > best_score:
            best, best_score = i, score
    return best


def _extract_claims(home, answer: Answer, verified, terms, repos, max_claims) -> None:
    seen_paths = set()
    for hit, citation in verified:
        if len(answer.claims) >= max_claims:
            break
        if (citation.repo_name, citation.path_text) in seen_paths:
            continue
        line = _best_line(citation.quoted_text, terms)
        if line is None:
            continue
        seen_paths.add((citation.repo_name, citation.path_text))
        chosen = citation
        if (media_type_for(citation.path_text) not in registry.VISIBLE_TEXT_MEDIA_TYPES
                and citation.locator.start_line is not None):
            n = citation.locator.start_line + line
            [chosen] = cite(home, [citation.fragment_key], commit=citation.commit_oid, repos=repos, lines=(n, n))
            if chosen.verification not in VERIFIED:
                chosen = citation
        _add(answer, chosen, text=chosen.quoted_text)


def _add(answer: Answer, citation: Citation, *, text: str | None) -> int:
    for existing in answer.citations:
        if (existing.fragment_key, existing.locator) == (citation.fragment_key, citation.locator):
            no = existing.citation_no
            break
    else:
        no = len(answer.citations) + 1
        citation.citation_no = no
        answer.citations.append(citation)
    if text is not None:
        answer.claims.append(Claim(f"c{len(answer.claims) + 1}", text, [no]))
    return no


def _conflicts(answer: Answer, verified, terms) -> list[dict]:
    """Mesmo termo essencial com números diferentes em trechos verificados."""
    wanted = set(terms)
    by_term: dict[str, dict[str, list]] = {}
    for _, c in verified:
        for number, word in _NUMBER_TERM.findall(fold(c.quoted_text)):
            if word in wanted:
                by_term.setdefault(word, {}).setdefault(number.replace(",", "."), []).append(c)
    conflicts = []
    for term, values in sorted(by_term.items()):
        if len(values) < 2:
            continue
        sides = []
        for value, cites in sorted(values.items(), key=lambda kv: float(kv[0])):
            nos = sorted({_add(answer, c, text=None) for c in cites})
            claim = Claim(f"c{len(answer.claims) + 1}", f"{value} {term}", nos)
            answer.claims.append(claim)
            sides.append({"value": value, "claim_id": claim.claim_id, "citation_nos": nos,
                          "scope": [{"path": answer.citations[n - 1].path_text,
                                     "commit_oid": answer.citations[n - 1].commit_oid} for n in nos]})
        conflicts.append({"topic": term, "sides": sides})
    return conflicts


def _enforce_support(answer: Answer) -> None:
    """CTR-08 inv. 1: afirmação sem citação verificada sai, e a saída fica registrada."""
    kept = []
    for claim in answer.claims:
        if any(answer.citations[n - 1].verification in VERIFIED for n in claim.citation_nos):
            kept.append(claim)
        else:
            answer.removed_claims.append({"claim_id": claim.claim_id, "reason": "sem citação verificada"})
    answer.claims = kept


def _claims_by_citation(answer: Answer) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for claim in answer.claims:
        for n in claim.citation_nos:
            out.setdefault(n, []).append(claim.claim_id)
    return out


def _abstain(home, query_id, mode, revisions, code, message, question, result: SearchResult | None,
             nearest: list[Citation]) -> Answer:
    near = nearest[:3]
    for i, c in enumerate(near, start=1):
        c.citation_no = i
    abstention = {
        "code": code, "message": message,
        "searched": {"revisions": revisions, "query_parsed": result.diagnostics["parsed_query"] if result else None,
                     "total_hits": result.diagnostics["total_hits"] if result else 0},
        "nearest_label": "relacionadas, não respondem",
    }
    answer = Answer(query_id, "abstained", mode, revisions, citations=near, abstention=abstention)
    audit.record_answer(home, query_id, outcome="abstained", mode=mode, abstention_code=code,
                        answer_text=json.dumps(answer.to_json(), ensure_ascii=False))
    audit.record_citations(home, query_id, near)
    return answer
