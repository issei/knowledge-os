-- Gerado a partir de docs/fase-0/02-modelo-de-dados.md §5. Mantenha os dois em sincronia
-- (tests/unit/test_schema.py compara tabelas e colunas).
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE audit_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
); -- schema_version, created_by_tool_version (acrescentada no BL-01)

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
