---
id: KOS-F0-CTR
titulo: Fase 0C — Contratos
status: rascunho para aprovação
data: 2026-10-21
requisitos: [REQ-01..REQ-15, RNF-01..RNF-06]
---

# Fase 0C — Contratos

Cada contrato define entradas, saídas, invariantes, falhas esperadas e testes de contrato. Os nomes de funções são **lógicos**; linguagem e assinatura concretas são decididas na Fase 1 (Q-02). Códigos de erro pertencem ao catálogo fechado de CTR-10.

Tipos comuns:

```text
RepoRef      = { repo_name, commit_oid (hex completo) }
Policy       = { policy_id, version, include[], exclude[], max_bytes, generated[], kind_rules[] } → policy_sha256
Profile      = processing_profile (02-modelo-de-dados.md §4)
Locator      = { type: text|structured|code|page, start_byte?, end_byte?, start_line?, end_line?,
                 struct_path?, page_start?, page_end?, symbol? }
Verification = verified_exact | verified_normalized | derived | unverified
```

---

## CTR-01 — Descoberta de arquivos elegíveis

**Entradas:** `RepoRef`, `Policy`.
**Saída:** lista ordenada por `path_bytes` de `{ path_bytes, path_text, path_is_utf8, blob_oid, file_mode, byte_size, eligibility, exclusion_rule?, artifact_kind, kind_rule, is_generated }`.

**Invariantes**
1. Lê a árvore do commit (`git ls-tree -r -z` ou equivalente). Nunca lê a cópia de trabalho, o índice do Git nem arquivos não rastreados.
2. Mesmas entradas → mesma saída, byte a byte (determinismo).
3. Todo arquivo da árvore aparece na saída, como `eligible` ou `excluded` com a regra que o excluiu. Nada some em silêncio.
4. Symlinks (`120000`) são `excluded` com `symlink_not_followed`. Submódulos (`160000`) são `excluded` com `submodule_not_followed`. Ponteiros LFS são `excluded` com `lfs_pointer` (Q-10).
5. Arquivo acima de `max_bytes` é `excluded` com `too_large`.
6. Binário sem perfil que o aceite é `excluded` com `binary_unsupported`. Heurística (BL-03): nos primeiros 8000 bytes, há NUL **e** o trecho não é UTF-8 válido, ou mais de 10% dos bytes são de controle. NUL sozinho não basta: no corpus, `scripts/optimize-critical-path.mjs` é texto e usa um byte NUL como sentinela.

**Falhas esperadas:** `E_REPO_NOT_FOUND`, `E_COMMIT_NOT_FOUND`, `E_POLICY_INVALID`, `E_GIT_UNAVAILABLE`.

**Testes de contrato**
- TC-DSC-01 Repositório-fixture com 10 arquivos → 10 entradas, ordem estável.
- TC-DSC-02 Arquivo modificado só na cópia de trabalho não altera a saída.
- TC-DSC-03 Duas execuções produzem saída idêntica (hash da serialização).
- TC-DSC-04 Caminhos `apresentação/ADR.md` (UTF-8, NFD e NFC) e um nome não UTF-8 → `path_bytes` exato; `path_is_utf8` correto.
- TC-DSC-05 Symlink, submódulo e ponteiro LFS → `excluded` com a regra certa.
- TC-DSC-06 `src/en/**` marcado como `generated` pela regra declarada.
- TC-DSC-07 Política inválida → `E_POLICY_INVALID`, nenhuma escrita no índice.

---

## CTR-02 — Parsing e normalização

**Entradas:** `{ blob_bytes, path_text, media_type, Profile }`.
**Saída:** `{ status: parsed|parsed_with_warnings|skipped|failed, reason_code?, fragments[], symbols[], warnings[] }`, onde cada fragmento tem `{ ordinal, fragment_kind, heading_path?, text, ident_terms?, text_sha256, Locator }`.

