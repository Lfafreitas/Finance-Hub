"""O repositório não guarda pedaço de CPF (nem real, nem mascarado).

Regressão: um teste de importação tinha os dígitos do meio de um CPF de
extrato real ("•••.xxx.xxx-••"). Nos testes, só o placeholder 123.456.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDERS = [
    ROOT / "backend" / "app",
    ROOT / "backend" / "tests",
    ROOT / "backend" / "docs",
    ROOT / "frontend" / "src",
]
MASKED = re.compile(r"•••\.(\d{3}\.\d{3})-••")
FULL = re.compile(r"(?<![\d.])\d{3}\.\d{3}\.\d{3}-\d{2}(?![\d])")


def _files():
    for folder in FOLDERS:
        for path in folder.rglob("*"):
            if (
                path.suffix in {".py", ".ts", ".tsx", ".md", ".json", ".csv", ".ofx"}
                and path.is_file()
            ):
                yield path


def test_nenhum_cpf_nos_fontes():
    found = []
    for path in _files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        found += [
            f"{path.name}: {m.group(0)}" for m in MASKED.finditer(text) if m.group(1) != "123.456"
        ]
        found += [f"{path.name}: {m.group(0)}" for m in FULL.finditer(text)]
    assert found == []
