"""Gravação atômica do retrato da carteira e dos alertas lidos.

Regressão: no Windows o Jornal mostrava "não foi possível gravar o retrato
da carteira: [Errno 13] Permission denied: '...\\.carteira.json.tmp'".
Duas gravações ao mesmo tempo (o React roda o efeito da tela duas vezes no
modo de desenvolvimento; ou o celular e o computador abertos) usavam o
MESMO arquivo temporário, e uma atropelava a outra.
"""

import json
import os
import threading
from uuid import uuid4

import pytest

from app.core import files
from app.core.config import settings
from app.core.files import atomic_write_text
from app.services import insights_service


@pytest.fixture()
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "insights_dir", tmp_path)
    return tmp_path


def _hold_replace_until_both_arrive(monkeypatch):
    """Segura cada troca até as duas gravações chegarem nela (ou meio
    segundo, se uma só puder passar por vez): é a corrida que acontecia."""
    real_replace = os.replace
    barrier = threading.Barrier(2, timeout=0.5)

    def replace(source, target):
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", replace)


def test_duas_gravacoes_do_retrato_ao_mesmo_tempo_dao_certo(folder, monkeypatch):
    user_id = uuid4()
    monkeypatch.setattr(
        insights_service, "build_snapshot", lambda db, uid: {"positions": [], "uid": str(uid)}
    )
    _hold_replace_until_both_arrive(monkeypatch)
    errors: list[BaseException] = []

    def write():
        try:
            insights_service.write_snapshot(None, user_id)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=write) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)

    assert errors == []
    assert json.loads((folder / "carteira.json").read_text(encoding="utf-8"))["positions"] == []
    assert [p.name for p in folder.iterdir()] == ["carteira.json"]  # nenhum temporário sobrou


def test_cada_gravacao_usa_um_temporario_proprio(tmp_path, monkeypatch):
    used: list[str] = []
    real_replace = os.replace

    def replace(source, target):
        used.append(os.path.basename(source))
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", replace)
    atomic_write_text(tmp_path / "carteira.json", "a")
    atomic_write_text(tmp_path / "carteira.json", "b")

    assert len(set(used)) == 2
    assert all(name.startswith(".carteira.json.") and name.endswith(".tmp") for name in used)
    assert (tmp_path / "carteira.json").read_text(encoding="utf-8") == "b"


def test_windows_segurando_o_arquivo_por_um_instante_nao_derruba_a_gravacao(tmp_path, monkeypatch):
    real_replace = os.replace
    calls = {"n": 0}

    def replace(source, target):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(13, "Permission denied")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(files, "REPLACE_WAIT_SECONDS", 0)
    atomic_write_text(tmp_path / "carteira.json", "ok")

    assert (tmp_path / "carteira.json").read_text(encoding="utf-8") == "ok"
    assert calls["n"] == 3


def test_se_o_windows_nao_soltar_o_arquivo_o_erro_aparece_e_nao_sobra_temporario(
    tmp_path, monkeypatch
):
    def replace(source, target):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(files, "REPLACE_WAIT_SECONDS", 0)
    (tmp_path / "carteira.json").write_text("antigo", encoding="utf-8")

    with pytest.raises(PermissionError):
        atomic_write_text(tmp_path / "carteira.json", "novo")

    assert (tmp_path / "carteira.json").read_text(encoding="utf-8") == "antigo"
    assert [p.name for p in tmp_path.iterdir()] == ["carteira.json"]


def test_alertas_lidos_tambem_gravam_sem_disputar_o_temporario(folder, monkeypatch):
    _hold_replace_until_both_arrive(monkeypatch)
    errors: list[BaseException] = []

    def mark(ids):
        try:
            insights_service._write_read_ids(ids)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=mark, args=([f"a{i}"],)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)

    assert errors == []
    assert [p.name for p in (folder / "alertas").iterdir()] == ["lidos.json"]