**Invariantes**
1. Função pura de `(blob_bytes, Profile)`: sem rede, sem relógio, sem estado global.
2. Para formatos textuais, `blob_bytes[start_byte:end_byte]` decodificado e normalizado pelo `normalizer_version` produz exatamente `text` (é a base de `verified_exact`). **Exceção: HTML**, cujo `text` é o texto visível do recorte, `visible_text(normalize(recorte))`; a função depende só do recorte, então a citação é reconferível, mas como `verified_normalized`.
3. Linhas são 1-based e inclusivas; `\r\n` conta como uma quebra; offsets são do blob original.
4. Ordinais começam em 0 e são contíguos.
5. Fragmentos não se sobrepõem dentro do mesmo perfil, exceto `symbol` aninhado, que referencia o pai.
6. Docling só roda se o perfil `docling` estiver habilitado e o tipo estiver na lista do perfil; sua saída usa `Locator.type = page`.
7. Erro de parsing de um arquivo não interrompe os demais (o orquestrador registra e segue).

**Regras de recorte (perfil inicial, ajustáveis pelo benchmark)**
- Markdown: uma seção por cabeçalho; seções longas divididas por parágrafo respeitando blocos de código e tabelas; `heading_path` sempre presente. Front matter YAML vira fragmento `yaml_node`.
- YAML/JSON: um fragmento por nó de primeiro e segundo nível com `struct_path` (JSON Pointer); o fragmento de um membro de objeto começa na chave. Sintaxe inválida (ex.: JSON com comentários) cai em janelas de texto, com `parsed_with_warnings` e `E_PARSE_SYNTAX`.
- Código: um fragmento por símbolo de topo (função, classe, export) mais um fragmento "resto do arquivo"; testes reconhecidos (`describe`/`it`/`test`) viram `test_case`.
- Texto puro: janelas por parágrafo (até 40 linhas). Até o BL-15, código usa as mesmas janelas (até 60 linhas) com `fragment_kind = code_block`.
- HTML: uma seção por cabeçalho `h1`..`h6` com `heading_path`, como no Markdown; o que vem antes do primeiro cabeçalho (título, `meta description`, navegação) é a seção sem `heading_path`; seções com mais de 80 linhas são divididas no início de um elemento de bloco. Conteúdo de `script`, `style`, `template`, `noscript`, `svg`, `math`, `iframe`, `object` e `canvas` não entra.

**Falhas esperadas:** `E_DECODE` (encoding), `E_PARSE_SYNTAX` (com `parsed_with_warnings` quando houver recuperação parcial do Tree-sitter), `E_PARSER_UNAVAILABLE`, `E_TIMEOUT_PARSE`, `E_TOO_MANY_FRAGMENTS`.

**Testes de contrato**
- TC-PRS-01 Para cada fixture textual, `slice(bytes) → normalize == text` em 100% dos fragmentos.
- TC-PRS-02 Arquivo CRLF e LF com o mesmo conteúdo lógico → mesmas linhas, offsets diferentes, ambos verificáveis.
- TC-PRS-03 Markdown com cabeçalhos aninhados → `heading_path` correto; bloco de código não é cortado.
- TC-PRS-04 JSON com ponteiro `/scripts/gate` → fragmento com `struct_path` correspondente e linhas corretas.
- TC-PRS-05 JS com erro de sintaxe → `parsed_with_warnings` e símbolos válidos fora da região quebrada.
- TC-PRS-06 Mesma entrada duas vezes → saídas idênticas (pureza).
- TC-PRS-07 Perfil `docling` desligado + PDF → `skipped` com `profile_disabled`.
- TC-PRS-08 Mudar `config_json` do perfil → `profile_fingerprint` diferente → chaves de fragmento diferentes.

---

## CTR-03 — Ingestão incremental

**Entradas:** `repo_name`, `base_commit` (última revisão `succeeded`), `target_commit`, `Policy`, perfis ativos.
**Saída:** registro `ingest_run` com `status` e `counts_json = { discovered, eligible, reused, processed, failed, removed_from_manifest }`.

