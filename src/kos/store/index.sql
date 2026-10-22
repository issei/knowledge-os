-- Gerado a partir de docs/fase-0/02-modelo-de-dados.md §4. Mantenha os dois em sincronia
-- (tests/unit/test_schema.py compara tabelas e colunas).
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
