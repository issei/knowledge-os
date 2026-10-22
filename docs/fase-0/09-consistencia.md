---
id: KOS-F0-CON
titulo: Verificação de consistência, decisões e questões abertas
status: rascunho para aprovação
data: 2026-10-21
---

# Verificação de consistência

## 1. Matriz de rastreabilidade

| Requisito | ADR | Contrato | Testes | Backlog | Golden set |
|---|---|---|---|---|---|
| REQ-01 Git fonte de verdade / reconstruível | 001 | CTR-05 | TC-REB-01..03 | BL-09 | todos (revisão fixa) |
| REQ-02 Descoberta determinística | 001 | CTR-01 | TC-DSC-01..07 | BL-03 | GS-SPEC-001 (caminho não ASCII) |
| REQ-03 Parsing nativo / Tree-sitter / Docling opcional | 003 | CTR-02 | TC-PRS-01..08 | BL-05..07, BL-15, BL-22, BL-23 | GS-CODE-*, GS-DOC-* (lacuna) |
| REQ-04 Incremental | 001 | CTR-03 | TC-INC-01..05 | BL-16 | — |
| REQ-05 Atualização e remoção | 001 | CTR-04 | TC-UPD-01..05 | BL-17 | GS-HIST-* (lacuna) |
| REQ-06 FTS5 com filtros | 002 | CTR-06 | TC-RET-01..06 | BL-10 | GS-LEX-* |
| REQ-07 Localizador completo | 004 | CTR-07 | TC-CIT-01..06 | BL-11 | todos com evidência |
| REQ-08 Inferido ≠ verificado | 004 | CTR-07 | TC-CIT-03..05, TC-CLI-03 | BL-11 | GS-CONF-003 |
| REQ-09 Respostas fundamentadas | 007 | CTR-08 | TC-ANS-01..05 | BL-13, BL-21 | GS-SPEC-*, GS-CODE-* |
| REQ-10 Abstenção | 007 | CTR-09 | TC-ABS-01..05 | BL-13, BL-18 | GS-ABS-*, GS-CONF-003 |
| REQ-11 Conflitos | 004 | CTR-08 inv. 4 | TC-ANS-04 | BL-13 | GS-CONF-001, 002 |
| REQ-12 Erros e auditoria | 001 | CTR-10 | TC-AUD-01..05, TC-MCP-03 | BL-08, BL-12 | — |
| REQ-13 CLI | 005 | todos | TC-CLI-01..04 | BL-01..14 | — |
| REQ-14 MCP leitura | 006 | CTR-06, 07, 09 | TC-MCP-01..03 | BL-20 | — |
| REQ-15 Benchmark | 008 (evidência) | — | TC-BEN-01..04 | BL-14, BL-18, BL-19 | todos |
| RNF-01 Nada sai sem opt-in | 006, 007 | CTR-08 inv. 6, CTR-10 inv. 4 | TC-SEC-01, TC-ANS-05 | BL-20, BL-21 | — |
| RNF-02 Determinismo | 001 | CTR-01 inv. 2, CTR-02 inv. 1, CTR-05 inv. 2 | TC-DSC-03, TC-PRS-06, TC-REB-02 | BL-03..09 | — |
| RNF-03 Offline | 002, 005 | — | TC-CLI-04 | BL-01 | — |
| RNF-04 Recursos medidos | 002 | — | TC-BEN-04 | BL-14 | — |
| RNF-05 Caminhos como bytes | 003 | CTR-01 inv. 1 | TC-DSC-04 | BL-03 | GS-SPEC-001 |
| RNF-06 Sem vetores/grafos | 008 | — | TC-ARQ-01 | BL-01 | GS-ABS-003 |

## 2. Verificações feitas e achados