**Invariantes**
1. O conjunto a processar é `{ versões elegíveis em target } − { (version, profile) já em version_processing com status ≠ failed }`.
2. Versão com `blob_oid` igual é reaproveitada sem parsing (contagem `reused`).
3. O manifesto de `target` é gravado inteiro. A execução só fica `succeeded` depois do manifesto, dos fragmentos e do FTS confirmados na mesma sequência transacional.
4. Falhas por arquivo deixam a execução `partial`, não `failed`; o artefato falho fica no manifesto com `version_processing.status = failed` e **não** tem fragmentos pesquisáveis.
5. Uma execução interrompida não deixa a revisão-alvo consultável (consultas usam a última revisão `succeeded`/`partial`).
6. O resultado final é idêntico ao de uma ingestão `full` da mesma revisão (propriedade verificada por TC-INC-04).
7. Mudança de `Policy` ou de perfil força reavaliação dos itens afetados (o cache é chaveado por perfil).

**Falhas esperadas:** `E_BASE_NOT_INDEXED`, `E_BASE_NOT_ANCESTOR` (aviso; continua como diff de árvores), `E_LOCKED` (outra ingestão em curso), `E_DISK_FULL`, `E_ABORTED`.

**Testes de contrato**
- TC-INC-01 Commit que altera 1 de 10 arquivos → `processed=1`, `reused=9`.
- TC-INC-02 Commit que só muda modo de arquivo → `processed=0`.
- TC-INC-03 Falha de parsing em 1 arquivo → `partial`; os outros consultáveis; erro registrado.
- TC-INC-04 Propriedade: para uma sequência de commits-fixture, `incremental(c0→c1→c2)` e `full(c2)` produzem o mesmo conjunto de `fragment_key` e o mesmo manifesto.
- TC-INC-05 Processo morto no meio → próxima execução marca a anterior `aborted` e a revisão anterior continua sendo a consultada.

---

## CTR-04 — Atualização e remoção de documentos

**Entradas:** manifesto de `base` e de `target`.
**Saída:** delta `{ added[], modified[], deleted[], renamed_inferred[] }` gravado no `ingest_run` e refletido no manifesto de `target`.

**Invariantes**
1. Artefato ausente em `target` não aparece em nenhuma busca sobre `target`.
2. As versões e fragmentos de `base` permanecem enquanto `base` estiver `retained`; consultas fixadas em `base` continuam funcionando.
3. Renomeação = remoção + inclusão. A ligação vai para `artifact_lineage` com `method` e `similarity`, rotulada como inferida. Nenhuma citação herda a identidade antiga.
4. Arquivo que passa de `eligible` a `excluded` (ex.: cresceu além do limite) sai das buscas de `target` e registra o motivo.
5. Remoção física de dados antigos só acontece pelo `gc` explícito, que apaga revisões `retained=0` e versões órfãs, nessa ordem.

**Falhas esperadas:** `E_MANIFEST_MISSING`, `E_GC_REFERENCED` (tentativa de apagar versão ainda referenciada).

**Testes de contrato**
- TC-UPD-01 Arquivo apagado em `target` → zero resultados em `target`, resultados intactos em `base`.
- TC-UPD-02 `git mv a.md b.md` → busca em `target` retorna `b.md`; `artifact_lineage` tem `a→b` com `method=git-rename-detect`.
- TC-UPD-03 Arquivo que cruza `max_bytes` → `excluded/too_large` em `target`.
- TC-UPD-04 `gc` com `base` retida → nada apagado; com `base` liberada → versões órfãs apagadas, FTS consistente.
- TC-UPD-05 Busca por `fragment_key` de versão removida pelo `gc` → `E_FRAGMENT_GONE` (nunca um resultado vazio silencioso).

---

## CTR-05 — Reconstrução integral dos índices

**Entradas:** lista de `(repo_name, commit_oid)` retidas, `Policy`, perfis. Origem preferencial: o próprio `index.sqlite` antigo ou um arquivo de manifesto exportado (`kos export-manifest`).
**Saída:** `index.sqlite` novo, construído em arquivo temporário e trocado atomicamente; relatório de diferenças contra o antigo.

**Invariantes**
1. Não depende de nada além do Git e das entradas declaradas (REQ-01). Apagar `index.sqlite` e rodar `rebuild` é sempre permitido.
2. Determinismo: mesmas entradas → mesmos `fragment_key`, mesmos manifestos, mesmo conteúdo FTS (RNF-02). IDs `INTEGER` podem diferir; nada fora do índice depende deles.
3. `audit.sqlite` não é lido para construir nem alterado.
4. Se o rebuild falhar, o índice antigo continua em uso.
5. O relatório lista fragmentos adicionados/removidos por perfil quando a versão de parser mudou.

