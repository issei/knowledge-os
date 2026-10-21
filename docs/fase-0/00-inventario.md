---
id: KOS-F0-INV
titulo: Fase 0A — Inventário e estado atual
status: rascunho para aprovação
data: 2026-10-21
revisao_inspecionada: issei/mauricio-site @ 73570bbc9b99e2a1e44d6844b9375bc4aa16e357 (branch main)
---

# Fase 0A — Inventário e estado atual

Convenção usada em todos os documentos desta pasta:

- **[FATO]** verificado nesta inspeção, com caminho e linha na revisão acima.
- **[INFERÊNCIA]** conclusão minha a partir de fatos; pode estar errada.
- **[ABERTO]** decisão ou informação que falta e precisa de Issei.

## 1. Escopo inspecionado

| Local | O que foi feito |
|---|---|
| `issei/mauricio-site` (clone em `main`, `73570bb`) | Busca textual por `knowledge os`, `knowledge-os`, `fts5`, `tree-sitter`, `docling`; leitura de `AGENTS.md`, `CLAUDE.md`, `docs/specs/**` relevantes, `package.json`, `scripts/`. |
| Pasta compartilhada do projeto (`/mnt/project-files/`) | Busca por `knowledge os` em `estudos/`, `planejamento-fde/`, `.notes/`. |
| Outros repositórios | Nenhum. A sessão só tem acesso a `issei/mauricio-site`. |

## 2. Resultado principal

1. **[FATO] Não existe implementação do Knowledge OS Enterprise** em nenhum local inspecionado. Não há código, esquema, CLI, parser, índice, teste nem benchmark com esse nome. Os termos `fts5`, `tree-sitter` e `docling` não aparecem em arquivos de texto versionados do repositório.
2. **[FATO] O Knowledge OS existe apenas como página pública de apresentação** no site pessoal:
   - `src/knowledge-os-presentation.html` (2.488 linhas) e a versão Markdown `public/knowledge-os-presentation.md` (36 linhas, "Publicado: 2026-05-07 · Atualizado: 2026-06-21").
   - Gêmeos gerados em inglês: `src/en/knowledge-os-presentation.html`, `public/en/knowledge-os-presentation.md`.
   - Citações em navegação/ecossistema: `specs/SPEC_ECOSYSTEM.md:48,86-88`, `specs/RESEARCH_MAPPING.md:39,77,132`, `ECOSYSTEM.md:32,71`, `scripts/seo/pages.mjs`, `scripts/i18n/i18n-manifest.json`, `src/js/eco-nav.js`.
3. **[FATO] A pasta compartilhada não contém material do Knowledge OS.** `planejamento-fde/PLANEJAMENTO-FDE.md:192` exclui explicitamente "cases de MCP, RAG, evals, guardrails" até haver "um case real com fluxo, contrato, falha, fallback e teste".
4. **[INFERÊNCIA]** "Repositório atual" na solicitação pode significar (a) o `mauricio-site` como corpus-piloto, ou (b) outro repositório ainda não conectado onde o Knowledge OS será construído. **[ABERTO] Q-01.** Esta especificação foi escrita para funcionar nos dois casos: o golden set usa o `mauricio-site` como **corpus-piloto C0** (evidências reais, verificadas), e os casos do corpus corporativo-alvo ficam registrados como lacuna.

## 3. Inventário de artefatos existentes relevantes

### 3.1 Arquitetura, requisitos e convenções

