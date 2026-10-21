---
id: KOS-F0-BEN
titulo: Fase 0D — Benchmark próprio e golden set inicial
status: rascunho para aprovação
data: 2026-10-21
requisitos: [REQ-06, REQ-07, REQ-08, REQ-09, REQ-10, REQ-11, REQ-15, RNF-04]
corpus_piloto: C0 = issei/mauricio-site @ 73570bbc9b99e2a1e44d6844b9375bc4aa16e357
---

# Fase 0D — Benchmark próprio

## 1. Corpus

| Corpus | Situação | Uso |
|---|---|---|
| **C0** `issei/mauricio-site` @ `73570bbc9b99e2a1e44d6844b9375bc4aa16e357` | Disponível. Tem specs, ADRs, contratos, código JS/MJS, testes, JSON/YAML e uma fonte com contradição interna. | Golden set inicial (§3). Todas as evidências abaixo foram conferidas nesta inspeção, com linha. |
| **C1** corpus corporativo-alvo do Knowledge OS Enterprise | **Desconhecido** ([ABERTO] Q-01). | Casos GS-ENT-* ficam como lacuna (§4). Nada foi inventado. |

C0 é **representativo de forma**, não de escala nem de domínio: 907 arquivos, sem PDF/DOCX versionado, poucas linguagens. Resultados em C0 não autorizam metas para C1.

## 2. Esquema de um caso

```yaml
id: GS-<CLASSE>-<NNN>          # estável; nunca reutilizado
classe: lexical | spec_fact | code | conflict | no_answer
pergunta: "<texto em PT-BR>"
revisao_esperada: <commit_oid completo>
fontes_relevantes:              # julgamento de relevância (graded): 2 = essencial, 1 = útil
  - { caminho: <path>, linhas: "<a-b>", relevancia: 2 }
evidencia_esperada:             # trecho literal que precisa aparecer em alguma citação
  - { caminho: <path>, linhas: "<a-b>", trecho: "<literal>" }
resultado_esperado:
  outcome: answered | answered_with_conflict | abstained
  abstention_codes_aceitos: [ ... ]   # só quando abstained
  afirmacoes_obrigatorias: [ "<fato mínimo>" ]
  afirmacoes_proibidas: [ "<erro que reprova>" ]
criterios: [ ... ]              # quais métricas do §5 se aplicam
```

Regra de manutenção: casos são ancorados numa revisão. Ao trocar a revisão do benchmark, cada caso é reconferido e o histórico de mudança fica no próprio arquivo (TC-BEN-02).

## 3. Golden set inicial (C0)

Todas as linhas abaixo foram lidas nesta inspeção em `73570bb`.