| # | Verificação | Resultado |
|---|---|---|
| 1 | Todo trecho de `evidencia_esperada` do golden set existe na linha indicada em `73570bb` | **14/14 conferidos** por script de leitura literal. Duas referências de `fontes_relevantes` em `AGENTS.md` estavam com linhas erradas no rascunho (40-41 → 39; 123-126 → 124-125) e foram corrigidas. |
| 2 | Todo requisito tem ADR, contrato ou teste e item de backlog | Sim (§1). REQ-15 não tem contrato próprio: o benchmark é especificado em `04-benchmark.md`, o que é intencional. |
| 3 | Todo ID de teste citado nos requisitos está definido | Conferido por script (TC-* de `01-requisitos.md` contra `03-contratos.md` e `06-plano-de-testes.md`). |
| 4 | Toda questão Q-* citada está definida em §3 | Conferido por script. |
| 5 | Contratos coerentes com o modelo de dados | Estados de verificação, códigos de abstenção e `outcome` são os mesmos nos `CHECK` de `audit.sqlite` e em CTR-07/08/09. `E_*` usados nos contratos estão no catálogo de CTR-10. |
| 6 | Golden set coerente com a arquitetura | **Resolvida pela decisão Q-05 (§4).** Registro original: GS-SPEC-003 e GS-CONF-002 dependem de HTML, que não está na lista de parsers aprovada (Q-05). Até BL-22, esses casos rodam com o perfil de texto (marcação crua) ou viram `out_of_scope`, conforme a resposta de Q-05; o relatório B0 deve marcá-los. |
| 7 | Golden set não mistura recuperação e resposta | Cada caso declara `fontes_relevantes` (recuperação) separado de `resultado_esperado` (resposta); métricas em §5.1 e §5.3 são calculadas separadamente. |
| 8 | Nenhuma meta numérica sem justificativa | Nenhuma meta fixada. Números da página pública registrados como hipóteses (DIV-06, DIV-07). O "10 casos por classe" de `04-benchmark.md` §6.4 está declarado como ponto de partida para discussão. |
| 9 | Nenhum arquivo existente alterado | Sim. Os únicos arquivos escritos estão em `/mnt/project-files/knowledge-os/fase-0/`. Nada foi instalado, nada foi enviado a serviço externo, nenhum commit foi feito. |
| 10a | DDL de `02-modelo-de-dados.md` é válido | Os dois blocos SQL foram executados num banco SQLite 3.45.1 **em memória** (sem gravar nada); todas as tabelas criadas e `PRAGMA foreign_key_check` vazio. |
| 10 | Divergências com decisões documentadas registradas | DIV-01..09 em `00-inventario.md` §4; ADR-kos-008 aponta as linhas. A página pública não foi alterada. |

## 3. Questões abertas (precisam de Issei antes da Fase 1)

| ID | Questão | Proposta padrão | Bloqueia |
|---|---|---|---|
| **Q-01** | Qual é o corpus/repositório-alvo? | **DECIDIDO (Issei, 2026-10-21): `issei/mauricio-site`.** C0 passa a ser o corpus-alvo. | — |
| **Q-02** | Linguagem de implementação | **DECIDIDO (Issei, 2026-10-21): Python.** | — |
| **Q-03** | O que fazer com a página `knowledge-os-presentation`, que descreve GraphRAG/vetores/agentes | Manter e, numa tarefa separada, rotular como "visão-alvo" | — |
| Q-04 | Indexar histórico completo ou só a ponta + revisões fixadas | Só ponta + fixadas no MVP | GS-HIST-* |
| **Q-05** | HTML entra como formato do MVP? | **DECIDIDO (Issei, 2026-10-21): sim.** O parser HTML entra no caminho vertical mínimo (BL-22 antes de BL-08). | — |
| Q-06 | Versão do SQLite na máquina de Issei (precisa de FTS5) | Verificar no BL-01 | BL-01 |
| Q-07 | Migração de esquema no MVP | Mudança de esquema = rebuild | — |
| Q-08 | Multiusuário e controle de acesso por documento | Fora do MVP | BL-20 remoto |
| Q-09 | Retenção de `audit.sqlite` | Sem expurgo no MVP; definir antes de C1 com dados sensíveis | — |
| Q-10 | Arquivos Git LFS | Excluídos com regra `lfs_pointer` | — |
| Q-11 | Regra de precedência entre fontes conflitantes (ex.: ADR aceito > página) | Nenhuma no MVP: mostrar os dois lados | — |
| Q-12 | Códigos de saída 3 (abstenção) e 4 (parcial) | Manter | — |
| Q-13 | Corpus de PDF/DOCX para testar Docling | Criar documentos de teste próprios; não usar o TGI de 2004 sem consentimento dos coautores | BL-23 |
| Q-14 | Segundo anotador e tamanho mínimo do golden set | Issei como segundo anotador; ≥ 10 casos por classe como ponto de partida | BL-18 |
| Q-15 | Regra de custo para escolher o limiar de abstenção | Zero respostas sem suporte no conjunto de teste; minimizar abstenção indevida sob essa restrição | BL-18 |
| Q-16 | Tempo de rebuild aceitável em C1 | Definir após medir C1 | revisão de ADR-kos-001 |
| Q-17 | O repositório `mauricio-site` é público? Permalinks de forge podem ir na citação? | Campo opcional; nunca identidade | — |
| Q-18 | Política de provedores de LLM (local/remoto) | Desligado; remoto só com opt-in por repositório | BL-21 |
| **Q-19** | Onde os documentos e o código vão morar | Repositório próprio (`knowledge-os`), não o `mauricio-site`, cujo merge em `main` publica o site | BL-01 |

