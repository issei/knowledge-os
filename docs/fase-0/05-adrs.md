---
id: KOS-F0-ADR
titulo: Fase 0E — ADRs preliminares
status: propostos (nenhum aceito)
data: 2026-10-21
---

# Fase 0E — ADRs preliminares

Prefixo `ADR-kos-NNN`, para não colidir com `docs/specs/14-adr/ADR-NNN` (LifeOS) nem `ADR-eai/te/ap-*` (páginas). Todos estão em **Proposto**; viram **Aceito** com a aprovação de Issei antes da Fase 1. Formato herdado de `docs/decisions/ADR-eai-002-*.md`, acrescido de riscos, evidências necessárias e condição de revisão.

---

## ADR-kos-001 — Fonte de verdade e reconstrução

- **Status:** Proposto · **Requisitos:** REQ-01, REQ-12, RNF-02 · **Contratos:** CTR-01, CTR-05, CTR-10

**Contexto.** O valor do sistema está em respostas rastreáveis. Se o índice puder divergir silenciosamente do Git, a rastreabilidade se perde. A arquitetura provisória já fixa Git como fonte de verdade.

**Decisão provisória.**
1. Git (objetos do commit) é a única fonte de verdade. A cópia de trabalho não é lida.
2. `index.sqlite` é 100% derivado e descartável; `rebuild` a partir de (repositórios, commits retidos, política, perfis) é operação de primeira classe e determinística.
3. Auditoria vive em `audit.sqlite`, separada, nunca tocada pelo rebuild.
4. Identidade de fragmento é um hash determinístico (`02-modelo-de-dados.md` §1), não um ID sequencial.

**Alternativas.** (a) Índice como fonte primária com sincronização periódica: rejeitada, cria divergência e perde proveniência. (b) Ler a cópia de trabalho: rejeitada, conteúdo não endereçável por commit. (c) Um único banco com auditoria dentro: rejeitada, o rebuild apagaria a trilha.

**Consequências.** (+) Qualquer resposta pode ser reconferida contra o Git. (+) Migração de esquema vira rebuild. (−) Conteúdo não versionado (wikis, tickets) fica fora até ter um conector que o materialize em Git ou em um armazenamento endereçável. (−) Force-push pode apagar commits retidos.

**Riscos.** Rebuild lento em corpus grande; commits retidos perdidos após reescrita de histórico; determinismo quebrado por dependência de ordem do sistema de arquivos ou de locale.

**Evidências necessárias.** TC-REB-01..03 verdes; tempo de rebuild de C0 e de C1 medido; prova de determinismo com dois rebuilds em máquinas diferentes.

**Condição de revisão.** Rebuild de C1 acima do que Issei considerar aceitável (Q-16), ou necessidade de fontes que não são Git.

---

## ADR-kos-002 — SQLite/FTS5 como busca inicial

- **Status:** Proposto · **Requisitos:** REQ-06, RNF-03, RNF-06 · **Contratos:** CTR-06

**Contexto.** O MVP precisa de busca textual com metadados e proveniência, offline, sem serviço residente. O ambiente inspecionado já tem SQLite 3.45.1 com FTS5. O repositório já usa BM25 em memória via `okf search` para a memória OKF.

**Decisão provisória.** SQLite com FTS5 (tabela de conteúdo externo, `bm25()` com pesos por coluna, tokenizador `unicode61 remove_diacritics 2`) é o único mecanismo de recuperação do MVP. Metadados, manifesto e proveniência ficam no mesmo arquivo, permitindo filtrar por revisão em uma consulta.

**Alternativas.** (a) Elasticsearch/OpenSearch: rejeitada no MVP, exige serviço e operação. (b) Tantivy/Lucene embarcado: viável, mas separa índice de metadados e acrescenta dependência sem ganho demonstrado. (c) `git grep` puro: mantido como linha de comparação B0-grep, sem ranking nem metadados. (d) Busca vetorial: ver ADR-kos-008.