```yaml
- id: GS-LEX-001
  classe: lexical
  pergunta: "Qual comando roda o quality gate do site?"
  revisao_esperada: 73570bbc9b99e2a1e44d6844b9375bc4aa16e357
  fontes_relevantes:
    - { caminho: package.json, linhas: "14", relevancia: 2 }
    - { caminho: AGENTS.md, linhas: "39", relevancia: 1 }   # "npm run gate já cobra…"
  evidencia_esperada:
    - { caminho: package.json, linhas: "14", trecho: "\"gate\": \"node scripts/quality-gate.mjs\"" }
  resultado_esperado:
    outcome: answered
    afirmacoes_obrigatorias: ["npm run gate", "scripts/quality-gate.mjs"]
  criterios: [recall@k, mrr, citacao_exata, cobertura_afirmacoes]

- id: GS-LEX-002
  classe: lexical
  pergunta: "Qual ferramenta faz a tradução do gêmeo em inglês do site?"
  revisao_esperada: 73570bbc9b99e2a1e44d6844b9375bc4aa16e357
  fontes_relevantes:
    - { caminho: AGENTS.md, linhas: "35-36", relevancia: 2 }
    - { caminho: scripts/i18n/README.md, linhas: "4-5", relevancia: 2 }
  evidencia_esperada:
    - { caminho: AGENTS.md, linhas: "35", trecho: "A tradução é **local** (Argos Translate, `scripts/i18n/`)" }
  resultado_esperado:
    outcome: answered
    afirmacoes_obrigatorias: ["Argos Translate", "local"]
    afirmacoes_proibidas: ["usa um LLM para traduzir"]
  criterios: [recall@k, precision@k, citacao_exata, cobertura_afirmacoes]

- id: GS-SPEC-001
  classe: spec_fact
  pergunta: "Qual é o piso de contraste da Camada 3 da página apresentacao?"
  revisao_esperada: 73570bbc9b99e2a1e44d6844b9375bc4aa16e357
  fontes_relevantes:
    - { caminho: AGENTS.md, linhas: "121", relevancia: 2 }
    - { caminho: "docs/specs/pages/apresentação/ADR-ap-001-namespace-e-excecao-dark-tech.md", linhas: "25-28", relevancia: 1 }
    - { caminho: tests/apresentacao.tokens.test.mjs, linhas: "39", relevancia: 1 }
  evidencia_esperada:
    - { caminho: AGENTS.md, linhas: "121", trecho: "e um piso de contraste de **7:1** na Camada 3." }
  resultado_esperado:
    outcome: answered
    afirmacoes_obrigatorias: ["7:1"]
    afirmacoes_proibidas: ["4.5:1 como piso da Camada 3"]
  criterios: [recall@k, mrr, citacao_exata, cobertura_afirmacoes]
  nota: "Caminho com 'ç' e 'ã' exercita CTR-01 (TC-DSC-04)."

- id: GS-SPEC-002
  classe: spec_fact
  pergunta: "Por que os fluxos da página engenharia-agentes-ia não usam bpmn-js, e quando isso pode mudar?"
  revisao_esperada: 73570bbc9b99e2a1e44d6844b9375bc4aa16e357
  fontes_relevantes:
    - { caminho: docs/decisions/ADR-eai-002-fluxos-em-svg-sem-bpmnjs.md, linhas: "9-22", relevancia: 2 }
  evidencia_esperada:
    - { caminho: docs/decisions/ADR-eai-002-fluxos-em-svg-sem-bpmnjs.md, linhas: "15", trecho: "No MVP/V1, renderizar os fluxos com **SVG/CSS próprios** (sem `bpmn-js`):" }
    - { caminho: docs/decisions/ADR-eai-002-fluxos-em-svg-sem-bpmnjs.md, linhas: "21-22", trecho: "`bpmn-js` **editável** fica **diferido para a V2** (WU-13)" }
  resultado_esperado:
    outcome: answered
    afirmacoes_obrigatorias: ["dependência pesada / bundle", "diferido para a V2 com novo ADR"]
  criterios: [recall@k, citacao_exata, cobertura_afirmacoes]

- id: GS-SPEC-003
  classe: spec_fact
  pergunta: "Qual SLO de latência de recuperação a página do Knowledge OS declara?"
  revisao_esperada: 73570bbc9b99e2a1e44d6844b9375bc4aa16e357
  fontes_relevantes:
    - { caminho: src/knowledge-os-presentation.html, linhas: "1015", relevancia: 2 }
    - { caminho: src/knowledge-os-presentation.html, linhas: "1991", relevancia: 1 }
  evidencia_esperada:
    - { caminho: src/knowledge-os-presentation.html, linhas: "1015", trecho: "SLOs por domínio: P95 retrieval &lt; 800ms; freshness &lt; 24h." }
  resultado_esperado:
    outcome: answered
    afirmacoes_obrigatorias: ["P95 < 800 ms é uma meta declarada na página"]
    afirmacoes_proibidas: ["o sistema atinge P95 < 800 ms"]
  criterios: [recall@k, citacao_exata, cobertura_afirmacoes, taxa_sem_suporte]
  nota: "Depende de Q-05 (HTML como formato). Se HTML ficar fora, o caso migra para no_answer com código out_of_scope."

- id: GS-CODE-001
  classe: code
  pergunta: "O que acontece quando um hexadecimal é escrito em src/apresentacao.html?"
  revisao_esperada: 73570bbc9b99e2a1e44d6844b9375bc4aa16e357
  fontes_relevantes:
    - { caminho: scripts/guard-ap-tokens.mjs, linhas: "2-10", relevancia: 2 }
    - { caminho: scripts/guard-ap-tokens.mjs, linhas: "50-59", relevancia: 2 }
    - { caminho: AGENTS.md, linhas: "124-125", relevancia: 1 }
  evidencia_esperada:
    - { caminho: scripts/guard-ap-tokens.mjs, linhas: "58", trecho: "process.exit(2);" }
  resultado_esperado:
    outcome: answered
    afirmacoes_obrigatorias: ["hook PostToolUse bloqueia (saída 2)", "cores só em src/apresentacao.css"]
  criterios: [recall@k, mrr, citacao_exata, cobertura_afirmacoes]

- id: GS-CODE-002
  classe: code
  pergunta: "Onde é montado o bloco PF:START da home e qual função o grava no HTML?"
  revisao_esperada: 73570bbc9b99e2a1e44d6844b9375bc4aa16e357
  fontes_relevantes:
    - { caminho: scripts/gen-portfolio.mjs, linhas: "386-402", relevancia: 2, simbolo: pfBlock }
    - { caminho: scripts/gen-portfolio.mjs, linhas: "580", relevancia: 2, simbolo: fill }
    - { caminho: scripts/gen-portfolio.mjs, linhas: "593", relevancia: 1 }
  evidencia_esperada:
    - { caminho: scripts/gen-portfolio.mjs, linhas: "386", trecho: "const pfBlock = `<!-- PF:START" }
  resultado_esperado:
    outcome: answered
    afirmacoes_obrigatorias: ["pfBlock em scripts/gen-portfolio.mjs", "função fill"]
  criterios: [recall@k, mrr, citacao_exata, simbolo_correto]

