"""Testes de contrato do parser HTML (CTR-02, TC-PRS-01 para HTML, 02, 06; BL-22)."""

import unittest

from kos.parsing import html_doc
from kos.parsing.normalize import normalize

PAGE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <script>var s = "<h1>não é cabeçalho</h1>";</script>
  <style>h1 { color: red }</style>
  <title>Página &amp; teste</title>
  <meta name="description" content="Descrição da página.">
</head>
<body>
  <nav><a href="/">Início</a></nav>
  <h1>Título<br><small>subtítulo</small></h1>
  <p>Parágrafo com <b>negrito</b> e P95 &lt; 800ms.</p>
  <svg><text>escondido</text></svg>
  <template><h2>modelo</h2></template>
  <h2>Seção A</h2>
  <ul><li>um</li><li>dois</li></ul>
  <h3>Sub A1</h3>
  <p>texto&nbsp;final</p>
  <h2>Seção B</h2>
  <table><tr><td>a</td><td>b</td></tr></table>
</body>
</html>
"""


def _check(test, blob, result):
    """TC-PRS-01 (HTML): o texto se reconstrói do recorte; ordinais contíguos; sem sobreposição."""
    frags = result.fragments
    test.assertEqual([f.ordinal for f in frags], list(range(len(frags))))
    for f in frags:
        test.assertEqual(html_doc.visible_text(normalize(blob[f.locator.start_byte:f.locator.end_byte])), f.text)
    for a, b in zip(frags, frags[1:]):
        test.assertLessEqual(a.locator.end_byte, b.locator.start_byte)


class HtmlParserTest(unittest.TestCase):
    def setUp(self):
        self.blob = PAGE.encode("utf-8")
        self.result = html_doc.parse(self.blob)

    def test_secoes_e_heading_path(self):
        self.assertEqual(self.result.status, "parsed")
        _check(self, self.blob, self.result)
        self.assertEqual([(f.heading_path, f.locator.start_line, f.locator.end_line, f.text)
                          for f in self.result.fragments], [
            (None, 6, 10, "Página & teste\nDescrição da página.\nInício"),
            ("Título subtítulo", 11, 12, "Título\nsubtítulo\nParágrafo com negrito e P95 < 800ms."),
            ("Título subtítulo > Seção A", 15, 16, "Seção A\num\ndois"),
            ("Título subtítulo > Seção A > Sub A1", 17, 18, "Sub A1\ntexto final"),
            ("Título subtítulo > Seção B", 19, 20, "Seção B\na b"),
        ])

    def test_conteudo_nao_visivel_fica_fora(self):
        joined = "\n".join(f.text for f in self.result.fragments)
        for hidden in ("não é cabeçalho", "color", "escondido", "modelo", "var s"):
            self.assertNotIn(hidden, joined)

    def test_crlf_e_lf(self):
        """TC-PRS-02."""
        crlf = PAGE.replace("\n", "\r\n").encode("utf-8")
        other = html_doc.parse(crlf)
        _check(self, crlf, other)
        view = lambda r: [(f.heading_path, f.locator.start_line, f.locator.end_line, f.text) for f in r.fragments]
        self.assertEqual(view(other), view(self.result))

    def test_bom_e_texto_nao_ascii(self):
        blob = "﻿".encode("utf-8") + self.blob
        result = html_doc.parse(blob)
        _check(self, blob, result)
        self.assertEqual(result.fragments[1].locator.start_line, 11)

    def test_secao_longa_dividida_no_inicio_de_bloco(self):
        body = "\n".join(f"<p>parágrafo {i}</p>" for i in range(200))
        blob = f"<h1>Longa</h1>\n{body}\n".encode("utf-8")
        result = html_doc.parse(blob)
        _check(self, blob, result)
        self.assertGreater(len(result.fragments), 2)
        self.assertEqual({f.heading_path for f in result.fragments}, {"Longa"})
        limit = html_doc.PROFILE.config["max_section_lines"]
        for f in result.fragments:
            self.assertLessEqual(f.locator.end_line - f.locator.start_line, limit)
        self.assertEqual(sum(f.text.count("parágrafo ") for f in result.fragments), 200)

    def test_html_quebrado_nao_falha(self):
        for blob in (b"<h2>sem fechar", b"<p>a <b>b</p> c", b"</div>texto<div", b"<!-- aberto", b"&amp"):
            result = html_doc.parse(blob)
            self.assertEqual(result.status, "parsed", blob)
            _check(self, blob, result)

    def test_vazio_e_so_marcacao(self):
        self.assertEqual(html_doc.parse(b"").fragments, ())
        self.assertEqual(html_doc.parse(b"<html><script>x</script></html>").fragments, ())

    def test_utf8_invalido(self):
        self.assertEqual(html_doc.parse(b"<p>\xff</p>").reason_code, "E_DECODE")

    def test_pureza(self):
        """TC-PRS-06."""
        self.assertEqual(html_doc.parse(self.blob), self.result)


if __name__ == "__main__":
    unittest.main()