**Consequências.** (+) Zero infraestrutura; arquivo único; transações. (+) Filtros por revisão via `JOIN` no manifesto. (−) Sem sinônimos nem semântica: perguntas parafraseadas vão falhar mais. O benchmark mede o quanto. (−) `bm25()` não é comparável entre consultas, o que complica limiares de abstenção (tratado em `04-benchmark.md` §6.3).

**Riscos.** Tokenização ruim para identificadores de código e para PT-BR; concorrência de escrita (um escritor por vez); tamanho do índice em C1.

**Evidências necessárias.** B0 vs B0-grep em C0; TC-RET-02/03 (acentos e identificadores); tamanho e latência em C1.

**Condição de revisão.** Recall@k de B0 abaixo de um patamar que Issei defina após ver B0, com análise de erros mostrando que as falhas são de vocabulário (paráfrase), não de recorte ou tokenização.

---

## ADR-kos-003 — Estratégia de parsing

- **Status:** Proposto · **Requisitos:** REQ-03, RNF-05 · **Contratos:** CTR-02

**Contexto.** O corpus tem Markdown, YAML, JSON, código e texto; documentos complexos (PDF/DOCX) são raros em C0 e desconhecidos em C1. A citação verificável exige offsets confiáveis no original.

**Decisão provisória.**
1. Parsers nativos para Markdown, YAML, JSON e texto, escolhidos pela capacidade de devolver **posições no original** (bytes/linhas). Parser sem posições não é aceito para formato textual.
2. Tree-sitter para código: sintaxe e símbolos de topo, com versão da gramática no perfil. Linguagens iniciais: as presentes no corpus-alvo; em C0, JavaScript (`.js`, `.mjs`, `.cjs`) e Python.
3. Docling só atrás do perfil opcional `docling`, para PDF/DOCX, com localizador de página e verificação no máximo `verified_normalized`.
4. Todo parser é encapsulado num perfil com fingerprint; trocar versão ou configuração invalida o cache de forma explícita.
5. HTML: **decisão aberta (Q-05)**. Proposta: parser HTML nativo da linguagem escolhida, extraindo texto visível com offsets, tratado como "documento", com páginas geradas marcadas como `generated`.

**Alternativas.** (a) Docling para tudo: rejeitada, perde offsets de texto e acrescenta dependência pesada. (b) Expressões regulares para código: rejeitada, símbolos frágeis. (c) Indexar arquivo inteiro sem recorte: rejeitada, citações imprecisas e ranking pior.

**Consequências.** (+) Citação exata por bytes em todo formato textual. (−) Um perfil por formato para manter. (−) Tree-sitter exige empacotar gramáticas e fixar versões.

**Riscos.** Parser Markdown que normaliza o texto sem preservar posições; gramáticas com comportamento diferente entre versões; Docling instável ou lento.

**Evidências necessárias.** TC-PRS-01 (100% dos fragmentos verificáveis) em C0; taxa de `parsed_with_warnings` por linguagem.

**Condição de revisão.** Formato relevante em C1 sem parser com posições; ou volume de PDF/DOCX em C1 que torne o Docling caminho principal.

---

## ADR-kos-004 — Proveniência e formato das citações

- **Status:** Proposto · **Requisitos:** REQ-07, REQ-08, REQ-11 · **Contratos:** CTR-07, CTR-08

**Contexto.** O pedido proíbe apresentar localização inferida como verificada. Formatos têm estruturas diferentes (linhas, ponteiros, páginas, símbolos).

**Decisão provisória.**
1. Citação = repositório, caminho, commit completo, blob, localizador polimórfico, trecho literal, hash do trecho e **estado de verificação** obrigatório (`verified_exact`, `verified_normalized`, `derived`, `unverified`).
2. A verificação relê o blob do Git no momento da montagem.
3. Forma humana: `[n] repo:caminho#La-Lb @commit12 (estado)` seguida do trecho; JSON completo com esquema versionado.
4. Renomeações são inferidas e rotuladas; citações não herdam identidade.
5. Conflitos mostram as duas fontes com escopo; não há resolução implícita.

