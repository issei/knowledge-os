"""O catálogo de erros do código é o mesmo do contrato CTR-10."""

import re
import unittest

from kos.errors import ERROR_CODES, KosError
from tests.helpers import SPEC


class ErrorCatalogTest(unittest.TestCase):
    def test_catalog_matches_ctr10(self):
        text = (SPEC / "03-contratos.md").read_text(encoding="utf-8")
        section = text.split("**Catálogo de erros (inicial):**")[1].split("**Códigos de saída")[0]
        self.assertEqual(set(re.findall(r"E_[A-Z0-9_]+", section)), set(ERROR_CODES))

    def test_unknown_code_is_rejected(self):
        # TC-AUD-04: código fora do catálogo é um erro de programação.
        with self.assertRaises(ValueError):
            KosError("E_NAO_EXISTE", "x")


if __name__ == "__main__":
    unittest.main()
