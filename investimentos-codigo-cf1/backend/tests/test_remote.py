"""Quem é local e quem é remoto: na dúvida, remoto (pede Face ID)."""

import pytest

from app.core.remote import client_host, host_name, is_remote


@pytest.mark.parametrize(
    "headers",
    [
        {},  # programa deste computador chamando direto (widget, iniciador)
        {"X-Dashboard-Client-Host": "localhost:5173"},
        {"x-dashboard-client-host": "127.0.0.1:5173"},
        {"X-Dashboard-Client-Host": "[::1]:5173"},
        {"X-Dashboard-Client-Host": "LOCALHOST:5173"},
    ],
)
def test_local(headers):
    assert is_remote(headers) is False


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Dashboard-Client-Host": "meupc.tail1234.ts.net"},
        {"X-Dashboard-Client-Host": ""},  # cabeçalho vazio: nega
        {"X-Dashboard-Client-Host": "   "},
        {"X-Dashboard-Client-Host": "localhost.evil.com:5173"},
        {"X-Dashboard-Client-Host": "localhost:5173", "X-Forwarded-For": "100.64.0.2"},
        {"X-Dashboard-Client-Host": "localhost:5173", "Tailscale-User-Login": "a@b"},
        {"X-Forwarded-Host": "meupc.tail1234.ts.net"},  # proxy no meio, mesmo sem o do Vite
        {"Forwarded": "for=100.64.0.2"},
    ],
)
def test_remoto(headers):
    assert is_remote(headers) is True


def test_nome_do_host():
    assert host_name("Meupc.Tail1234.ts.net:443") == "meupc.tail1234.ts.net"
    assert host_name("[::1]:5173") == "::1"
    assert host_name("[::1") == ""
    assert host_name("localhost") == "localhost"
    assert client_host({"x-dashboard-client-host": " meupc.ts.net "}) == "meupc.ts.net"
    assert client_host({}) is None


def test_endereco_encaminhado_pelo_tailscale_vale_mais_que_o_host():
    # Se algum proxy trocar o Host por localhost, a passkey continua presa
    # ao endereço do Tailscale (e a chamada continua remota).
    headers = {"x-dashboard-client-host": "localhost:5173", "X-Forwarded-Host": "pc.tail.ts.net, x"}
    assert client_host(headers) == "pc.tail.ts.net"
    assert is_remote(headers) is True