**Falhas esperadas:** `E_COMMIT_NOT_FOUND` (commit retido sumiu do Git, ex.: após force-push): o rebuild segue com as demais revisões e marca a ausente; `E_DISK_FULL`.

**Testes de contrato**
- TC-REB-01 Apagar o índice, reconstruir, rodar o benchmark → mesmos resultados de recuperação (mesmas chaves, mesma ordem para empates resolvidos por `fragment_key`).
- TC-REB-02 Dois rebuilds independentes → dump lógico ordenado idêntico (exceto IDs inteiros e carimbos de tempo).
- TC-REB-03 Commit retido ausente → rebuild `partial` com erro registrado; demais revisões íntegras.

---

## CTR-06 — Recuperação de evidências

**Entradas:** `{ query_text, revision? (padrão: última consultável da branch configurada), k, filters{ repo, path_glob, kind[], language[], include_generated=false } }`.
**Saída:** `{ revision: RepoRef, results: [{ rank, fragment_key, score, path_text, artifact_kind, Locator, snippet, text_sha256 }], diagnostics: { parsed_query, total_hits, latency_ms } }`.

**Invariantes**
1. Todo resultado pertence a uma versão presente no manifesto da revisão consultada.
2. Ordenação determinística: `bm25()` com pesos de coluna declarados; empate desempata por `fragment_key`.
3. A consulta do usuário é escapada antes de virar expressão FTS5 (sem injeção de sintaxe `NEAR`, `*`, `:`, aspas).
4. A recuperação não chama LLM e não reescreve a pergunta por modelo no MVP.
5. Resultado vazio é um resultado válido (`results=[]`), não um erro.
6. Arquivos gerados ficam fora por padrão; quando incluídos, vêm marcados.

**Falhas esperadas:** `E_NO_INDEXED_REVISION`, `E_REVISION_NOT_INDEXED`, `E_QUERY_EMPTY`, `E_FILTER_INVALID`.

**Testes de contrato**
- TC-RET-01 Termo exato presente em um único fragmento → rank 1.
- TC-RET-02 Termo sem acento casa com texto acentuado ("apresentacao" → "apresentação").
- TC-RET-03 Busca por `gen portfolio` encontra o símbolo `genPortfolio`/`gen-portfolio`.
- TC-RET-04 Entrada com `"`, `*`, `NEAR(` e `:` não gera erro de sintaxe nem muda o operador.
- TC-RET-05 Resultado nunca vem de versão fora do manifesto (propriedade sobre o fixture de histórico).
- TC-RET-06 Contagem de linhas de `fragment` = contagem indexada no FTS após cada ingestão.

---

## CTR-07 — Montagem de citações

**Entradas:** `fragment_key` (ou lista) e opcionalmente um sub-intervalo dentro do fragmento.
**Saída:** `Citation = { citation_no, repo_name, path_text, commit_oid, blob_oid, Locator, quoted_text, quoted_sha256, verification, verification_note? }`.

Formato humano canônico (CLI):

```text
[1] mauricio-site:AGENTS.md#L121 @73570bbc9b99 (verified_exact)
    "e um piso de contraste de **7:1** na Camada 3."
```

**Invariantes**
1. `commit_oid` é sempre o hex completo no JSON; a forma humana pode abreviar a 12 caracteres, nunca menos.
2. Verificação no momento da montagem: o blob é relido do Git pelo `blob_oid`; `verified_exact` só se `sha256(normalize(blob[start:end])) == quoted_sha256`.
3. Se o blob não puder ser lido (revisão podada, repositório ausente), `verification = unverified` e a CLI imprime o rótulo **"não verificada"**. Nunca há omissão do rótulo.
4. Linhas derivadas de bytes sem releitura = `derived`. Página do Docling e fragmento HTML (texto visível) = no máximo `verified_normalized`.
5. O trecho citado é um recorte literal do texto do fragmento, nunca uma paráfrase. Recortes podem ser encurtados com `…` explícito, mantendo `quoted_sha256` do trecho inteiro.
6. Citações apontam para a fonte, nunca para o arquivo gerado quando a fonte estiver no mesmo índice (ex.: `public/x.md` em vez de `public/en/x.md`), salvo pedido explícito.

