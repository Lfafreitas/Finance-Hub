#!/usr/bin/env sh
# Abre o widget da carteira. Precisa do tkinter (pacote python3-tk).
AQUI="$(cd "$(dirname "$0")" && pwd)"
PY="$AQUI/../backend/.venv/bin/python"
[ -x "$PY" ] || PY=python3
nohup "$PY" "$AQUI/carteira_widget.py" --ligar-backend >/dev/null 2>&1 &