- id: GS-CODE-003
  classe: code
  pergunta: "Qual teste verifica o contraste mínimo de 7:1 na Camada 3 da apresentação?"
  revisao_esperada: 73570bbc9b99e2a1e44d6844b9375bc4aa16e357
  fontes_relevantes:
    - { caminho: tests/apresentacao.tokens.test.mjs, linhas: "39", relevancia: 2 }
  evidencia_esperada:
    - { caminho: tests/apresentacao.tokens.test.mjs, linhas: "39", trecho: "test('INV-AP-02 · contraste do texto da Camada 3 ≥ 7:1 (evolução 11)'" }
  resultado_esperado:
    outcome: answered
    afirmacoes_obrigatorias: ["tests/apresentacao.tokens.test.mjs", "INV-AP-02"]
  criterios: [recall@k, mrr, citacao_exata]

- id: GS-CONF-001
  classe: conflict
  pergunta: "O projeto usa Vite ou é sem build step?"
  revisao_esperada: 73570bbc9b99e2a1e44d6844b9375bc4aa16e357
  fontes_relevantes:
    - { caminho: docs/specs/14-adr/ADR-001-sem-build.md, linhas: "1-24", relevancia: 2 }
    - { caminho: package.json, linhas: "30", relevancia: 2 }
    - { caminho: docs/specs/ARCHITECTURE.md, linhas: "395", relevancia: 1 }
    - { caminho: docs/specs/000-INDEX.md, linhas: "3", relevancia: 1 }   # escopo LifeOS
  evidencia_esperada:
    - { caminho: docs/specs/14-adr/ADR-001-sem-build.md, linhas: "24", trecho: "| Vite/bundler | Toolchain e lockfiles p/ manter; quebra o ethos \"view-source\" |" }
    - { caminho: package.json, linhas: "30", trecho: "\"vite\": \"^6.0.0\"" }
  resultado_esperado:
    outcome: answered_with_conflict
    afirmacoes_obrigatorias: ["o site usa Vite 6", "ADR-001 rejeita Vite no escopo do LifeOS/life3d"]
    afirmacoes_proibidas: ["o site inteiro é sem build", "escolher um lado sem citar o outro"]
  criterios: [recall@k, citacao_exata, cobertura_afirmacoes, deteccao_de_conflito]