**Falhas esperadas:** `E_FRAGMENT_GONE`, `E_BLOB_UNREADABLE` (vira `unverified`, não exceção para o usuário), `E_SUBRANGE_OUT_OF_BOUNDS`.

**Testes de contrato**
- TC-CIT-01 Citação de fragmento Markdown → todos os campos preenchidos, `verified_exact`.
- TC-CIT-02 Citação de JSON → `struct_path` e linhas corretas.
- TC-CIT-03 Blob alterado artificialmente no fixture → `unverified` com nota; saída humana contém "não verificada".
- TC-CIT-04 Fragmento de PDF via Docling → `page_start` presente, `verified_normalized`, sem linhas.
- TC-CIT-05 Nenhuma citação em nenhum caso de teste tem `verification` ausente (propriedade).
- TC-CIT-06 Commit abreviado em JSON é rejeitado pela validação de esquema.

---

## CTR-08 — Geração de respostas fundamentadas

**Entradas:** `query_text`, resultado de CTR-06, modo `extractive|llm`, limiares de suficiência (CTR-09).
**Saída:** `Answer = { outcome: answered|answered_with_conflict|abstained, claims: [{ claim_id, text, citation_nos[] }], citations: Citation[], conflicts?: [{ topic, sides: [{ claim_id, citation_nos[] }] }], abstention?: Abstention }`.

**Invariantes**
1. Toda `claim` tem ≥ 1 citação com `verification ∈ {verified_exact, verified_normalized}`. Afirmação sem isso é removida antes da saída, e a remoção é registrada.
2. Modo `extractive` (padrão, sem LLM): as afirmações são os próprios trechos citados, agrupados por artefato e ordenados por rank.
3. Modo `llm`: o adaptador recebe só os fragmentos recuperados e devolve afirmações com referências a eles; o validador confere cada referência e aplica a regra 1. O modelo nunca recebe acesso ao repositório nem ao índice.
4. Quando dois fragmentos sustentam afirmações incompatíveis sobre o mesmo tópico, `outcome = answered_with_conflict` e ambos os lados são apresentados, com escopo (caminho, data do commit, tipo de artefato). Não há escolha de vencedor sem regra explícita declarada na política (Q-11).
5. A resposta registra a revisão consultada e o modo; nada é gerado sem `query_event` gravado.
6. Com o adaptador desligado, pedir `llm` retorna `E_LLM_DISABLED`, não cai em silêncio para outro modo.

**Falhas esperadas:** `E_LLM_DISABLED`, `E_LLM_TIMEOUT`, `E_LLM_INVALID_OUTPUT` (resposta sem referências válidas → tratada como abstenção `llm_unsupported_output`).

**Testes de contrato**
- TC-ANS-01 Modo extrativo em GS-SPEC-001 → afirmação com citação `verified_exact` de `AGENTS.md`.
- TC-ANS-02 LLM simulado (dublê determinístico) que inventa uma afirmação sem referência → afirmação removida e registrada.
- TC-ANS-03 LLM simulado que cita `fragment_key` não recuperado → rejeitado.
- TC-ANS-04 GS-CONF-002 → `answered_with_conflict` com os dois lados.
- TC-ANS-05 Adaptador desligado + `--mode llm` → `E_LLM_DISABLED`; nenhuma chamada de rede (verificada por dublê de transporte).

---

## CTR-09 — Abstenção

**Entradas:** resultado de CTR-06, afirmações candidatas, limiares `{ min_hits, min_top_score?, min_verified_citations, require_term_coverage }`.
**Saída:** `Abstention = { code, message, searched: { revision, query_parsed, filters, total_hits }, nearest: Citation[0..3] }`.

Códigos fechados:

| Código | Quando |
|---|---|
| `no_hits` | Recuperação vazia. |
| `insufficient_evidence` | Há resultados, mas nenhum cobre os termos essenciais da pergunta ou nenhum passa no limiar. |
| `unverifiable_evidence` | Os resultados existem, mas nenhuma citação passou na verificação. |
| `revision_unavailable` | A revisão pedida não está indexada. |
| `out_of_scope` | Pergunta sobre algo que a política exclui (ex.: binários, repositório não registrado). |
| `llm_unsupported_output` | O LLM não produziu afirmação com suporte válido. |

