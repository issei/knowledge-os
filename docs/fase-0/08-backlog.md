---
id: KOS-F0-BKL
titulo: Fase 0F — Backlog ordenado por dependências
status: rascunho para aprovação
data: 2026-10-21
---

# Fase 0F — Backlog

Ordem = dependências. **BL-01 a BL-14, mais BL-22 (HTML), formam o caminho vertical mínimo** (ingestão → indexação → recuperação → citação verificável → avaliação). Itens depois de BL-14 só começam com B0 medido.

Decisões de 2026-10-21: Python (Q-02), repositório `issei/knowledge-os` (Q-19), corpus `issei/mauricio-site` (Q-01) e HTML no MVP (Q-05). Pacote Python `kos`, com pastas `kos/{discovery,parsing,store,search,cite,answer,audit,bench,cli}` e `tests/{unit,contract,property,e2e}`, `bench/golden/`.

| ID | Objetivo | Especificações | Módulos candidatos | Testes | Critérios de aceitação | Depende de | Riscos |
|---|---|---|---|---|---|---|---|
| BL-00 | Aprovar ADR-kos-001..008 (Q-01, Q-02, Q-05 e Q-19 já respondidas) | `05-adrs.md`, `09-consistencia.md` §3 | — | — | ADRs com status Aceito ou alterados; respostas registradas | — | RSK-01, RSK-12, RSK-13 |
| BL-01 | Esqueleto do projeto, `kos init` cria `index.sqlite` e `audit.sqlite` com o DDL | `02-modelo-de-dados.md` §4-5, ADR-kos-005 | `kos/store/schema`, `kos/cli` | Unidade: DDL aplica; `PRAGMA foreign_key_check` vazio; TC-CLI-01 (init) | `kos init` idempotente; `index_meta.schema_version` gravado | BL-00 | — |
| BL-02 | Construtor de repositórios-fixture determinístico | `06-plano-de-testes.md` §2 | `tests/fixtures/gitbuilder` | Unidade: mesmo roteiro → mesmos commit OIDs | Suporta arquivos, commits, `git mv`, symlink, submódulo, LFS fake, nome não UTF-8, CRLF | BL-00 | — |
| BL-03 | Política de elegibilidade versionada e descoberta | CTR-01 | `kos/discovery` | TC-DSC-01..07 | Saída determinística; nenhum arquivo some sem regra | BL-01, BL-02 | RSK-11 |
| BL-04 | Perfis de processamento e fingerprint; `fragment_key` | `02-modelo-de-dados.md` §1, CTR-02 inv. 1 | `kos/parsing/profile` | Unidade de fingerprint; TC-PRS-08 | Mudar qualquer campo do perfil muda o fingerprint | BL-01 | — |
| BL-05 | Normalizador único e parser Markdown com offsets | CTR-02, ADR-kos-003 | `kos/parsing/normalize`, `kos/parsing/markdown` | TC-PRS-01, 02, 03, 06 | 100% dos fragmentos de C0 `.md` verificáveis por bytes | BL-04 | RSK-04, RSK-05 |
| BL-06 | Parsers JSON, YAML e texto com offsets e `struct_path` | CTR-02 | `kos/parsing/{json,yaml,text}` | TC-PRS-01, 04 | Idem para `.json`/`.yaml`/`.txt` de C0 | BL-04 | RSK-04 |
| BL-07 | Perfil "código como texto" provisório (janelas por bloco), até BL-15 | CTR-02 | `kos/parsing/text` | TC-PRS-01 | Arquivos `.js/.mjs/.py` indexados e citáveis por linhas | BL-06 | — |
| BL-08 | Ingestão `full`: manifesto, versões, fragmentos, localizadores, FTS, `ingest_run`, erros | CTR-03 (modo full), CTR-10 | `kos/ingest`, `kos/store` | TC-INC-03, TC-RET-06, TC-AUD-03 | `kos ingest mauricio-site --rev 73570bb --full` conclui `succeeded` ou `partial` com erros explicados | BL-03, BL-05..07, BL-22 | — |
| BL-09 | `kos rebuild` com troca atômica e determinismo | CTR-05, ADR-kos-001 | `kos/rebuild` | TC-REB-01..03, TC-AUD-02 | Dois rebuilds → dump lógico idêntico | BL-08 | RSK-10 |
| BL-10 | `kos search` com filtro por revisão, escape de consulta, pesos de coluna | CTR-06, ADR-kos-002 | `kos/search` | TC-RET-01..05 | GS-LEX-001 e GS-SPEC-001 com a fonte essencial no top-10 (verificação funcional, não meta de métrica) | BL-08 | RSK-03 |
| BL-11 | `kos cite` com releitura do blob e estado de verificação | CTR-07, ADR-kos-004 | `kos/cite` | TC-CIT-01..03, 05, 06; TC-CLI-03 | Zero `verified_exact` falsos em C0 | BL-10 | RSK-05 |
| BL-12 | `audit.sqlite`: registro de consultas, resultados e citações | CTR-10 | `kos/audit` | TC-AUD-01, 04, 05 | Toda consulta tem `query_event`; citação auditada reconferível sem índice | BL-11 | — |
| BL-13 | `kos ask --mode extractive` com conflitos e abstenção por regras simples | CTR-08 (extrativo), CTR-09 | `kos/answer` | TC-ANS-01, 04; TC-ABS-01, 03, 04, 05 | GS-ABS-001 abstém; GS-CONF-001 retorna `answered_with_conflict` ou o desvio fica registrado na análise de erros de B0 | BL-11, BL-12 | RSK-06 |
| BL-14 | Runner do benchmark, golden set C0 em arquivo, auto-verificação, relatório B0, B0-grep e B0-path | `04-benchmark.md` | `kos/bench`, `bench/golden/c0.yaml` | TC-BEN-01..04 | Relatório B0 arquivado com fingerprint, versões e hardware; análise de erros por caso | BL-10, BL-11, BL-13 | RSK-07 |
| — | **Fim do caminho vertical mínimo.** Revisão com Issei: B0, análise de erros e próximos itens | | | | | | |
| BL-15 | Tree-sitter para JS (`.js/.mjs/.cjs`) e Python: símbolos e fragmentos por símbolo | CTR-02, ADR-kos-003 | `kos/parsing/code` | TC-PRS-05; GS-CODE-* | `symbol` preenchido; GS-CODE-002 encontra `pfBlock`/`fill`; comparação com BL-07 no benchmark | BL-14 | RSK-04 |
| BL-16 | Ingestão incremental | CTR-03 | `kos/ingest` | TC-INC-01, 02, 04, 05 | `incremental ≡ full` (propriedade) | BL-08, BL-09 | — |
| BL-17 | Remoção, renomeação inferida e `gc` | CTR-04 | `kos/ingest`, `kos/gc` | TC-UPD-01..05 | Remoções somem da revisão-alvo; `gc` não apaga versão referenciada | BL-16 | — |
| BL-18 | Calibração dos limiares de abstenção | CTR-09, `04-benchmark.md` §6.3 | `kos/answer/thresholds`, `kos/bench` | TC-ABS-02; curva no relatório | Limiar escolhido pela regra aprovada (Q-15) e registrado com fingerprint | BL-14, crescimento do golden set (Q-14) | RSK-06, RSK-07 |
| BL-19 | Expansão do golden set no `mauricio-site` e segundo anotador | `04-benchmark.md` §4, §6.4 | `bench/golden/c0.yaml` | TC-BEN-01, 02 | Casos por classe com concordância registrada | BL-14 | RSK-01 |
| BL-20 | Servidor MCP de leitura | ADR-kos-006 | `kos/mcp` | TC-MCP-01..03 | Só 3 ferramentas; tudo auditado | BL-13 | RSK-08, RSK-09 |
| BL-21 | Adaptador de LLM desligado por padrão + validador de referências | ADR-kos-007, CTR-08 | `kos/answer/llm` | TC-ANS-02, 03, 05; TC-SEC-01 | Nenhuma rede sem opt-in; afirmações sem suporte removidas | BL-13, Q-18 | RSK-08 |
| BL-22 | Parser HTML (Q-05 = sim; **faz parte do caminho vertical**, antes de BL-08) | ADR-kos-003 | `kos/parsing/html` | TC-PRS-01 para HTML; GS-SPEC-003, GS-CONF-002 | Texto visível com offsets; páginas `src/en/**` como `generated` | BL-04, BL-06 | RSK-11 |
| BL-23 | Perfil Docling (se Q-13 definir corpus de PDF/DOCX) | ADR-kos-003 | `kos/parsing/docling` | TC-PRS-07, TC-CIT-04; GS-DOC-* | Citações com página e `verified_normalized` | BL-14, Q-13 | RSK-14 |