- id: GS-CONF-002
  classe: conflict
  pergunta: "Quantos KPIs cognitivos o Knowledge OS define?"
  revisao_esperada: 73570bbc9b99e2a1e44d6844b9375bc4aa16e357
  fontes_relevantes:
    - { caminho: src/knowledge-os-presentation.html, linhas: "690", relevancia: 2 }
    - { caminho: src/knowledge-os-presentation.html, linhas: "1014", relevancia: 2 }
    - { caminho: src/knowledge-os-presentation.html, linhas: "2109", relevancia: 2 }
  evidencia_esperada:
    - { caminho: src/knowledge-os-presentation.html, linhas: "1014", trecho: "18 KPIs cognitivos divididos em 4 camadas (§7)." }
    - { caminho: src/knowledge-os-presentation.html, linhas: "2109", trecho: "22 KPIs cognitivos em 5 camadas" }
  resultado_esperado:
    outcome: answered_with_conflict
    afirmacoes_obrigatorias: ["a mesma página diz 18 (4 camadas) e 22 (5 camadas)"]
    afirmacoes_proibidas: ["um único número sem mencionar a divergência"]
  criterios: [recall@k, citacao_exata, deteccao_de_conflito]
  nota: "Depende de Q-05 (HTML)."

- id: GS-CONF-003
  classe: conflict
  pergunta: "Quantas páginas HTML existem em src/?"
  revisao_esperada: 73570bbc9b99e2a1e44d6844b9375bc4aa16e357
  fontes_relevantes:
    - { caminho: AGENTS.md, linhas: "64-65", relevancia: 2 }
  evidencia_esperada:
    - { caminho: AGENTS.md, linhas: "64", trecho: "CodeGraph has no HTML parser, so the 36" }
  resultado_esperado:
    outcome: abstained   # abstenção parcial
    abstention_codes_aceitos: [insufficient_evidence]
    afirmacoes_obrigatorias: ["AGENTS.md afirma 36", "a contagem não é verificada pela documentação"]
    afirmacoes_proibidas: ["são 36 páginas (como fato verificado)", "são 46 páginas (o MVP não agrega contagens)"]
  criterios: [citacao_exata, taxa_sem_suporte, reconhecimento_de_lacuna]
  nota: "Fato da inspeção: 46 arquivos src/*.html fora de src/en/. O caso testa que uma afirmação documental não vira fato verificado. Contagem por manifesto pode virar recurso futuro."

- id: GS-ABS-001
  classe: no_answer
  pergunta: "Qual é o RTO e o RPO do site em produção?"
  revisao_esperada: 73570bbc9b99e2a1e44d6844b9375bc4aa16e357
  fontes_relevantes: []
  evidencia_esperada: []
  resultado_esperado:
    outcome: abstained
    abstention_codes_aceitos: [no_hits, insufficient_evidence]
    afirmacoes_proibidas: ["qualquer valor de RTO ou RPO"]
  criterios: [reconhecimento_de_lacuna, taxa_sem_suporte]
  nota: "Verificado: busca por RTO/RPO em arquivos de texto do repositório retornou 0 ocorrências (só PNGs binários casaram)."

- id: GS-ABS-002
  classe: no_answer
  pergunta: "Qual foi o Recall@10 medido do Knowledge OS?"
  revisao_esperada: 73570bbc9b99e2a1e44d6844b9375bc4aa16e357
  fontes_relevantes:
    - { caminho: src/knowledge-os-presentation.html, linhas: "2210", relevancia: 1 }   # meta, não medição
  evidencia_esperada: []
  resultado_esperado:
    outcome: abstained
    abstention_codes_aceitos: [insufficient_evidence]
    afirmacoes_obrigatorias: ["não há medição registrada", "existe uma meta declarada: Recall@10 > 0.75 (rotulada como meta)"]
    afirmacoes_proibidas: ["Recall@10 medido = 0.75 ou qualquer valor"]
  criterios: [reconhecimento_de_lacuna, taxa_sem_suporte]

- id: GS-ABS-003
  classe: no_answer
  pergunta: "Qual banco vetorial o Knowledge OS usa em produção?"
  revisao_esperada: 73570bbc9b99e2a1e44d6844b9375bc4aa16e357
  fontes_relevantes:
    - { caminho: src/knowledge-os-presentation.html, linhas: "1068", relevancia: 1 }   # visão "vector + BM25 + graph", sem produto
  evidencia_esperada: []
  resultado_esperado:
    outcome: abstained
    abstention_codes_aceitos: [insufficient_evidence]
    afirmacoes_proibidas: ["nome de qualquer produto vetorial", "afirmar que há produção"]
  criterios: [reconhecimento_de_lacuna, taxa_sem_suporte]
  nota: "Verificado: nenhum de qdrant, pgvector, pinecone, weaviate, milvus, chromadb, faiss aparece no repositório."
