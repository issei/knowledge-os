---
id: KOS-F0-DM
titulo: Fase 0B — Modelo de dados SQLite
status: rascunho para aprovação
data: 2026-10-21
requisitos: [REQ-01, REQ-02, REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-12, RNF-02, RNF-05]
adrs: [ADR-kos-001, ADR-kos-002, ADR-kos-003, ADR-kos-004]
---

# Fase 0B — Modelo de dados SQLite

O DDL abaixo é **proposta de especificação**, não implementação. Foi escrito para SQLite ≥ 3.45 com FTS5 (versão e FTS5 confirmadas no ambiente desta inspeção; a versão na máquina de Issei é **[ABERTO] Q-06**).

## 1. Três identidades distintas

| Identidade | O que é | Chave | Muda quando |
|---|---|---|---|
| **Lógica** (`artifact`) | "O arquivo `docs/x.md` do repositório R", independente de conteúdo. | `artifact_id` substituto + único `(repo_id, path_bytes)` | Nunca. Renomear cria outra identidade lógica; a ligação entre as duas é registrada em `artifact_lineage` como relação **inferida**. |
| **Versão** (`artifact_version`) | Um conteúdo concreto daquele arquivo, endereçado pelo blob Git. | `version_id` substituto + único `(artifact_id, blob_oid)` | Quando o blob muda. Commits que não mexem no arquivo reaproveitam a mesma versão. |
| **Fragmento** (`fragment`) | Uma unidade indexável extraída de uma versão por um perfil de processamento. | `fragment_key` = SHA-256 de `blob_oid ‖ profile_fingerprint ‖ locator_canônico` | Quando o conteúdo, o perfil (parser, versão, configuração) ou o recorte mudam. |

Consequências:

- A presença de uma versão numa revisão fica em `revision_manifest`, não na versão. Isso evita duplicar conteúdo por commit.
- `fragment_key` é **determinística**: reconstruir o índice gera as mesmas chaves (RNF-02). O benchmark e o log de auditoria referenciam `fragment_key`, não `rowid`.
- Mesmo texto em versões diferentes tem `fragment_key` diferente, mas o mesmo `text_sha256`. Isso permite dizer "o trecho continua igual na revisão nova" sem confundir as identidades.

## 2. Dois arquivos de banco

| Arquivo | Conteúdo | Pode ser apagado? |
|---|---|---|
| `index.sqlite` | Tudo que é derivado do Git: revisões, artefatos, versões, fragmentos, localizadores, símbolos, FTS, execuções e erros de processamento. | **Sim.** É reconstruível (REQ-01). |
| `audit.sqlite` | Consultas, resultados, respostas, citações e abstenções. | **Não** como parte do rebuild. Política de retenção é **[ABERTO] Q-09**. |

Separar os arquivos impede que um `rebuild` apague a trilha de auditoria (REQ-12) e deixa claro o que é derivado. A auditoria guarda o texto citado e os identificadores Git, então continua verificável mesmo se o índice for apagado.

## 3. Representação de localizações

Os formatos não têm a mesma estrutura, então o localizador é polimórfico, com uma regra comum: **todo localizador de formato textual tem intervalo de bytes**, porque é o único recorte que se confere contra o blob sem interpretação. As demais formas são derivadas ou complementares.

| Formato | Localizador primário | Complementos | Observação |
|---|---|---|---|
| Markdown, texto | `byte_range` | linhas (1-based, inclusivo), `heading_path` | Linhas derivadas dos bytes; quebra de linha normalizada só no texto indexado, nunca nos offsets. |
| YAML | `byte_range` | `struct_path` (ex.: `$.navigation[2].nodes`) | Ponteiro só quando o parser fornecer posição; senão, só bytes. |
| JSON | `byte_range` | `struct_path` em JSON Pointer (RFC 6901) | Idem. |
| Código | `byte_range` | linhas, `symbol_id` | Símbolo vem do Tree-sitter com versão da gramática. |
| HTML (se aprovado, Q-05) | `byte_range` | linhas, seletor estrutural | Texto extraído perde marcação; offsets apontam para o original. |
| PDF/DOCX via Docling | `page_range` | bloco/ordem na página, `bbox` opcional | **Sem bytes do original.** Verificação é por texto normalizado na página extraída; estado máximo é `verified_normalized`, nunca `verified_exact`. |