As marcadas em negrito são as que mais mudam o desenho.

## 4. Decisões registradas (Issei, 2026-10-21)

| Questão | Decisão | Efeito nos documentos |
|---|---|---|
| Q-19 | Repositório próprio `issei/knowledge-os` | Documentos em `docs/fase-0/` deste repositório. |
| Q-01 | Corpus-alvo = `issei/mauricio-site` | C0 deixa de ser só piloto e vira o corpus do MVP; não há C1 separado. GS-ENT-* e GS-MULTI-* saem das lacunas; BL-19 vira a expansão do golden set no próprio `mauricio-site`. RSK-01 cai para baixa probabilidade. |
| Q-02 | Python | Módulos candidatos viram o pacote Python `kos`. Bibliotecas concretas (parser Markdown, YAML e JSON com posições, bindings do Tree-sitter) são escolhidas e justificadas em BL-05, BL-06 e BL-15, com TC-PRS-01 como critério. |
| Q-05 | HTML entra no MVP | ADR-kos-003 item 5 deixa de ser aberto. BL-22 passa para dentro do caminho vertical (BL-08 depende dele). GS-SPEC-003 e GS-CONF-002 deixam de ser condicionais. A tensão do achado 6 (§2) está resolvida. |

Os ADR-kos-001..008 foram **aceitos** por Issei em 2026-10-22 (BL-00 concluído).

## 5. Registro da implementação

