"""Recorte comum de JSON e YAML: um fragmento por nó de primeiro e segundo nível (CTR-02).

A árvore de entrada é independente do formato: `Node(start, end, children)`,
com posições em caracteres do texto decodificado e filhos `(chave, início, nó)`
— o início do filho inclui a chave, para que o fragmento `"gate": "..."` traga
o nome do campo. Um nó de primeiro nível com filhos vira um fragmento por filho
(`/scripts/gate`); sem filhos, vira um fragmento só (`/name`). Os fragmentos
não se sobrepõem e `struct_path` é um JSON Pointer (RFC 6901).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kos.parsing.lines import LineTable
from kos.parsing.spans import CharMap, fragment, pointer_token
from kos.parsing.types import Fragment


@dataclass
class Node:
    start: int
    end: int
    children: list[tuple[object, int, "Node"]] = field(default_factory=list)


def fragments(blob: bytes, text: str, roots: list[tuple[str, Node]], kind: str) -> list[Fragment]:
    """`roots`: (prefixo do ponteiro, nó raiz) por documento."""
    cmap, lines, out = CharMap(blob, text), LineTable(blob), []

    def emit(start: int, end: int, path: str) -> None:
        frag = fragment(blob, lines, len(out), kind, cmap.byte(start), cmap.byte(end),
                        locator_type="structured", struct_path=path)
        if frag is not None:
            out.append(frag)

    for prefix, root in roots:
        if not root.children:
            emit(root.start, root.end, prefix)
            continue
        for key, key_start, node in root.children:
            path = f"{prefix}/{pointer_token(key)}"
            if node.children:
                for sub_key, sub_start, sub in node.children:
                    emit(sub_start, sub.end, f"{path}/{pointer_token(sub_key)}")
            else:
                emit(key_start, node.end, path)
    return out
