"""Testes de contrato dos parsers JSON e YAML (CTR-02, TC-PRS-01, 02, 04, 06; BL-06)."""

import unittest

from kos.parsing import json_doc, yaml_doc
from kos.parsing.normalize import normalize

PACKAGE = """{
  "name": "site",
  "scripts": {
    "gate": "npm run lint && npm test",
    "a/b~c": "x"
  },
  "files": ["dist", {"src": "ação"}],
  "private": true,
  "vazio": {}
}
"""

WORKFLOW = """# comentário
name: CI
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: echo "ação"
  test: 1
"""


def _view(result):
    return [(f.locator.struct_path, f.locator.start_line, f.locator.end_line, f.text)
            for f in result.fragments]


class OffsetsMixin:
    def check(self, blob, result):
        """TC-PRS-01, mais ordinais contíguos e fragmentos sem sobreposição."""
        frags = result.fragments
        self.assertEqual([f.ordinal for f in frags], list(range(len(frags))))
        for f in frags:
            self.assertEqual(f.locator.type, "structured")
            self.assertEqual(normalize(blob[f.locator.start_byte:f.locator.end_byte]), f.text)
        for a, b in zip(frags, frags[1:]):
            self.assertLessEqual(a.locator.end_byte, b.locator.start_byte)


class JsonTest(OffsetsMixin, unittest.TestCase):
    def setUp(self):
        self.blob = PACKAGE.encode("utf-8")
        self.result = json_doc.parse(self.blob)

    def test_ponteiro_scripts_gate(self):
        """TC-PRS-04."""
        self.assertEqual(self.result.status, "parsed")
        self.check(self.blob, self.result)
        gate = next(f for f in self.result.fragments if f.locator.struct_path == "/scripts/gate")
        self.assertEqual(gate.text, '"gate": "npm run lint && npm test"')
        self.assertEqual((gate.locator.start_line, gate.locator.end_line), (4, 4))

    def test_primeiro_e_segundo_nivel(self):
        self.assertEqual([f.locator.struct_path for f in self.result.fragments], [
            "/name", "/scripts/gate", "/scripts/a~1b~0c", "/files/0", "/files/1",
            "/private", "/vazio",
        ])

    def test_offsets_com_acento(self):
        frag = next(f for f in self.result.fragments if f.locator.struct_path == "/files/1")
        self.assertEqual(frag.text, '{"src": "ação"}')

    def test_crlf_e_lf(self):
        """TC-PRS-02."""
        crlf = PACKAGE.replace("\n", "\r\n").encode("utf-8")
        other = json_doc.parse(crlf)
        self.check(crlf, other)
        self.assertEqual(_view(other), _view(self.result))

    def test_bom(self):
        blob = "﻿".encode("utf-8") + self.blob
        result = json_doc.parse(blob)
        self.check(blob, result)
        self.assertEqual(_view(result), _view(self.result))

    def test_raiz_escalar_e_vazia(self):
        self.assertEqual(_view(json_doc.parse(b' "x" \n')), [("", 1, 1, '"x"')])
        self.assertEqual(_view(json_doc.parse(b"[]")), [("", 1, 1, "[]")])
        self.assertEqual(json_doc.parse(b"\n").fragments, ())

    def test_sintaxe_invalida_vira_texto_com_aviso(self):
        blob = b'{\n  // comentario\n  "a": 1\n}\n'
        result = json_doc.parse(blob)
        self.assertEqual((result.status, result.reason_code), ("parsed_with_warnings", "E_PARSE_SYNTAX"))
        self.assertTrue(result.warnings[0].startswith("E_PARSE_SYNTAX"))
        self.assertEqual(result.fragments[0].text, blob.decode().strip())
        for blob in (b'{"a": 1,}', b'{"a" 1}', b"[1 2]", b'{"a": tru}', b'{"a": 1} x', b'"\\x"'):
            self.assertEqual(json_doc.parse(blob).status, "parsed_with_warnings", blob)

    def test_aninhamento_profundo_nao_quebra(self):
        blob = b"[" * 5000 + b"]" * 5000
        self.assertEqual(json_doc.parse(blob).status, "parsed_with_warnings")

    def test_utf8_invalido(self):
        self.assertEqual(json_doc.parse(b'{"a": "\xff"}').reason_code, "E_DECODE")

    def test_pureza(self):
        """TC-PRS-06."""
        self.assertEqual(json_doc.parse(self.blob), self.result)


class YamlTest(OffsetsMixin, unittest.TestCase):
    def setUp(self):
        self.blob = WORKFLOW.encode("utf-8")
        self.result = yaml_doc.parse(self.blob)

    def test_nos_de_primeiro_e_segundo_nivel(self):
        self.assertEqual(self.result.status, "parsed")
        self.check(self.blob, self.result)
        self.assertEqual([(f.locator.struct_path, f.locator.start_line, f.locator.end_line)
                          for f in self.result.fragments], [
            ("/name", 2, 2), ("/on/0", 3, 3), ("/jobs/build", 5, 9), ("/jobs/test", 10, 10),
        ])
        build = self.result.fragments[2]
        self.assertTrue(build.text.startswith("build:\n    runs-on"))
        self.assertTrue(build.text.endswith('echo "ação"'))

    def test_crlf_e_lf(self):
        crlf = WORKFLOW.replace("\n", "\r\n").encode("utf-8")
        other = yaml_doc.parse(crlf)
        self.check(crlf, other)
        self.assertEqual(_view(other), _view(self.result))

    def test_varios_documentos(self):
        blob = b"a: 1\n---\nb:\n  c: 2\n"
        result = yaml_doc.parse(blob)
        self.check(blob, result)
        self.assertEqual([f.locator.struct_path for f in result.fragments], ["/0/a", "/1/b/c"])

    def test_tag_nao_e_construida(self):
        blob = b"x: !!python/object/apply:os.system ['echo oi']\n"
        result = yaml_doc.parse(blob)
        self.assertEqual(result.status, "parsed")
        self.check(blob, result)

    def test_sintaxe_invalida_vira_texto_com_aviso(self):
        result = yaml_doc.parse(b"a: [1, 2\nb: 3\n")
        self.assertEqual((result.status, result.reason_code), ("parsed_with_warnings", "E_PARSE_SYNTAX"))
        self.assertTrue(result.fragments)

    def test_pureza(self):
        self.assertEqual(yaml_doc.parse(self.blob), self.result)


if __name__ == "__main__":
    unittest.main()