Estados de verificação de um localizador (usados também nas citações, `03-contratos.md` CTR-07):

| Estado | Significado |
|---|---|
| `verified_exact` | Os bytes do intervalo no blob, lidos de novo, têm o `text_sha256` registrado. |
| `verified_normalized` | O texto normalizado da página/bloco extraído confere; não há offsets no original. |
| `derived` | Localização calculada (ex.: linha a partir de bytes) sem nova leitura. Pode ser exibida, com o rótulo. |
| `unverified` | Não foi possível conferir (blob ausente, revisão podada, erro). **Nunca** exibida como verificada. |

## 4. DDL proposto (`index.sqlite`)

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- Metadados do próprio índice
CREATE TABLE index_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
); -- schema_version, created_by_tool_version, eligibility_policy_sha256

CREATE TABLE repository (
  repo_id        INTEGER PRIMARY KEY,
  name           TEXT NOT NULL UNIQUE,      -- nome lógico estável escolhido no registro
  origin_url     TEXT,                      -- informativo; nunca usado como identidade
  object_format  TEXT NOT NULL DEFAULT 'sha1' CHECK (object_format IN ('sha1','sha256')),
  registered_at  TEXT NOT NULL
);

CREATE TABLE source_revision (
  revision_id    INTEGER PRIMARY KEY,
  repo_id        INTEGER NOT NULL REFERENCES repository(repo_id),
  commit_oid     TEXT NOT NULL,             -- hex completo, nunca abreviado
  tree_oid       TEXT NOT NULL,
  committed_at   TEXT NOT NULL,             -- data do committer, ISO-8601 UTC
  ref_name       TEXT,                      -- ex.: refs/heads/main no momento da ingestão (informativo)
  retained       INTEGER NOT NULL DEFAULT 1 CHECK (retained IN (0,1)),
  UNIQUE (repo_id, commit_oid)
);

CREATE TABLE artifact (
  artifact_id    INTEGER PRIMARY KEY,
  repo_id        INTEGER NOT NULL REFERENCES repository(repo_id),
  path_bytes     BLOB NOT NULL,             -- caminho Git exato
  path_text      TEXT NOT NULL,             -- UTF-8 NFC para exibição; marca U+FFFD se não decodificar
  path_is_utf8   INTEGER NOT NULL CHECK (path_is_utf8 IN (0,1)),
  artifact_kind  TEXT NOT NULL,             -- doc|spec|adr|code|test|config|data|generated|other
  kind_rule      TEXT NOT NULL,             -- regra da política que classificou (auditável)
  UNIQUE (repo_id, path_bytes)
);
CREATE INDEX ix_artifact_path ON artifact(repo_id, path_text);

CREATE TABLE artifact_lineage (            -- renomeações: relação INFERIDA
  from_artifact_id INTEGER NOT NULL REFERENCES artifact(artifact_id),
  to_artifact_id   INTEGER NOT NULL REFERENCES artifact(artifact_id),
  revision_id      INTEGER NOT NULL REFERENCES source_revision(revision_id),
  method           TEXT NOT NULL,           -- ex.: git-rename-detect
  similarity       INTEGER,                 -- 0..100 informado pelo git
  PRIMARY KEY (from_artifact_id, to_artifact_id, revision_id),
  CHECK (from_artifact_id <> to_artifact_id)
);

