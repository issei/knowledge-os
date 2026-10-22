"""Confere TC-PRS-01 num corpus real: todo fragmento Markdown elegível é verificável por bytes.

Uso: PYTHONPATH=src python scripts/dev/check_md_offsets.py REPO [--rev REV] [--policy ARQ]

Lê os blobs direto do Git (nada da cópia de trabalho). Sai com 1 se algum
fragmento não bater, listando arquivo, ordinal e linhas.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from kos.discovery import Policy, discover
from kos.parsing import markdown
from kos.parsing.normalize import normalize


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", type=Path)
    ap.add_argument("--rev", default="HEAD")
    ap.add_argument("--policy", type=Path)
    args = ap.parse_args()
    policy = Policy.load(args.policy) if args.policy else Policy.default()
    commit, files = discover(args.repo, args.rev, policy)
    md = [f for f in files if f.eligibility == "eligible" and f.media_type == "text/markdown"]
    n_frag, bad, failed = 0, [], []
    for f in md:
        blob = subprocess.run(["git", "-C", str(args.repo), "cat-file", "blob", f.blob_oid],
                              capture_output=True, check=True).stdout
        result = markdown.parse(blob)
        if result.status == "failed":
            failed.append((f.path_text, result.reason_code))
        for frag in result.fragments:
            n_frag += 1
            loc = frag.locator
            if normalize(blob[loc.start_byte:loc.end_byte]) != frag.text:
                bad.append((f.path_text, frag.ordinal, loc.start_line, loc.end_line))
    print(f"commit {commit}: {len(md)} arquivos .md, {n_frag} fragmentos, "
          f"{len(bad)} divergentes, {len(failed)} com falha")
    for item in bad + failed:
        print("  ", *item)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
