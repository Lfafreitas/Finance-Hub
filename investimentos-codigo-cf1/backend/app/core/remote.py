"""Quem está chamando: o próprio computador ou o celular pela rede?

O backend escuta só em 127.0.0.1. Chegam até ele:

1. programas do próprio computador chamando direto (widget, iniciador,
   scripts) — sem o cabeçalho do proxy;
2. o navegador, sempre pelo proxy do Vite (`/api`), que grava em
   `X-Dashboard-Client-Host` o endereço que o navegador usou
   (sobrescrevendo qualquer valor que venha do cliente).

É LOCAL só quem chama direto (1) ou quem abriu `localhost:5173` no próprio
computador (2) sem nenhum cabeçalho de encaminhamento. Qualquer outra coisa
— o endereço do Tailscale, um nome estranho, o cabeçalho vazio, um
`X-Forwarded-For` — é REMOTA e precisa da trava (Face ID). Na dúvida,
remoto: a regra nega por padrão.
"""

from __future__ import annotations

from collections.abc import Mapping

PROXY_HEADER = "x-dashboard-client-host"
# Cabeçalhos que o Tailscale (ou qualquer proxy no meio) acrescenta.
FORWARD_HEADERS = ("x-forwarded-for", "x-forwarded-host", "forwarded", "tailscale-user-login")
LOCAL_NAMES = frozenset({"localhost", "127.0.0.1", "::1"})


def host_name(host: str) -> str:
    """ "Meupc.Tail.ts.net:443" → "meupc.tail.ts.net"; "[::1]:5173" → "::1"."""
    host = host.strip().lower()
    if host.startswith("["):
        return host[1 : host.find("]")] if "]" in host else ""
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def is_remote(headers: Mapping[str, str]) -> bool:
    lowered = {k.lower(): v for k, v in headers.items()}
    if any(h in lowered for h in FORWARD_HEADERS):
        return True
    client_host = lowered.get(PROXY_HEADER)
    if client_host is None:
        return False  # chamada direta de um programa deste computador
    return host_name(client_host) not in LOCAL_NAMES


def client_host(headers: Mapping[str, str]) -> str | None:
    """Endereço usado pelo navegador (com porta, se houver), que prende a
    passkey ao site. O Tailscale informa em `X-Forwarded-Host` (e mantém o
    Host); se algum proxy trocar o Host, vale o encaminhado. Um valor
    forjado aqui só faz a assinatura do próprio forjador não conferir.
    """
    lowered = {k.lower(): v for k, v in headers.items()}
    forwarded = (lowered.get("x-forwarded-host") or "").split(",")[0].strip()
    value = forwarded or (lowered.get(PROXY_HEADER) or "").strip()
    return value or None
