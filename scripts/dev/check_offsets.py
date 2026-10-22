"""Confere TC-PRS-01 num corpus real: todo fragmento elegível é verificável por bytes.

Uso: PYTHONPATH=src python scripts/dev/check_offsets.py REPO [--rev REV] [--policy ARQ]

Lê os blobs direto do Git (nada da cópia de trabalho), escolhe o parser pelo
tipo de mídia e confere que o texto de cada fragmento se reconstrói do recorte
(`registry.expected_text`). Sai
com 1 se algum fragmento não bater ou se um parser levantar exceção.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from kos.discovery import Policy, discover
from kos.parsing import registry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", type=Path)
    ap.add_argument("--rev", default="HEAD")
    ap.add_argument("--policy", type=Path)
    args = ap.parse_args()
    policy = Policy.load(args.policy) if args.policy else Policy.default()
    commit, files = discover(args.repo, args.rev, policy)
    eligible = [f for f in files if f.eligibility == "eligible"]
    stats: dict[str, Counter] = defaultdict(Counter)
    problems = []
    for f in eligible:
        blob = subprocess.run(["git", "-C", str(args.repo), "cat-file", "blob", f.blob_oid],
                              capture_output=True, check=True).stdout
        try:
            profile, result = registry.parse(blob, f.media_type)
        except Exception as exc:  # noqa: BLE001 — o objetivo é listar qualquer quebra
            problems.append((f.path_text, "exceção", repr(exc)))
            continue
        name = profile.profile_name if profile else "(sem parser)"
        st = stats[name]
        st["arquivos"] += 1
        st[result.status] += 1
        st["fragmentos"] += len(result.fragments)
        if result.status != "parsed":
            problems.append((f.path_text, result.status, result.reason_code or "", *result.warnings))
        for frag in result.fragments:
            loc = frag.locator
            if registry.expected_text(f.media_type, blob[loc.start_byte:loc.end_byte]) != frag.text:
                st["divergentes"] += 1
                problems.append((f.path_text, "divergente", frag.ordinal, loc.start_line, loc.end_line))
    print(f"commit {commit}: {len(eligible)} arquivos elegíveis")
    for name in sorted(stats):
        print(f"  {name}: " + ", ".join(f"{k}={v}" for k, v in sorted(stats[name].items())))
    for item in problems:
        print("  -", *item)
    broken = sum(st["divergentes"] for st in stats.values()) + sum(p[1] == "exceção" for p in problems)
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
