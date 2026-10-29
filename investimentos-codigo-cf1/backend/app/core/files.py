"""Gravação atômica de arquivos que outros programas leem (o retrato da
carteira, a lista de alertas lidos).

Grava num arquivo temporário e troca pelo final, para quem lê (a análise
do Claude) nunca pegar um arquivo pela metade. Três cuidados por causa do
Windows:

- cada gravação usa um temporário com NOME PRÓPRIO: duas gravações ao
  mesmo tempo (duas abas abertas, o celular e o computador, ou o React
  rodando o efeito duas vezes no modo de desenvolvimento) disputavam o
  mesmo `.carteira.json.tmp`, e o Windows nega o segundo
  ("[Errno 13] Permission denied");
- gravações no mesmo arquivo passam uma de cada vez (trava por caminho);
- a troca tenta de novo por um instante quando o Windows segura o arquivo
  (antivírus ou indexação abrindo o arquivo recém-criado, ou alguém lendo
  o destino naquela hora).
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()

REPLACE_ATTEMPTS = 6
REPLACE_WAIT_SECONDS = 0.05


def _lock_for(path: Path) -> threading.Lock:
    key = os.path.normcase(str(path.resolve()))
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def _replace_with_retry(source: str, target: Path) -> None:
    for attempt in range(REPLACE_ATTEMPTS):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(REPLACE_WAIT_SECONDS * (attempt + 1))


def atomic_write_text(target: Path, text: str) -> None:
    """Grava `text` (UTF-8) em `target` de forma atômica. Falhas viram
    `OSError` e não deixam temporário para trás."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with _lock_for(target):
        fd, temporary = tempfile.mkstemp(
            dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            _replace_with_retry(temporary, target)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