CREATE TABLE artifact_version (
  version_id     INTEGER PRIMARY KEY,
  artifact_id    INTEGER NOT NULL REFERENCES artifact(artifact_id),
  blob_oid       TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  byte_size      INTEGER NOT NULL CHECK (byte_size >= 0),
  media_type     TEXT NOT NULL,             -- detectado pela política, não pela extensão apenas
  text_encoding  TEXT,                      -- NULL se binário
  line_ending    TEXT CHECK (line_ending IN ('lf','crlf','mixed','none')),
  is_generated   INTEGER NOT NULL DEFAULT 0 CHECK (is_generated IN (0,1)),
  UNIQUE (artifact_id, blob_oid)
);
CREATE INDEX ix_version_blob ON artifact_version(blob_oid);

-- Qual versão de cada artefato está em cada revisão indexada
CREATE TABLE revision_manifest (
  revision_id    INTEGER NOT NULL REFERENCES source_revision(revision_id) ON DELETE CASCADE,
  artifact_id    INTEGER NOT NULL REFERENCES artifact(artifact_id),
  version_id     INTEGER NOT NULL REFERENCES artifact_version(version_id),
  file_mode      TEXT NOT NULL,             -- 100644|100755|120000(symlink)
  eligibility    TEXT NOT NULL CHECK (eligibility IN ('eligible','excluded')),
  exclusion_rule TEXT,                      -- obrigatório quando excluded
  PRIMARY KEY (revision_id, artifact_id),
  CHECK ((eligibility = 'excluded') = (exclusion_rule IS NOT NULL))
);
CREATE INDEX ix_manifest_version ON revision_manifest(version_id);

CREATE TABLE processing_profile (
  profile_id          INTEGER PRIMARY KEY,
  profile_name        TEXT NOT NULL,        -- md-native|yaml-native|json-native|text-plain|ts-<lang>|docling
  parser_name         TEXT NOT NULL,
  parser_version      TEXT NOT NULL,
  grammar_version     TEXT,                 -- Tree-sitter: versão/commit da gramática
  normalizer_version  TEXT NOT NULL,
  config_json         TEXT NOT NULL,        -- JSON canônico (chaves ordenadas)
  profile_fingerprint TEXT NOT NULL UNIQUE  -- sha256 de todos os campos acima
);

CREATE TABLE ingest_run (
  run_id              INTEGER PRIMARY KEY,
  run_uuid            TEXT NOT NULL UNIQUE,
  repo_id             INTEGER NOT NULL REFERENCES repository(repo_id),
  mode                TEXT NOT NULL CHECK (mode IN ('full','incremental','rebuild','gc')),
  base_revision_id    INTEGER REFERENCES source_revision(revision_id),
  target_revision_id  INTEGER NOT NULL REFERENCES source_revision(revision_id),
  policy_sha256       TEXT NOT NULL,
  tool_version        TEXT NOT NULL,
  started_at          TEXT NOT NULL,
  finished_at         TEXT,
  status              TEXT NOT NULL CHECK (status IN ('running','succeeded','partial','failed','aborted')),
  counts_json         TEXT,                 -- descobertos, processados, reaproveitados, falhos, removidos
  CHECK (mode <> 'incremental' OR base_revision_id IS NOT NULL)
);

-- Resultado de processar UMA versão com UM perfil (cache entre execuções)
CREATE TABLE version_processing (
  version_id     INTEGER NOT NULL REFERENCES artifact_version(version_id),
  profile_id     INTEGER NOT NULL REFERENCES processing_profile(profile_id),
  status         TEXT NOT NULL CHECK (status IN ('parsed','parsed_with_warnings','skipped','failed')),
  reason_code    TEXT,                      -- obrigatório quando skipped/failed
  first_run_id   INTEGER NOT NULL REFERENCES ingest_run(run_id),
  last_run_id    INTEGER NOT NULL REFERENCES ingest_run(run_id),
  fragment_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (version_id, profile_id),
  CHECK (status IN ('parsed','parsed_with_warnings') OR reason_code IS NOT NULL)
);