| Item | Decisão ou medição |
|---|---|
| BL-05 parser Markdown | `markdown-it-py` 3.x (preset CommonMark + tabelas). Motivo: expõe o mapa de linhas de cada bloco, o que permite recortar fragmentos por limites de bloco e calcular bytes a partir das linhas. Medição em `mauricio-site@73570bb`: 413 arquivos `.md` elegíveis, 6.622 fragmentos, **0 divergentes** em `normalize(recorte) == texto` (TC-PRS-01), 0 falhas de decodificação. Script: `scripts/dev/check_offsets.py`. |
| BL-06/07 JSON, YAML, texto e código como texto | JSON: leitor próprio sobre a biblioteca padrão (o `json` não dá posições). YAML: `PyYAML` 6.x, fase `compose` com `SafeLoader` (marcas de início e fim por nó, nenhuma tag vira objeto). Medição em `mauricio-site@73570bb`, todos os 856 elegíveis: JSON 26 arquivos / 2.384 fragmentos, YAML 12 / 263, texto 30 / 137, código como texto 290 / 972, Markdown 413 / 6.622; **0 divergentes**, nenhum caiu no recurso de sintaxe. 85 HTML ficam `skipped` até o BL-22. Observação para o benchmark: nós de segundo nível podem ser grandes (`/jobs/deploy` em `deploy.yml` tem 90 linhas). |
| BL-08 correção de `fragment_key` | A fórmula da Fase 0 (`blob ‖ perfil ‖ localizador`) dava a mesma chave para o mesmo blob em dois caminhos; o corpus tem 6 blobs repetidos e a ingestão violou `UNIQUE(fragment_key)`. A chave passou a incluir o nome lógico do repositório e o caminho em bytes (§1 de `02-modelo-de-dados.md`). Continua determinística e continua mudando com conteúdo, perfil ou recorte. |
| BL-08 ingestão full | `kos ingest mauricio-site --rev 73570bb --full` → `succeeded`: 907 entradas no manifesto (856 elegíveis, 51 excluídas com regra), 13.999 fragmentos, `foreign_key_check` e `integrity_check` limpos, `integrity-check` do FTS limpo; `index.sqlite` com 23 MiB. Segunda execução: 856 reaproveitados, 0 processados. Observação para o BL-10: a busca "retrieval 800ms" traz a página em inglês (`src/en/**`, `is_generated = 1`) à frente da fonte em português; o filtro e o peso de gerados são decisão do BL-10. |
| BL-09 rebuild | `kos rebuild` sobre o índice de `mauricio-site@73570bb`: 11 s, `succeeded`, digest do dump lógico igual ao do índice ingerido (`61fab801…`), nenhum fragmento adicionado ou removido; hash de `audit.sqlite` inalterado (TC-AUD-02). |
| BL-10 busca | Verificação funcional do critério do BL-10 em `mauricio-site@73570bb` (gerados fora, k=10): **GS-SPEC-001** traz `AGENTS.md` (linhas 117-129, contém a linha 121) em **1º**. **GS-LEX-001 não atende**: o fragmento `/scripts/gate` de `package.json` fica em 55º com a pergunta completa e em 13º com só "quality gate"; documentos longos que repetem "quality gate" e palavras comuns ("o", "do") ficam à frente. Não ajustei pesos nem acrescentei lista de palavras vazias para passar um caso só, o que seria sobreajuste ao golden set; o caso entra na análise de erros do B0 (BL-14). Latência observada: 6 a 46 ms por consulta. |
| BL-11 citação | `kos cite` relê o blob do Git e decide o estado pelo hash do recorte. Varredura em `mauricio-site@73570bb`: os 13.999 fragmentos citados, 10.421 `verified_exact`, 3.578 `verified_normalized` (HTML cujo texto visível difere do literal), 0 `unverified`, em 28 s. Zero `verified_exact` falsos por construção: o estado só sai exato quando o hash do recorte literal normalizado é igual ao do fragmento. CTR-07 inv. 6 (apontar para a fonte em vez do gerado) fica pendente; os gerados são só marcados. |
| BL-12 auditoria | `kos search` passa a gravar `query_event` (antes da busca) e `retrieval_result`; `kos audit verify` reconfere citações gravadas sem o índice. Em `mauricio-site@73570bb`, a busca auditada leva 36 a 59 ms de consulta e cerca de 0,2 s de processo inteiro na CLI. TC-AUD-02 (rebuild não muda o hash do `audit.sqlite`) já vinha do BL-09; TC-AUD-04 (catálogo fechado) do BL-01. |
| BL-13 resposta extrativa | `kos ask` em `mauricio-site@73570bb` com os limiares iniciais, pergunta a pergunta do golden set: **GS-ABS-001** → `insufficient_evidence` ("rto" e "rpo" não ocorrem no corpus); **GS-CONF-002** → `answered_with_conflict` com 18 × 22 KPIs; **GS-SPEC-001** → `AGENTS.md#L121` citado na linha, `verified_exact`; os demais casos com resposta esperada respondem; se a evidência certa está entre as afirmações, o B0 mede. Desvios que vão para a análise de erros do B0 (BL-14), sem ajuste agora: GS-ABS-002 e GS-ABS-003 respondem (todos os termos existem no corpus); GS-CONF-001 responde sem conflito (contradição sem número); GS-CONF-003 responde em vez de abster-se em parte. |
| BL-14 benchmark B0 | O golden set C0 está em `bench/golden/c0.yaml`. A auto-verificação dá 14 casos e 0 problemas. B0 em `mauricio-site@73570bb`: Recall@10 0,42; MRR 0,35; resultado correto 0,64; 0 `verified_exact` falso em 76 citações. B0-grep: Recall@10 0,10. Relatório e análise de erros: [`bench/reports/b0-c0-73570bb.md`](../../bench/reports/b0-c0-73570bb.md). Novo código de erro: `E_SUITE_INVALID`. |
| BL-22 HTML | `html.parser` da biblioteca padrão; o texto do fragmento é o texto visível do recorte, logo a citação HTML é `verified_normalized` (CTR-02 inv. 2, CTR-07 inv. 4). Medição em `mauricio-site@73570bb`: 85 arquivos, 3.621 fragmentos, **0 divergentes** entre o texto e `visible_text(normalize(recorte))`. As evidências de GS-SPEC-003 (linha 1015) e GS-CONF-002 (linhas 1014 e 2109) de `knowledge-os-presentation.html` caem em fragmentos cujo texto contém o trecho esperado, com `&lt;` decodificado para `<`. |
