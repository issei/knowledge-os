"""YAML com posições no original (BL-06; CTR-02).

Usa a fase `compose` do PyYAML com `SafeLoader` (nenhuma tag é construída em
objeto Python). As marcas de início e fim dos nós são índices de caractere no
texto decodificado. Vários documentos no mesmo arquivo viram `/0/...`, `/1/...`.
Sintaxe inválida cai em janelas de texto com aviso.
"""

from __future__ import annotations

import yaml

from kos.errors import KosError
from kos.parsing import text as text_parser
from kos.parsing.normalize import NORMALIZER_VERSION, decode
from kos.parsing.profile import Profile
from kos.parsing.structured import Node, fragments
from kos.parsing.types import ParseResult

PROFILE = Profile(
    profile_name="yaml-native", parser_name="pyyaml", parser_version=yaml.__version__,
    normalizer_version=NORMALIZER_VERSION,
    config={"loader": "SafeLoader", "levels": 2, "struct_path": "json-pointer"},
)


def parse(blob: bytes, profile: Profile = PROFILE) -> ParseResult:
    try:
        text = decode(blob)
    except KosError as err:
        return ParseResult(status="failed", reason_code=err.code)
    if not text.strip():
        return ParseResult(status="parsed")
    try:
        docs = [d for d in yaml.compose_all(text, Loader=yaml.SafeLoader) if d is not None]
    except yaml.YAMLError as exc:
        return text_parser.fallback(blob, " ".join(str(exc).split()))
    except RecursionError:
        return text_parser.fallback(blob, "aninhamento profundo demais")
    roots = [("" if len(docs) == 1 else f"/{i}", _tree(d)) for i, d in enumerate(docs)]
    return ParseResult(status="parsed", fragments=tuple(fragments(blob, text, roots, "yaml_node")))


def _tree(node: yaml.Node) -> Node:
    out = Node(node.start_mark.index, node.end_mark.index)
    if isinstance(node, yaml.MappingNode):
        for key, value in node.value:
            name = key.value if isinstance(key, yaml.ScalarNode) else f"{key.start_mark.index}"
            out.children.append((name, key.start_mark.index, _tree(value)))
    elif isinstance(node, yaml.SequenceNode):
        for i, item in enumerate(node.value):
            out.children.append((i, item.start_mark.index, _tree(item)))
    return out