| Caminho | Tipo | Relevância para o Knowledge OS | Evidência |
|---|---|---|---|
| `AGENTS.md` (via `CLAUDE.md` → `@AGENTS.md`) | Convenções do repositório | Define SDD obrigatório, specs em `docs/specs/`, memória OKF em `knowledge/`, CodeGraph em `.codegraph/` | `AGENTS.md` seções "Spec-Driven Development", "CodeGraph", "Persistent Project Memory" |
| `docs/specs/ARCHITECTURE.md` | Arquitetura do site | Stack Vite 6 + Tailwind v4 (não é do Knowledge OS) | linhas 387-398 |
| `docs/specs/PAGE_SPEC_TEMPLATE.md` | Template SDD | Template de página web, não de sistema; não serve como template de spec de backend | arquivo inteiro |
| `docs/specs/000-INDEX.md` | Índice de specs do **LifeOS / Terminal Evolutivo** | Mostra uma convenção madura de árvore SDD (contratos `CTR-*`, ADRs, testes `TST-*`, backlog `BKL-*`), reaproveitável como **formato** | linhas 1-14 |
| `docs/specs/02-contracts/CTR-01..08` | Contratos do LifeOS | Formato de contrato existente | diretório |
| `docs/specs/13-testing/TST-01-plano-mestre.md`, `TST-02-matriz-rastreabilidade.md` | Plano de testes + rastreabilidade do LifeOS | Formato de matriz de rastreabilidade | diretório |
| `docs/specs/15-backlog/BKL-01-mvp.md` | Backlog do LifeOS | Formato de backlog | diretório |
| `knowledge/` (OKF v0.2) | Memória persistente do projeto | Já existe busca BM25 em memória via `okf search` (segundo `AGENTS.md`) | `AGENTS.md` seção OKF; `knowledge/index.md` |

### 3.2 ADRs existentes

| Caminho | Escopo | Relação com a arquitetura provisória |
|---|---|---|
| `docs/specs/14-adr/ADR-001-sem-build.md` | LifeOS (life3d_v2) | Sem conflito direto; escopo diferente. Usado no golden set como **fonte conflitante por escopo** com `package.json:30` (Vite). |
| `docs/specs/14-adr/ADR-002`, `ADR-003`, `RFC-004` | LifeOS | Sem relação. |
| `docs/decisions/ADR-eai-001`, `ADR-eai-002`, `ADR-te-001` | Páginas do site | Sem relação. Formato de ADR (Status/Data/Escopo/Contexto/Decisão/Consequências) adotado aqui. |
| `docs/specs/pages/apresentação/ADR-ap-001-namespace-e-excecao-dark-tech.md` | Página `apresentacao` | Sem relação; útil como caso de golden set. |

**[FATO]** Não existe nenhum ADR sobre o Knowledge OS. Os ADRs desta fase usam o prefixo `ADR-kos-NNN` para não colidir com `ADR-NNN` (LifeOS) nem `ADR-eai/te/ap-*`.

### 3.3 Testes e ferramentas existentes

| Item | Fato |
|---|---|
| Testes | 67 entradas em `tests/` (Playwright `*.spec.js` e Node `*.test.mjs`), todas do site. Nenhum teste de recuperação ou de citação. |
| Quality gate | `package.json:14` → `node scripts/quality-gate.mjs`. |
| CodeGraph | `AGENTS.md` afirma índice em `.codegraph/`; no clone, `.codegraph/` só tem `.gitignore` (índice é local, não versionado). O binário `codegraph` não está instalado neste ambiente. |
| OKF | `okf` não está instalado neste ambiente. |
| Ambiente | Python 3 com SQLite 3.45.1 e FTS5 disponível (verificado criando uma tabela FTS5 em memória); Node 22. Nada foi instalado. |

## 4. Decisões existentes que conflitam com a arquitetura provisória

A arquitetura provisória exclui embeddings, bancos vetoriais, grafos e orquestração multiagente do núcleo. A página pública afirma o contrário. **Nada foi alterado**; a divergência fica registrada aqui e em `ADR-kos-008`.