**Alternativas.** (a) Só caminho + linha: rejeitada, não é reconferível sem commit e hash. (b) Permalink de forge (GitHub): útil como campo extra, não como identidade, porque depende de hospedagem e visibilidade (Q-17). (c) Omitir o estado quando verificado: rejeitada, ausência de rótulo é ambígua.

**Consequências.** (+) Toda citação é auditável a posteriori. (−) Citações longas na saída humana. (−) Custo de reler blobs a cada resposta (pequeno, medido no benchmark).

**Riscos.** Normalização de texto divergente entre indexação e verificação; repositório indisponível no momento da resposta (vira `unverified`).

**Evidências necessárias.** TC-CIT-01..06; métrica "taxa de rótulo correto" = 100% no golden set; zero `verified_exact` falsos.

**Condição de revisão.** Necessidade de citar fontes fora do Git, ou formato de citação exigido por cliente/ferramenta MCP.

---

## ADR-kos-005 — Interface CLI

- **Status:** Proposto · **Requisitos:** REQ-13, RNF-03 · **Contratos:** CTR-01..10

**Contexto.** A CLI é a interface primária aprovada. O benchmark, os testes e o futuro MCP precisam do mesmo núcleo.

**Decisão provisória.** Um executável `kos` com subcomandos:

| Comando | Contrato |
|---|---|
| `kos init` | cria `index.sqlite` e `audit.sqlite` |
| `kos repo add <nome> <caminho>` | registra repositório |
| `kos ingest <nome> [--rev <commit>] [--full]` | CTR-01..04 |
| `kos rebuild` | CTR-05 |
| `kos gc` | CTR-04 inv. 5 |
| `kos search "<consulta>" [--rev] [-k] [--kind] [--path]` | CTR-06 |
| `kos cite <fragment_key>` | CTR-07 |
| `kos ask "<pergunta>" [--mode extractive\|llm]` | CTR-08, CTR-09 |
| `kos bench run --suite <arquivo>` | `04-benchmark.md` |
| `kos status` / `kos errors [--run]` | CTR-10 |

Toda saída tem `--json` com esquema versionado (`schema: "kos.<comando>.v1"`). Códigos de saída em CTR-10. A CLI é uma casca fina: a lógica fica numa biblioteca que o MCP reutiliza.

**Alternativas.** (a) Servidor HTTP primeiro: rejeitada, acrescenta operação. (b) Só biblioteca: rejeitada, dificulta uso e auditoria manual.

**Consequências.** (+) Testável por processo, scriptável. (−) Esquemas JSON passam a ser contrato público e precisam de versionamento.

**Riscos.** Linguagem de implementação indefinida (Q-02) afeta distribuição e o acesso a Tree-sitter/Docling.

**Evidências necessárias.** TC-CLI-01..04.

**Condição de revisão.** Uso real concentrado no MCP, tornando a CLI secundária.

---

## ADR-kos-006 — Integração MCP de leitura

- **Status:** Proposto · **Requisitos:** REQ-14, RNF-01 · **Contratos:** CTR-06, CTR-07, CTR-09

**Contexto.** A integração MCP está planejada. Um servidor MCP expõe o corpus a clientes de agente; o risco é transformar recuperação em canal de exfiltração ou de escrita.

**Decisão provisória.** Servidor MCP local (stdio), somente leitura, com três ferramentas: `search` (CTR-06), `get_citation` (CTR-07) e `ask_extractive` (CTR-08 em modo extrativo, com abstenção). Sem ingestão, sem `rebuild`, sem leitura de arquivo arbitrário, sem execução de comandos. Limites de `k` e de tamanho de trecho. Toda chamada vai para `audit.sqlite` com `interface='mcp'`. Entra **depois** do caminho vertical mínimo (BL-17).

**Alternativas.** (a) Expor leitura de arquivo genérica: rejeitada, ignora política de elegibilidade. (b) Transporte HTTP remoto: adiado; exige autenticação (Q-08).

**Consequências.** (+) Agentes recebem só evidências citáveis. (−) O cliente MCP pode enviar o conteúdo recuperado a um modelo remoto; isso sai do controle do Knowledge OS e precisa ser dito na documentação.

