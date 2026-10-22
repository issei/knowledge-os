"""Testes de contrato do texto puro, código como texto e do registro de parsers (BL-06, BL-07)."""

import unittest

from kos.parsing import registry, text
from kos.parsing.normalize import normalize


def _check(test, blob, result):
    for f in result.fragments:
        test.assertEqual(normalize(blob[f.locator.start_byte:f.locator.end_byte]), f.text)
    test.assertEqual([f.ordinal for f in result.fragments], list(range(len(result.fragments))))


class TextWindowsTest(unittest.TestCase):
    def test_paragrafos_agrupados_ate_o_limite(self):
        blob = b"\n".join(f"linha {i}".encode() + (b"\n" if i % 5 == 4 else b"") for i in range(100))
        result = text.parse(blob)
        _check(self, blob, result)
        for f in result.fragments:
            self.assertLessEqual(f.locator.end_line - f.locator.start_line + 1, 40)
            self.assertEqual(f.fragment_kind, "paragraph")
        joined = " ".join(f.text for f in result.fragments)
        self.assertEqual(joined.count("linha "), 100)

    def test_paragrafo_longo_cortado_em_linhas_inteiras(self):
        blob = "\n".join(f"ação {i}" for i in range(95)).encode("utf-8")
        result = text.parse(blob)
        _check(self, blob, result)
        self.assertEqual([(f.locator.start_line, f.locator.end_line) for f in result.fragments],
                         [(1, 40), (41, 80), (81, 95)])

    def test_crlf_e_lf(self):
        lf = b"a\nb\n\nc\n"
        crlf = lf.replace(b"\n", b"\r\n")
        view = lambda r: [(f.locator.start_line, f.locator.end_line, f.text) for f in r.fragments]
        self.assertEqual(view(text.parse(lf)), view(text.parse(crlf)))
        _check(self, crlf, text.parse(crlf))

    def test_codigo_como_texto(self):
        blob = b"function a() {\n  return 1;\n}\n\nexport const b = 2;\n"
        result = text.parse(blob, text.CODE_PROFILE)
        _check(self, blob, result)
        self.assertEqual([f.fragment_kind for f in result.fragments], ["code_block"])
        self.assertEqual((result.fragments[0].locator.start_line, result.fragments[0].locator.end_line), (1, 5))

    def test_vazio_e_decode(self):
        self.assertEqual(text.parse(b" \n\n").fragments, ())
        self.assertEqual(text.parse(b"\xff").reason_code, "E_DECODE")


class RegistryTest(unittest.TestCase):
    def test_parser_por_tipo_de_midia(self):
        cases = {
            "text/markdown": "md-native", "application/json": "json-native",
            "application/yaml": "yaml-native", "text/javascript": "code-as-text",
            "text/x-python": "code-as-text", "text/plain": "text-windows",
            "application/octet-stream": "text-windows",
        }
        for media, name in cases.items():
            profile, result = registry.parse(b"a\n", media)
            self.assertEqual(profile.profile_name, name, media)
            self.assertEqual(registry.profile_for(media), profile)

    def test_html_aguarda_o_bl22(self):
        profile, result = registry.parse(b"<p>x</p>", "text/html")
        self.assertIsNone(profile)
        self.assertEqual((result.status, result.reason_code), ("skipped", "E_PARSER_UNAVAILABLE"))

    def test_perfis_tem_impressoes_digitais_distintas(self):
        from kos.parsing import json_doc, markdown, yaml_doc
        profiles = [markdown.PROFILE, json_doc.PROFILE, yaml_doc.PROFILE, text.PROFILE, text.CODE_PROFILE]
        self.assertEqual(len({p.fingerprint for p in profiles}), len(profiles))


if __name__ == "__main__":
    unittest.main()