| ID | Fonte existente | O que afirma | Conflito com | Tratamento proposto |
|---|---|---|---|---|
| DIV-01 | `src/knowledge-os-presentation.html:1068` | Recuperação "Hybrid retrieval: vector + BM25 + graph traversal" | ADR-kos-002, ADR-kos-008 | Página descreve a **visão-alvo**; o MVP entrega só BM25/FTS5. **[ABERTO] Q-03**: atualizar a página ou rotulá-la como visão. |
| DIV-02 | `src/knowledge-os-presentation.html:1138` | "GraphRAG Híbrido + Retrieval Semântico via vector + BM25 + graph traversal" | ADR-kos-008 | Idem DIV-01. |
| DIV-03 | `src/knowledge-os-presentation.html:1151` | "Knowledge Graph + Ontologia via JSON-LD / SHACL" | ADR-kos-008 | Fora do núcleo; reavaliar após linha de base. |
| DIV-04 | `src/knowledge-os-presentation.html:1112` | "Agentes Cognitivos & Workflows via LangGraph / Mastra / CrewAI" | Exclusão de orquestração multiagente | Fora do núcleo. |
| DIV-05 | `public/knowledge-os-presentation.md` ("Em síntese", FAQ) | Define o produto como GraphRAG sobre Knowledge Graph | ADR-kos-008 | Idem DIV-01. |
| DIV-06 | `src/knowledge-os-presentation.html:1015` | SLO "P95 retrieval < 800ms; freshness < 24h" | Regra "não inventar metas sem justificativa" | Tratar como **meta declarada sem medição**; o benchmark mede antes de adotar (ver `04-benchmark.md` §6). |
| DIV-07 | `src/knowledge-os-presentation.html:2210` | Critério de saída "Recall@10 > 0.75 em benchmark interno" | Idem | Não existe benchmark interno nem medição. Mantido como hipótese, não como limiar. |
| DIV-08 | `src/knowledge-os-presentation.html:690,1014` vs `:2109` | "18 KPIs cognitivos … 4 camadas" vs "22 KPIs cognitivos em 5 camadas" | Inconsistência interna da própria fonte | Usado como caso de golden set (fonte conflitante). Não corrigido. |
| DIV-09 | `planejamento-fde/PLANEJAMENTO-FDE.md:192` (pasta do projeto) | RAG/evals fora do plano FDE até haver case real | Publicação de um case Knowledge OS no site | **[INFERÊNCIA]** O MVP pode ser exatamente o "case real" exigido; publicação no site continua bloqueada pela regra do plano até haver fluxo, contrato, falha, fallback e teste. |

## 5. Afirmações de documentação que não se confirmaram

| Afirmação | Onde | Verificação |
|---|---|---|
| "the 36 `src/*.html` pages" | `AGENTS.md:64` | `git ls-files 'src/*.html'` sem `src/en/` → **46** arquivos em `73570bb`. Documento desatualizado. |
| Índice CodeGraph em `.codegraph/` | `AGENTS.md`, seção CodeGraph | Só `.codegraph/.gitignore` existe no clone (esperado: índice é local). |
| `.agents/` é "YOUR HOME" com skills | `AGENTS.md`, mapa de diretórios | Existe `.agents/skills`; as skills citadas como obrigatórias estão em `.claude/skills/`. |

## 6. Características do corpus-piloto C0 que afetam o design

| Fato | Impacto |
|---|---|
| 907 arquivos versionados; 402 `.md`, 144 `.js`, 104 `.mjs`, 85 `.html`, 26 `.json`, 9 `.yaml`, 9 `.py`, 38 `.png` | Parsers nativos cobrem a maior parte. HTML não está na lista de parsers da arquitetura provisória: **[ABERTO] Q-05**. |
| 14 caminhos aparecem entre aspas em `git ls-files` (padrão `core.quotepath`), ex.: `docs/specs/pages/apresentação/…` | A descoberta precisa usar `git ls-files -z` e tratar caminho como bytes/UTF-8 NFC. |
| Arquivos gerados versionados (`src/en/**`, `public/en/**`, blocos `PF:*`/`CV:*`) | Precisam de classificação "derivado" para não competir com a fonte (`AGENTS.md`, seção i18n). |
| 0 symlinks, 0 submódulos, 0 arquivos LFS | Casos tratados no contrato, mas sem exemplo real em C0. |
| `.git` com 24 MB | Volume pequeno; latência de C0 não representa um corpus corporativo. |

## 7. Estado atual da implementação

**Estágio: zero.** Não há código. A Fase 1 parte do backlog em `08-backlog.md`. Nenhum arquivo existente foi alterado nesta fase.