**Invariantes**
1. Abstenção não é erro de execução: código de saída da CLI distinto de falha (CTR-10).
2. `nearest` mostra até 3 evidências próximas, rotuladas como "relacionadas, não respondem", para o usuário conferir.
3. Os limiares iniciais são **provisórios** e calibrados pelo benchmark (`04-benchmark.md` §6). Não há valor numérico fixado nesta fase.
4. Abstenção parcial é permitida: responder as partes sustentadas e declarar explicitamente as partes sem suporte.

**Testes de contrato**
- TC-ABS-01 GS-ABS-001 → `no_hits` ou `insufficient_evidence`, nunca `answered`.
- TC-ABS-02 GS-ABS-002 → abstenção sobre o valor medido; `nearest` contém a meta declarada rotulada como meta.
- TC-ABS-03 Revisão não indexada → `revision_unavailable`.
- TC-ABS-04 Todas as citações `unverified` → `unverifiable_evidence`.
- TC-ABS-05 Pergunta composta com uma parte sustentada e outra não → resposta parcial + declaração da lacuna.

---

## CTR-10 — Registro de erros e auditoria

**Entradas:** eventos de todas as etapas.
**Saída:** linhas em `processing_error`, `ingest_run` (`index.sqlite`) e em `query_event`, `retrieval_result`, `answer_record`, `citation_record` (`audit.sqlite`); log estruturado JSON Lines opcional em `stderr`.

**Catálogo de erros (inicial):** `E_REPO_NOT_FOUND, E_COMMIT_NOT_FOUND, E_GIT_UNAVAILABLE, E_POLICY_INVALID, E_DECODE, E_PARSE_SYNTAX, E_PARSER_UNAVAILABLE, E_TIMEOUT_PARSE, E_TOO_MANY_FRAGMENTS, E_BASE_NOT_INDEXED, E_BASE_NOT_ANCESTOR, E_LOCKED, E_DISK_FULL, E_ABORTED, E_MANIFEST_MISSING, E_GC_REFERENCED, E_FRAGMENT_GONE, E_BLOB_UNREADABLE, E_SUBRANGE_OUT_OF_BOUNDS, E_NO_INDEXED_REVISION, E_REVISION_NOT_INDEXED, E_QUERY_EMPTY, E_FILTER_INVALID, E_LLM_DISABLED, E_LLM_TIMEOUT, E_LLM_INVALID_OUTPUT, E_FTS5_UNAVAILABLE, E_SCHEMA_MISMATCH, E_STORE_UNWRITABLE`. Novo código exige atualização deste contrato. (Os três últimos foram acrescentados no BL-01, para o `kos init`: SQLite sem FTS5 (Q-06), banco existente com outra versão de esquema e diretório do índice sem permissão de escrita.)

**Códigos de saída da CLI:** `0` sucesso/resposta, `3` abstenção, `4` sucesso parcial (ingestão `partial`), `1` erro de uso, `2` erro de execução. **[ABERTO] Q-12** se 3 e 4 atrapalham scripts.

**Invariantes**
1. Toda consulta gera `query_event` antes de qualquer resposta.
2. Auditoria guarda texto citado e identificadores Git; não guarda conteúdo integral de arquivos.
3. Mensagens de erro não incluem conteúdo de arquivo além de 200 caracteres de contexto.
4. Nenhum log é enviado a serviço externo (RNF-01).
5. Toda execução de ingestão termina com status final, inclusive após falha (marcada na próxima execução, CTR-03 inv. 5).

**Testes de contrato**
- TC-AUD-01 Cada comando `ask`/`search` gera exatamente um `query_event`.
- TC-AUD-02 `rebuild` não altera o hash de `audit.sqlite`.
- TC-AUD-03 Erro de parsing → linha em `processing_error` com `stage`, `error_code`, `path_text`.
- TC-AUD-04 Erro com código fora do catálogo falha o teste (lista fechada).
- TC-AUD-05 Citação auditada continua verificável após apagar o índice (releitura direta do blob no Git).