```

**Distribuição:** 2 lexicais, 3 fatos de especificação, 3 de código (2 de símbolo, 1 de teste), 3 conflitantes, 3 sem resposta = 14 casos. É pouco para conclusões estatísticas; serve para validar o pipeline e as métricas. Meta de crescimento: §6.4.

## 4. Lacunas do golden set

| ID | Lacuna | Depende de |
|---|---|---|
| GS-ENT-* | Casos do corpus corporativo-alvo (C1): perguntas reais de usuários, documentos e repositórios reais. | Q-01 |
| GS-DOC-* | Casos de PDF/DOCX via Docling com localizador de página. C0 não tem esses formatos versionados. Candidato: um corpus de teste próprio (Q-13); o TGI de 2004 na pasta do projeto **não** deve ser usado sem decisão de Issei, pois tem pendência de consentimento de coautores. | Q-13 |
| GS-HIST-* | Perguntas sobre revisões antigas ("o que dizia o ADR X antes do commit Y"). | Q-04 |
| GS-MULTI-* | Perguntas que cruzam repositórios. | Q-01 |
| Rotulagem | Os julgamentos acima foram feitos por mim numa leitura. Precisam de revisão humana (segundo anotador) antes de virarem linha de base oficial. | Q-14 |

## 5. Métricas

Dois níveis, medidos e reportados **separadamente**. Uma boa recuperação com resposta ruim, ou o contrário, precisa aparecer como tal.

### 5.1 Recuperação (CTR-06, sem LLM)

Unidade de relevância: um resultado é relevante se seu intervalo se sobrepõe a pelo menos uma linha de uma `fonte_relevante` do caso, no mesmo caminho e na revisão esperada. Sobreposição por bytes quando houver; páginas para Docling.

| Métrica | Definição | Aplica-se a |
|---|---|---|
| Recall@k | fontes relevantes distintas cobertas no top-k ÷ fontes relevantes do caso | casos com `fontes_relevantes` ≠ ∅ |
| Precision@k | resultados relevantes no top-k ÷ k | idem |
| MRR | média de 1/rank do primeiro resultado com `relevancia: 2` | casos com resposta única clara (LEX, SPEC, CODE). Para CONF reporta-se Recall@k, porque é preciso achar os dois lados. |
| nDCG@k | ganho com relevância graduada 2/1 | opcional; só se a anotação graduada se mostrar estável |
| Hit-rate de "falso positivo" em no_answer | fração de casos ABS com algum resultado acima do limiar de suficiência | casos `no_answer` |

k reportados: 1, 3, 5, 10. Não se escolhe um "k oficial" antes da linha de base.

### 5.2 Citação (CTR-07)

| Métrica | Definição |
|---|---|
| Exatidão de citação | citações cujo (caminho, commit, intervalo) confere com o blob e cujo trecho é literal ÷ total de citações. Medida automaticamente pela releitura do blob. |
| Taxa de rótulo correto | citações cujo estado de verificação está correto ÷ total. Uma citação `verified_exact` que não confere é **falha grave**, contada à parte. |
| Acerto de evidência esperada | casos em que algum `evidencia_esperada.trecho` aparece numa citação ÷ casos com evidência esperada. |

### 5.3 Resposta (CTR-08, CTR-09)

| Métrica | Definição | Como medir |
|---|---|---|
| Cobertura de afirmações por evidência | afirmações com ≥ 1 citação verificada que as sustenta ÷ afirmações | Modo extrativo: 100% por construção (testa-se o invariante). Modo LLM: verificador automático de referência + amostra julgada por humano para "sustenta de fato". |
| Taxa de respostas sem suporte | respostas com ≥ 1 afirmação sem suporte, ou com `afirmacoes_proibidas` ÷ respostas | Automática para `afirmacoes_proibidas` por correspondência; humana na amostra. |
| Reconhecimento de lacunas | casos `no_answer` (e partes sem suporte) com abstenção correta e código aceito ÷ casos `no_answer` | Automática. |
| Abstenção indevida | casos com resposta esperada em que o sistema se absteve ÷ casos com resposta | Automática. Reportada junto com a anterior para mostrar o trade-off. |
| Detecção de conflito | casos `conflict` com `answered_with_conflict` e os dois lados citados ÷ casos `conflict` | Automática. |
| Afirmações obrigatórias | casos que contêm todas as `afirmacoes_obrigatorias` | Correspondência normalizada + revisão humana dos falhos. |

### 5.4 Recursos

Medidos por execução, com hardware e versões registrados: tempo de ingestão full e incremental, latência de consulta p50/p95 (recuperação e resposta separadas), pico de memória (RSS), tamanho de `index.sqlite`, número de fragmentos, e, no modo LLM, tokens de entrada/saída e chamadas. Latência de C0 vale como referência de máquina, não de produção.

## 6. Linha de base e calibração

### 6.1 Linha de base B0

B0 = FTS5 `bm25()` puro, pesos de coluna iguais, perfil de recorte inicial (CTR-02), resposta extrativa, abstenção apenas por `no_hits`. Executada sobre C0 em `73570bb`, 3 repetições para latência. Os números de B0 **não existem ainda**; serão produzidos pelo item BL-14 do backlog e registrados com o fingerprint do índice.

Linhas de comparação adicionais, todas sem embeddings:
- B0-grep: `git grep -n -i` com os termos da pergunta, para saber se o FTS5 agrega algo além de busca literal.
- B0-path: só correspondência no caminho do arquivo.

### 6.2 Por que não há metas numéricas agora

A página publicada declara "Recall@10 > 0.75" e "P95 retrieval < 800ms" (`00-inventario.md` DIV-06, DIV-07). Não há medição, corpus nem método por trás desses números no repositório. Adotá-los como limiar seria inventar meta. Ficam como hipóteses a confrontar com B0.

### 6.3 Calibração dos limiares de abstenção

1. Separar o golden set em calibração e teste (com 14 casos, isso só é viável depois de §6.4; até lá, calibra-se com validação cruzada deixando um caso de fora e se reporta a instabilidade).
2. Variar os limiares de CTR-09 (`min_hits`, cobertura de termos essenciais, `min_top_score` normalizado por consulta) e traçar a curva reconhecimento de lacunas × abstenção indevida.
3. Escolher o ponto pela regra de custo que Issei aprovar (**[ABERTO] Q-15**): proposta padrão é priorizar "taxa de respostas sem suporte = 0 no conjunto de teste" e, sob essa restrição, minimizar abstenção indevida.
4. Registrar o limiar escolhido com a revisão do benchmark e o fingerprint do índice. Mudança de perfil ou de parser obriga recalibração.
5. `bm25()` não é comparável entre consultas; por isso o limiar usa sinais relativos (cobertura de termos, razão top1/top2), não um valor absoluto de score.

### 6.4 Crescimento do golden set

Antes de usar qualquer métrica para decisão (por exemplo, revisar ADR-kos-008), o golden set precisa de casos suficientes por classe para que um caso a mais ou a menos não inverta a conclusão. Proposta: pelo menos 10 por classe em C0 e o mesmo em C1, com segundo anotador e concordância registrada. O número 10 é um ponto de partida para discussão, não um resultado estatístico (**[ABERTO] Q-14**).

## 7. Reprodutibilidade

- O benchmark roda via `kos bench run --suite golden/c0.yaml` e grava um relatório JSON com: revisão do corpus, fingerprint do índice, versões de ferramenta e parsers, métricas por caso e agregadas, e hardware.
- Consultas do benchmark entram em `audit.sqlite` com `interface='bench'`.
- Testes: TC-BEN-01 (esquema do YAML válido e IDs únicos), TC-BEN-02 (todo trecho esperado existe no blob da revisão esperada — o golden set se auto-verifica), TC-BEN-03 (métricas calculadas batem com um caso sintético calculado à mão), TC-BEN-04 (relatório contém métricas de recursos e versões).
