"""Utilitários compartilhados pelos testes."""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
SPEC = ROOT / "docs" / "fase-0"


def spec_sql_blocks() -> list[str]:
    """Blocos ```sql de 02-modelo-de-dados.md: [index.sqlite, audit.sqlite]."""
    text = (SPEC / "02-modelo-de-dados.md").read_text(encoding="utf-8")
    return re.findall(r"```sql\n(.*?)```", text, re.S)


def run_kos(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Roda a CLI como processo, sem depender de instalação do pacote."""
    full_env = {k: v for k, v in os.environ.items() if k != "KOS_HOME"}
    full_env.update({"PYTHONPATH": str(SRC), **(env or {})})
    return subprocess.run(
        [sys.executable, "-m", "kos", *args],
        capture_output=True, text=True, env=full_env, cwd=ROOT,
    )