CREATE TABLE fragment (
  fragment_id    INTEGER PRIMARY KEY,       -- rowid; usado só pelo FTS
  fragment_key   TEXT NOT NULL UNIQUE,      -- identidade estável (ver §1)
  version_id     INTEGER NOT NULL REFERENCES artifact_version(version_id),
  profile_id     INTEGER NOT NULL REFERENCES processing_profile(profile_id),
  ordinal        INTEGER NOT NULL CHECK (ordinal >= 0),
  fragment_kind  TEXT NOT NULL,             -- section|paragraph|list|table|code_block|symbol|yaml_node|json_node|page_block|test_case
  heading_path   TEXT,                      -- "H1 > H2 > H3"
  text           TEXT NOT NULL,             -- texto normalizado indexado
  ident_terms    TEXT,                      -- identificadores divididos (camelCase/snake_case) para busca de código
  text_sha256    TEXT NOT NULL,
  UNIQUE (version_id, profile_id, ordinal)
);

CREATE TABLE fragment_locator (
  fragment_id    INTEGER PRIMARY KEY REFERENCES fragment(fragment_id) ON DELETE CASCADE,
  locator_type   TEXT NOT NULL CHECK (locator_type IN ('text','structured','code','page')),
  start_byte     INTEGER, end_byte INTEGER,   -- [start, end) no blob original
  start_line     INTEGER, end_line INTEGER,   -- 1-based, inclusivo
  start_col      INTEGER, end_col INTEGER,
  struct_path    TEXT,                        -- JSON Pointer / caminho YAML
  page_start     INTEGER, page_end INTEGER,   -- 1-based, só locator_type='page'
  symbol_id      INTEGER REFERENCES symbol(symbol_id),
  CHECK (locator_type = 'page' OR (start_byte IS NOT NULL AND end_byte IS NOT NULL AND start_byte <= end_byte)),
  CHECK (locator_type <> 'page' OR (page_start IS NOT NULL AND page_end >= page_start)),
  CHECK (start_line IS NULL OR end_line >= start_line)
);

CREATE TABLE symbol (
  symbol_id        INTEGER PRIMARY KEY,
  version_id       INTEGER NOT NULL REFERENCES artifact_version(version_id),
  profile_id       INTEGER NOT NULL REFERENCES processing_profile(profile_id),
  language         TEXT NOT NULL,
  symbol_kind      TEXT NOT NULL,           -- function|class|method|const|export|test|...
  name             TEXT NOT NULL,
  qualified_name   TEXT NOT NULL,           -- escopo léxico, ex.: gen-portfolio.mjs::fill
  parent_symbol_id INTEGER REFERENCES symbol(symbol_id),
  start_byte       INTEGER NOT NULL, end_byte INTEGER NOT NULL,
  start_line       INTEGER NOT NULL, end_line INTEGER NOT NULL,
  signature        TEXT,
  UNIQUE (version_id, profile_id, qualified_name, start_byte)
);
CREATE INDEX ix_symbol_name ON symbol(name);

CREATE TABLE processing_error (
  error_id     INTEGER PRIMARY KEY,
  run_id       INTEGER NOT NULL REFERENCES ingest_run(run_id),
  stage        TEXT NOT NULL CHECK (stage IN ('discover','read','decode','parse','normalize','index','verify','commit')),
  artifact_id  INTEGER REFERENCES artifact(artifact_id),
  version_id   INTEGER REFERENCES artifact_version(version_id),
  path_text    TEXT,
  error_code   TEXT NOT NULL,               -- catálogo fechado (CTR-10)
  severity     TEXT NOT NULL CHECK (severity IN ('warning','error','fatal')),
  message      TEXT NOT NULL,
  detail_json  TEXT,
  created_at   TEXT NOT NULL
);
CREATE INDEX ix_error_run ON processing_error(run_id, severity);

