"""O prompt da análise diária e o formato aceito pelo app andam juntos:
se o app passa a aceitar um campo novo (ou versão nova), o prompt precisa
pedir — senão o jornal fica sem a seção e ninguém percebe.
"""

import re
import typing
from pathlib import Path

from app.schemas.insights import InsightReport

DOC = Path(__file__).resolve().parents[1] / "docs" / "agente-prompts" / "analise-diaria.md"


def test_prompt_pede_a_versao_mais_nova_do_formato():
    text = DOC.read_text(encoding="utf-8")
    newest = max(typing.get_args(InsightReport.model_fields["schema_version"].annotation))
    assert re.findall(r'"schema_version": (\d+)', text) == [str(newest)]


def test_prompt_mostra_todos_os_campos_do_relatorio():
    text = DOC.read_text(encoding="utf-8")
    missing = [name for name in InsightReport.model_fields if f'"{name}"' not in text]
    assert missing == []
