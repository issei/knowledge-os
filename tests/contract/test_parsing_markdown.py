"""Testes de contrato do parser Markdown (CTR-02, TC-PRS-01, 02, 03, 06; BL-05)."""

import unittest

from kos.parsing import markdown
from kos.parsing.normalize import normalize

DOC = """---
title: Exemplo
---

# Título

Parágrafo com acentuação: ação, coração.

```md
# isto não é cabeçalho
```

## Sub

- a
- b

### Neto

| a | b |
|---|---|
| 1 | 2 |

# Outro

texto final
"""


def _check_offsets(test, blob, result):
    """TC-PRS-01: o texto de todo fragmento sai do recorte de bytes normalizado."""
    for frag in result.fragments:
        loc = frag.locator
        test.assertEqual(normalize(blob[loc.start_byte:loc.end_byte]), frag.text)


class MarkdownParserTest(unittest.TestCase):
    def setUp(self):
        self.blob = DOC.encode("utf-8")
        self.result = markdown.parse(self.blob)

    def test_offsets_exatos(self):
        self.assertEqual(self.result.status, "parsed")
        _check_offsets(self, self.blob, self.result)

    def test_heading_path_e_front_matter(self):
        got = [(f.fragment_kind, f.heading_path) for f in self.result.fragments]
        self.assertEqual(got, [
            ("yaml_node", None),
            ("section", "Título"),
            ("section", "Título > Sub"),
            ("section", "Título > Sub > Neto"),
            ("section", "Outro"),
        ])

    def test_bloco_de_codigo_nao_e_cortado(self):
        titulo = self.result.fragments[1]
        self.assertIn("```md\n# isto não é cabeçalho\n```", titulo.text)
        self.assertEqual((titulo.locator.start_line, titulo.locator.end_line), (5, 11))

    def test_ordinais_contiguos_e_sem_sobreposicao(self):
        frags = self.result.fragments
        self.assertEqual([f.ordinal for f in frags], list(range(len(frags))))
        for a, b in zip(frags, frags[1:]):
            self.assertLessEqual(a.locator.end_byte, b.locator.start_byte)
            self.assertLess(a.locator.end_line, b.locator.start_line)

    def test_crlf_e_lf_tem_as_mesmas_linhas(self):
        """TC-PRS-02."""
        crlf = DOC.replace("\n", "\r\n").encode("utf-8")
        other = markdown.parse(crlf)
        _check_offsets(self, crlf, other)
        lf_view = [(f.heading_path, f.locator.start_line, f.locator.end_line, f.text)
                   for f in self.result.fragments]
        crlf_view = [(f.heading_path, f.locator.start_line, f.locator.end_line, f.text)
                     for f in other.fragments]
        self.assertEqual(lf_view, crlf_view)
        self.assertNotEqual(self.result.fragments[-1].locator.end_byte,
                            other.fragments[-1].locator.end_byte)

    def test_bom_e_nfd(self):
        blob = "﻿# Coração\n\ntexto\n".encode("utf-8")
        result = markdown.parse(blob)
        _check_offsets(self, blob, result)
        self.assertEqual(result.fragments[0].heading_path, "Coração")
        self.assertEqual(result.fragments[0].locator.start_line, 1)

    def test_pureza(self):
        """TC-PRS-06."""
        self.assertEqual(markdown.parse(self.blob), self.result)

    def test_secao_longa_dividida_entre_blocos(self):
        paras = "\n\n".join(f"parágrafo {i}" for i in range(80))
        blob = f"# Longa\n\n{paras}\n".encode("utf-8")
        result = markdown.parse(blob)
        _check_offsets(self, blob, result)
        self.assertGreater(len(result.fragments), 1)
        for frag in result.fragments:
            self.assertEqual(frag.heading_path, "Longa")
            self.assertLessEqual(frag.locator.end_line - frag.locator.start_line + 1,
                                 markdown.PROFILE.config["max_section_lines"])

    def test_texto_antes_do_primeiro_cabecalho(self):
        blob = b"intro\n\n# A\n\nx\n"
        got = [(f.heading_path, f.text) for f in markdown.parse(blob).fragments]
        self.assertEqual(got, [(None, "intro"), ("A", "# A\n\nx")])

    def test_vazio_e_so_espacos(self):
        for blob in (b"", b"\n\n  \n"):
            result = markdown.parse(blob)
            self.assertEqual((result.status, result.fragments), ("parsed", ()))

    def test_utf8_invalido_falha_com_e_decode(self):
        result = markdown.parse(b"# T\xff\n")
        self.assertEqual((result.status, result.reason_code), ("failed", "E_DECODE"))

    def test_front_matter_sem_fechamento_e_markdown_comum(self):
        blob = b"---\n\ntexto\n"
        result = markdown.parse(blob)
        _check_offsets(self, blob, result)
        self.assertNotIn("yaml_node", [f.fragment_kind for f in result.fragments])

    def test_perfil_registra_a_versao_do_parser(self):
        import markdown_it
        self.assertEqual(markdown.PROFILE.parser_version, markdown_it.__version__)


if __name__ == "__main__":
    unittest.main()