-- FTS5 com conteúdo externo
CREATE VIRTUAL TABLE fragment_fts USING fts5(
  text, heading_path, ident_terms,
  content='fragment', content_rowid='fragment_id',
  tokenize = "unicode61 remove_diacritics 2"
);
```

A sincronização `fragment` → `fragment_fts` é feita na mesma transação que grava os fragmentos (inserção explícita ou gatilhos; escolha de implementação na Fase 1, coberta por TC-RET-06).

## 5. Tabelas de `audit.sqlite`

```sql
CREATE TABLE query_event (
  query_id        TEXT PRIMARY KEY,         -- UUID
  asked_at        TEXT NOT NULL,
  interface       TEXT NOT NULL CHECK (interface IN ('cli','mcp','bench')),
  question        TEXT NOT NULL,
  params_json     TEXT NOT NULL,            -- k, filtros, revisão pedida, modo de resposta
  index_fingerprint TEXT NOT NULL,          -- hash de (schema, perfis, revisões) do índice consultado
  tool_version    TEXT NOT NULL
);
CREATE TABLE retrieval_result (
  query_id      TEXT NOT NULL REFERENCES query_event(query_id),
  rank          INTEGER NOT NULL CHECK (rank >= 1),
  fragment_key  TEXT NOT NULL,
  score         REAL NOT NULL,
  PRIMARY KEY (query_id, rank)
);
CREATE TABLE answer_record (
  query_id      TEXT PRIMARY KEY REFERENCES query_event(query_id),
  outcome       TEXT NOT NULL CHECK (outcome IN ('answered','answered_with_conflict','abstained','error')),
  mode          TEXT NOT NULL CHECK (mode IN ('extractive','llm')),
  abstention_code TEXT,
  answer_text   TEXT,
  llm_adapter_json TEXT,                    -- provedor, modelo, local/remoto; NULL no modo extrativo
  CHECK ((outcome = 'abstained') = (abstention_code IS NOT NULL))
);
CREATE TABLE citation_record (
  query_id        TEXT NOT NULL REFERENCES query_event(query_id),
  citation_no     INTEGER NOT NULL,
  claim_ids       TEXT NOT NULL,            -- JSON: afirmações que esta citação sustenta
  repo_name       TEXT NOT NULL,
  path_text       TEXT NOT NULL,
  commit_oid      TEXT NOT NULL,
  blob_oid        TEXT NOT NULL,
  locator_json    TEXT NOT NULL,
  quoted_text     TEXT NOT NULL,
  quoted_sha256   TEXT NOT NULL,
  verification    TEXT NOT NULL CHECK (verification IN ('verified_exact','verified_normalized','derived','unverified')),
  PRIMARY KEY (query_id, citation_no)
);
```

## 6. Finalidade, chaves, índices e atualização por tabela

| Tabela | Finalidade | PK | FKs | Índices / restrições | Estratégia de atualização |
|---|---|---|---|---|---|
| `index_meta` | Versão de esquema e política do índice | `key` | — | — | Escrita no `init` e no `rebuild`; migração de esquema = rebuild no MVP (Q-07). |
| `repository` | Repositórios registrados | `repo_id` | — | `UNIQUE(name)` | Inserção no `register`; `origin_url` atualizável. Nunca removido no MVP. |
| `source_revision` | Commits indexados | `revision_id` | `repo_id` | `UNIQUE(repo_id, commit_oid)` | Append-only. `retained=0` marca para `gc`; o `gc` apaga em cascata o manifesto. |
| `artifact` | Identidade lógica | `artifact_id` | `repo_id` | `UNIQUE(repo_id, path_bytes)`, índice por `path_text` | Inserção na primeira descoberta. `artifact_kind` recalculado se a política mudar (gera nova `policy_sha256`). |
| `artifact_lineage` | Renomeações inferidas | composta | 2× `artifact`, `revision` | `CHECK from<>to` | Append-only; sempre rotulada como inferida. |
| `artifact_version` | Conteúdo concreto | `version_id` | `artifact_id` | `UNIQUE(artifact_id, blob_oid)`, índice por `blob_oid` | Imutável. Removida só pelo `gc` quando nenhuma revisão retida a referencia. |
| `revision_manifest` | Presença de versões por revisão; base dos filtros de busca | `(revision_id, artifact_id)` | revisão, artefato, versão | `CHECK` excluded ⇔ regra; índice por `version_id` | Escrito inteiro por execução, por revisão. Imutável depois de `succeeded`. |
| `processing_profile` | Parser + versão + configuração | `profile_id` | — | `UNIQUE(profile_fingerprint)` | Imutável. Mudar qualquer campo cria perfil novo e invalida o cache. |
| `ingest_run` | Execuções | `run_id` | repo, 2× revisão | `CHECK` incremental ⇒ base | Inserida em `running`; status final gravado ao fim. Execução interrompida fica `running` e é marcada `aborted` na próxima. |
| `version_processing` | Cache e estado por (versão, perfil) | `(version_id, profile_id)` | versão, perfil, 2× run | `CHECK` falha ⇒ motivo | Upsert: atualiza `last_run_id`; reprocessa só se `failed` e a política pedir retry. |
| `fragment` | Unidade indexável | `fragment_id` + `UNIQUE(fragment_key)` | versão, perfil | `UNIQUE(version_id, profile_id, ordinal)` | Imutável; gravado em lote na mesma transação de `version_processing`. |
| `fragment_locator` | Localizador verificável | `fragment_id` | fragmento, símbolo | `CHECK` por tipo | Imutável, junto com o fragmento. |
| `symbol` | Símbolos de código | `symbol_id` | versão, perfil, pai | `UNIQUE(version, profile, qualified_name, start_byte)`, índice por `name` | Imutável. |
| `processing_error` | Erros e avisos | `error_id` | run, artefato, versão | índice `(run_id, severity)` | Append-only. |
| `fragment_fts` | Busca textual | rowid = `fragment_id` | — | tokenizador `unicode61 remove_diacritics 2` | Sincronizado na transação do fragmento; `rebuild` total via comando `'rebuild'` do FTS5. |
| `audit.*` | Trilha de consultas e respostas | ver DDL | só internas ao `audit.sqlite` | `CHECK` abstenção ⇔ código | Append-only. Nunca tocado por `rebuild`. |

## 7. Decisões de modelagem e alternativas descartadas

- **Revisões sem duplicar conteúdo.** A alternativa "uma linha de fragmento por commit" multiplicaria o índice pelo número de commits. O manifesto por revisão mais versões por blob mantém o custo proporcional às mudanças.
- **Quais revisões indexar.** MVP: a ponta de uma branch configurada e as revisões fixadas pelo benchmark. Histórico completo fica fora (Q-04).
- **Busca restrita a uma revisão.** Toda consulta resolve uma revisão (padrão: a última `succeeded` da branch configurada) e filtra por `revision_manifest`. Sem isso, versões antigas competiriam com as atuais.
- **Tokenização.** `unicode61 remove_diacritics 2` trata acentos do PT-BR (ex.: "apresentação" casa com "apresentacao"). Identificadores de código vão divididos em `ident_terms` para que `genPortfolio` case com "gen portfolio". Um segundo índice `trigram` para substring fica como opção medida pelo benchmark, não como padrão.
- **Arquivos gerados.** Ficam indexados com `is_generated=1` e `artifact_kind='generated'`; a recuperação os rebaixa ou filtra por padrão (política em CTR-01). Ex.: `src/en/**` no corpus C0.
- **Sem colunas de embedding.** Nenhuma tabela reserva espaço para vetores (RNF-06, ADR-kos-008).
