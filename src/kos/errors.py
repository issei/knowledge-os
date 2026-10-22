"""Catálogo fechado de erros e códigos de saída (CTR-10).

Um código novo exige atualizar docs/fase-0/03-contratos.md (CTR-10). O teste
tests/unit/test_errors.py compara este catálogo com o do contrato.
"""

ERROR_CODES = frozenset({
    "E_REPO_NOT_FOUND", "E_COMMIT_NOT_FOUND", "E_GIT_UNAVAILABLE", "E_POLICY_INVALID",
    "E_DECODE", "E_PARSE_SYNTAX", "E_PARSER_UNAVAILABLE", "E_TIMEOUT_PARSE",
    "E_TOO_MANY_FRAGMENTS", "E_BASE_NOT_INDEXED", "E_BASE_NOT_ANCESTOR", "E_LOCKED",
    "E_DISK_FULL", "E_ABORTED", "E_MANIFEST_MISSING", "E_GC_REFERENCED",
    "E_FRAGMENT_GONE", "E_BLOB_UNREADABLE", "E_SUBRANGE_OUT_OF_BOUNDS",
    "E_NO_INDEXED_REVISION", "E_REVISION_NOT_INDEXED", "E_QUERY_EMPTY",
    "E_FILTER_INVALID", "E_LLM_DISABLED", "E_LLM_TIMEOUT", "E_LLM_INVALID_OUTPUT",
    "E_FTS5_UNAVAILABLE", "E_SCHEMA_MISMATCH", "E_STORE_UNWRITABLE", "E_SUITE_INVALID",
})

# Códigos de saída da CLI (CTR-10).
EXIT_OK = 0
EXIT_USAGE = 1
EXIT_EXECUTION = 2
EXIT_ABSTAINED = 3
EXIT_PARTIAL = 4


class KosError(Exception):
    """Erro de execução com código do catálogo."""

    def __init__(self, code: str, message: str):
        if code not in ERROR_CODES:
            raise ValueError(f"código de erro fora do catálogo CTR-10: {code}")
        super().__init__(message)
        self.code = code
        self.message = message