**Riscos.** Injeção de instruções dentro de documentos recuperados (o conteúdo é dado, não instrução; o servidor marca a origem); vazamento de conteúdo privado via cliente.

**Evidências necessárias.** TC-MCP-01..03 (ferramentas listadas são só as três; tentativa de caminho fora da política falha; toda chamada auditada).

**Condição de revisão.** Necessidade de acesso remoto ou multiusuário.

---

## ADR-kos-007 — Uso opcional de LLM

- **Status:** Proposto · **Requisitos:** REQ-09, REQ-10, RNF-01 · **Contratos:** CTR-08, CTR-09

**Contexto.** Respostas extrativas são verificáveis mas pouco fluentes. Um LLM pode sintetizar, mas cria risco de afirmações sem suporte e de envio de conteúdo privado a terceiros.

**Decisão provisória.**
1. O modo padrão é extrativo, sem LLM.
2. Um adaptador de LLM opcional, **desligado por padrão**, com interface única (`generate(question, fragments) → claims com referências`). Provedores local ou remoto são configuração; remoto exige opt-in explícito por repositório.
3. O LLM nunca vê o índice nem o repositório; recebe só os fragmentos recuperados.
4. Toda afirmação passa por validador de referências (CTR-08 inv. 1); sem suporte, é removida.
5. Recuperação e benchmark de recuperação não dependem de LLM.

**Alternativas.** (a) LLM obrigatório: rejeitada, viola RNF-01 e mistura qualidade de recuperação com geração. (b) Sem LLM nunca: possível, mas fecha a porta para síntese; mantido como padrão.

**Consequências.** (+) MVP utilizável sem nenhuma chamada externa. (−) Métricas de resposta em modo LLM exigem julgamento humano por amostra.

**Riscos.** Verificador de referência aceitar afirmação que cita fragmento real mas não é sustentada por ele (por isso a amostra humana); custos de token.

**Evidências necessárias.** TC-ANS-02, TC-ANS-03, TC-ANS-05; taxa de respostas sem suporte medida em modo LLM vs. extrativo.

**Condição de revisão.** Política de dados de Issei/empresa sobre provedores (Q-18); resultados do benchmark em modo LLM.

---

## ADR-kos-008 — Exclusão temporária de embeddings e grafos

- **Status:** Proposto · **Requisitos:** RNF-06 · **Diverge de:** `src/knowledge-os-presentation.html:1068,1112,1138,1151` e `public/knowledge-os-presentation.md` (DIV-01..05)

**Contexto.** A página pública do Knowledge OS descreve GraphRAG, busca híbrida vetor + BM25 + grafo, ontologia JSON-LD/SHACL e agentes via LangGraph/Mastra/CrewAI. Nada disso existe implementado. A arquitetura provisória aprovada exclui esses componentes do núcleo inicial.

**Decisão provisória.** O núcleo do MVP não usa embeddings, bancos vetoriais, bancos de grafos nem orquestração multiagente. O esquema não reserva colunas para vetores. A divergência com a página pública fica registrada; a página **não** é alterada nesta fase.

**Alternativas.** (a) Seguir a página e começar por GraphRAG: rejeitada, sem linha de base não há como provar ganho, e o custo operacional é alto. (b) Híbrido desde o início com vetores: rejeitada pelo mesmo motivo e por RNF-01 (modelos de embedding remotos).

**Consequências.** (+) Linha de base simples, explicável e barata. (−) Perguntas por paráfrase terão recall menor. (−) A página pública promete mais do que o MVP entrega (Q-03).

**Riscos.** Pressão para adicionar vetores antes de ter B0; leitores do site confundirem visão com produto.

**Evidências necessárias para revisar.** B0 medido; análise de erros mostrando que uma parcela relevante das falhas é de vocabulário; golden set com tamanho suficiente (`04-benchmark.md` §6.4); experimento controlado com um único componente novo por vez, comparado contra B0 nas mesmas métricas.

**Condição de revisão.** As evidências acima existirem; ou um requisito de C1 que FTS5 comprovadamente não atenda.
