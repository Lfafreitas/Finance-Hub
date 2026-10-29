"""Iniciador: as partes que decidem (sem ligar nada de verdade)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dashboard as d

NETSTAT = """
Conexões ativas

  Proto  Endereço local         Endereço externo       Estado         PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1012
  TCP    127.0.0.1:8000         0.0.0.0:0              LISTENING       4242
  TCP    127.0.0.1:18000        0.0.0.0:0              LISTENING       5555
  TCP    127.0.0.1:8000         127.0.0.1:51000        ESTABLISHED     4242
  TCP    127.0.0.1:8000         127.0.0.1:51001        TIME_WAIT       0
  TCP    127.0.0.1:51000        127.0.0.1:8000         ESTABLISHED     7777
  TCP    [::1]:5173             [::]:0                 LISTENING       9090
"""

SS = """LISTEN 0 2048 127.0.0.1:8000 0.0.0.0:* users:(("uvicorn",pid=321,fd=3))
LISTEN 0 511 [::1]:5173 [::]:* users:(("node",pid=654,fd=20))
LISTEN 0 511 0.0.0.0:18000 0.0.0.0:* users:(("other",pid=999,fd=3))
"""


class TestPortas:
    def test_windows_so_quem_escuta_na_porta_exata(self):
        assert d.listening_pids_windows(NETSTAT, 8000) == {4242}
        assert d.listening_pids_windows(NETSTAT, 5173) == {9090}
        assert d.listening_pids_windows(NETSTAT, 9999) == set()

    def test_linux(self):
        assert d.listening_pids_posix(SS, 8000) == {321}
        assert d.listening_pids_posix(SS, 5173) == {654}


class TestQuemEDeste:
    def test_backend_deste_projeto_pelo_nome_no_health(self):
        assert d.is_our_backend({"status": "ok", "app": d.APP_NAME, "environment": "dev"})
        assert not d.is_our_backend({"status": "ok", "app": "Outro projeto"})
        assert not d.is_our_backend({"status": "erro", "app": d.APP_NAME})
        assert not d.is_our_backend(None)

    def test_frontend_deste_projeto_pelo_titulo(self):
        assert d.is_our_frontend("<html><head><title>Dashboard Financeiro</title></head></html>")
        assert not d.is_our_frontend("<title>Peruas</title>")
        assert not d.is_our_frontend(None)


class TestDependencias:
    def test_instala_na_primeira_vez_e_quando_muda(self, tmp_path):
        source = tmp_path / "pyproject.toml"
        source.write_text("a")
        stamp = tmp_path / "stamp"
        marker = tmp_path / "venv"

        assert d.needs_install(source, stamp, marker)  # nunca instalou
        marker.mkdir()
        assert d.needs_install(source, stamp, marker)  # sem carimbo
        stamp.write_text(d.file_hash(source))
        assert not d.needs_install(source, stamp, marker)
        source.write_text("b")
        assert d.needs_install(source, stamp, marker)  # dependências mudaram

    def test_pasta_instalada_sumiu(self, tmp_path):
        source = tmp_path / "package-lock.json"
        source.write_text("x")
        stamp = tmp_path / "stamp"
        stamp.write_text(d.file_hash(source))

        assert d.needs_install(source, stamp, tmp_path / "node_modules")


class TestBanco:
    def test_endereco_do_env_ou_padrao(self):
        assert d.database_address(None) == ("localhost", 5432)
        env = "X=1\nDATABASE_URL=postgresql+psycopg://u:p@db.local:6543/investimentos\n"
        assert d.database_address(env) == ("db.local", 6543)
        assert d.database_address('DATABASE_URL="postgresql://u:p@127.0.0.1/x"') == ("127.0.0.1", 5432)


class TestTextos:
    def test_resumo_da_pasta_entrada(self):
        files = [
            {
                "file_name": "f.pdf",
                "status": "IMPORTED",
                "account_name": "Cartão",
                "imported_count": 7,
                "duplicate_count": 2,
                "matched_transfers": 1,
                "message": None,
            },
            {
                "file_name": "e.ofx",
                "status": "NOTHING_NEW",
                "account_name": "Conta",
                "imported_count": 0,
                "duplicate_count": 9,
                "matched_transfers": 0,
                "message": None,
            },
            {
                "file_name": "r.pdf",
                "status": "REFUSED",
                "account_name": None,
                "imported_count": 0,
                "duplicate_count": 0,
                "matched_transfers": 0,
                "message": "não confere",
            },
        ]

        assert d.describe_inbox(files) == [
            "  ✓ f.pdf — Cartão: 7 novo(s), 2 já existia(m), 1 pagamento(s) de fatura ligado(s)",
            "  = e.ofx — Conta: nada novo",
            "  ✗ r.pdf — ficou na pasta — não confere",
        ]

    def test_atalho_tem_caminhos_entre_aspas_e_crlf(self):
        text = d.bat_text("iniciar")

        assert '"%PROJ%\\backend\\.venv\\Scripts\\python.exe" "%PROJ%\\launcher\\dashboard.py" iniciar' in text
        assert 'py -3 "%PROJ%\\launcher\\dashboard.py" iniciar' in text
        assert text.count("\r\n") == text.count("\n")

    def test_atalhos_criados_na_pasta_de_cima(self, tmp_path, monkeypatch):
        monkeypatch.setattr(d, "DATA", tmp_path)

        d.cmd_atalhos(None)

        names = sorted(p.name for p in tmp_path.iterdir())
        assert names == [
            "Abrir widget.bat",
            "Ativar acesso pelo celular.bat",
            "Carregar pasta Entrada.bat",
            "Entrada",
            "Iniciar Dashboard.bat",
            "Parar Dashboard.bat",
        ]
        assert b"iniciar_widget.bat" in (tmp_path / "Abrir widget.bat").read_bytes()


class TestAtalhosVisual:
    def test_atalho_em_utf8_com_titulo(self):
        text = d.bat_text("iniciar")
        assert "chcp 65001 >nul" in text
        assert "title Iniciar Dashboard" in text
        assert "set PYTHONIOENCODING=utf-8" in text

    def test_iniciar_so_espera_tecla_quando_da_erro(self):
        text = d.bat_text("iniciar")
        assert "if errorlevel 1 pause" in text
        assert "\r\npause\r\n" not in text

    def test_carregar_sempre_espera_para_ler_o_resultado(self):
        assert d.bat_text("carregar").endswith("pause\r\n")
        assert "errorlevel" not in d.bat_text("carregar")

    def test_rotulo_de_data_curto(self):
        from datetime import datetime

        assert d.now_label(datetime(2026, 10, 17, 14, 5)) == "sáb 17/10 · 14:05"


# --- Celular (Tailscale) ------------------------------------------------------------

import io  # noqa: E402
import subprocess  # noqa: E402

import pytest  # noqa: E402

import tui  # noqa: E402

RUNNING = {"BackendState": "Running", "Self": {"DNSName": "meupc.tail1234.ts.net."}}
SERVING = {"Web": {"meupc.tail1234.ts.net:443": {"Handlers": {"/": {"Proxy": "http://localhost:5173"}}}}}


class TestCelularPartesPuras:
    def test_endereco_do_celular_vem_do_nome_da_maquina(self):
        assert d.phone_url(RUNNING) == "https://meupc.tail1234.ts.net/"

    @pytest.mark.parametrize(
        "status",
        [
            None,
            {},
            {"BackendState": "Stopped", "Self": {"DNSName": "meupc.tail1234.ts.net."}},
            {"BackendState": "NeedsLogin", "Self": {}},
            {"BackendState": "Running", "Self": {"DNSName": ""}},
            {"BackendState": "Running", "Self": {"DNSName": "meupc.local."}},  # sem MagicDNS
        ],
    )
    def test_sem_endereco_quando_desconectado_ou_sem_nome(self, status):
        assert d.phone_url(status) is None

    def test_publicacao_aponta_para_o_frontend(self):
        assert d.serve_points_to_frontend(SERVING)
        assert d.serve_points_to_frontend({"Web": {"x:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:5173/"}}}}})

    @pytest.mark.parametrize(
        "serve",
        [
            None,
            {},
            {"Web": {}},
            {"Web": {"x:443": {"Handlers": {"/": {"Proxy": "http://localhost:8000"}}}}},  # backend: nunca
            {"Web": {"x:443": {"Handlers": {"/outra": {"Proxy": "http://localhost:5173"}}}}},
            {"Web": {"x:443": {"Handlers": {"/": {"Path": "C:/pasta"}}}}},
        ],
    )
    def test_publicacao_que_nao_e_o_frontend(self, serve):
        assert not d.serve_points_to_frontend(serve)

    def test_atalho_do_celular_espera_tecla(self):
        text = d.bat_text("celular")
        assert text.endswith("pause\r\n")
        assert "errorlevel" not in text
        assert "title Acesso pelo celular" in text
        assert '"%PROJ%\\launcher\\dashboard.py" celular' in text


@pytest.fixture
def plain(monkeypatch):
    out = tui.Console(stream=io.StringIO(), color=False)
    monkeypatch.setattr(d, "_UI", out)
    return out


def fake_tailscale(monkeypatch, status, serve, calls):
    monkeypatch.setattr(d, "tailscale_cli", lambda: "tailscale")

    def fake_json(_cli, *args):
        calls.append(("json", args))
        return status if args == ("status",) else serve

    monkeypatch.setattr(d, "tailscale_json", fake_json)


class TestCelularComando:
    def test_sem_tailscale_explica_como_instalar(self, monkeypatch, plain):
        monkeypatch.setattr(d, "tailscale_cli", lambda: None)
        with pytest.raises(d.Stop) as exc:
            d.cmd_celular(None)
        assert "tailscale.com/download" in str(exc.value)
        assert "MESMA conta" in str(exc.value)

    def test_tailscale_desconectado_para_sem_publicar(self, monkeypatch, plain):
        calls = []
        fake_tailscale(monkeypatch, {"BackendState": "Stopped"}, None, calls)
        monkeypatch.setattr(d.subprocess, "Popen", lambda *a, **k: pytest.fail("não devia publicar"))
        with pytest.raises(d.Stop, match="desconectado"):
            d.cmd_celular(None)

    def test_publica_o_frontend_e_nunca_o_backend(self, monkeypatch, plain):
        calls, runs = [], []
        fake_tailscale(monkeypatch, RUNNING, {}, calls)
        monkeypatch.setattr(d, "web_up", lambda: True)

        def fake_popen(command, **kwargs):
            runs.append(command)
            return FakeServe(["Available within your tailnet:", "https://meupc.tail1234.ts.net/"])

        monkeypatch.setattr(d.subprocess, "Popen", fake_popen)
        d.cmd_celular(None)
        assert runs == [["tailscale", "serve", "--bg", "http://localhost:5173"]]
        text = plain.stream.getvalue()
        assert "publicado só na sua rede" in text
        assert "https://meupc.tail1234.ts.net" in text
        assert "Adicionar à Tela de Início" in text

    def test_ja_publicado_nao_publica_de_novo(self, monkeypatch, plain):
        calls = []
        fake_tailscale(monkeypatch, RUNNING, SERVING, calls)
        monkeypatch.setattr(d, "web_up", lambda: True)
        monkeypatch.setattr(d.subprocess, "Popen", lambda *a, **k: pytest.fail("não devia publicar de novo"))
        d.cmd_celular(None)
        assert "já estava publicado" in plain.stream.getvalue()

    def test_recusa_do_tailscale_mostra_o_que_ele_disse(self, monkeypatch, plain):
        calls = []
        fake_tailscale(monkeypatch, RUNNING, {}, calls)
        monkeypatch.setattr(
            d.subprocess,
            "Popen",
            lambda *a, **k: FakeServe(["error: access denied", "use sudo"], code=1),
        )
        monkeypatch.setattr(d.webbrowser, "open", lambda url: None)
        with pytest.raises(d.Stop) as exc:
            d.cmd_celular(None)
        assert "access denied" in str(exc.value)

    def test_dashboard_desligado_avisa_mas_publica(self, monkeypatch, plain):
        calls = []
        fake_tailscale(monkeypatch, RUNNING, SERVING, calls)
        monkeypatch.setattr(d, "web_up", lambda: False)
        d.cmd_celular(None)
        assert "Iniciar Dashboard" in plain.stream.getvalue()


class FakeServe:
    """`tailscale serve --bg` de mentira: imprime linhas e termina com
    `code`, ou fica esperando para sempre (`hang`), como quando o Tailscale
    pede para ligar o Serve na conta e aguarda alguém aceitar no navegador.
    """

    def __init__(self, lines, code=0, hang=False):
        self.stdout = io.StringIO("".join(line + "\n" for line in lines))
        self.code, self.hang, self.killed = code, hang, False

    def wait(self, timeout=None):
        if self.hang and not self.killed:
            raise subprocess.TimeoutExpired("tailscale serve", timeout)
        return self.code

    def kill(self):
        self.killed = True


SERVE_PROMPT = [
    "Serve is not enabled on your tailnet.",
    "To enable, visit:",
    "",
    "         https://login.tailscale.com/f/serve?node=nABC123",
]


class TestPublicarNoTailscale:
    """Regressão: na primeira vez o Tailscale mostra um link e fica esperando
    alguém aceitar. A saída ficava escondida, o atalho parecia travado por
    1 minuto e terminava com um traceback de TimeoutExpired.
    """

    def test_link_aparece_na_tela_e_abre_no_navegador(self, plain):
        opened = []
        d.run_serve("tailscale", popen=lambda *a, **k: FakeServe(SERVE_PROMPT + ["Success."]), opener=opened.append)

        text = plain.stream.getvalue()
        assert "https://login.tailscale.com/f/serve?node=nABC123" in text
        assert "aceite lá" in text
        assert opened == ["https://login.tailscale.com/f/serve?node=nABC123"]  # uma vez só

    def test_sem_aceitar_para_com_o_link_e_sem_traceback(self, plain):
        process = FakeServe(SERVE_PROMPT, hang=True)
        with pytest.raises(d.Stop) as exc:
            d.run_serve("tailscale", wait=120, popen=lambda *a, **k: process, opener=lambda url: None)

        assert process.killed
        message = str(exc.value)
        assert "2 min esperando" in message
        assert "https://login.tailscale.com/f/serve?node=nABC123" in message
        assert exc.value.__cause__ is None and exc.value.__suppress_context__

    def test_sem_link_e_sem_resposta_explica_o_que_conferir(self, plain):
        with pytest.raises(d.Stop, match="confira se está conectado"):
            d.run_serve("tailscale", wait=60, popen=lambda *a, **k: FakeServe([], hang=True), opener=lambda u: None)

    def test_saida_nunca_e_escondida(self, plain):
        seen = {}

        def popen(command, **kwargs):
            seen.update(kwargs)
            return FakeServe(["ok"])

        d.run_serve("tailscale", popen=popen, opener=lambda u: None)
        assert seen["stdout"] is subprocess.PIPE and seen["stderr"] is subprocess.STDOUT
        assert seen["stdin"] is subprocess.DEVNULL  # nunca fica esperando teclado
        assert "ok" in plain.stream.getvalue()


class TestErroInesperado:
    def test_vira_quadro_com_log_em_vez_de_traceback(self, monkeypatch, tmp_path, plain):
        monkeypatch.setattr(d, "STATE", tmp_path)

        def boom(_args):
            raise ValueError("algo estranho")

        monkeypatch.setattr(d, "cmd_parar", boom)
        assert d.main(["parar"]) == 1

        text = plain.stream.getvalue()
        assert "Não deu" in text and "ValueError: algo estranho" in text
        assert "Traceback" not in text
        assert "ValueError: algo estranho" in (tmp_path / "erro.log").read_text(encoding="utf-8")


class TestCelularNoCartaoFinal:
    def test_sem_tailscale_nao_aparece(self, monkeypatch, plain):
        monkeypatch.setattr(d, "tailscale_cli", lambda: None)
        assert d.phone_row() is None

    def test_desconectado(self, monkeypatch, plain):
        fake_tailscale(monkeypatch, {"BackendState": "Stopped"}, None, [])
        assert d.phone_row() == ("Celular", "Tailscale desconectado (abra o app do Tailscale)")

    def test_ainda_nao_publicado_indica_o_atalho(self, monkeypatch, plain):
        fake_tailscale(monkeypatch, RUNNING, {}, [])
        assert "Ativar acesso pelo celular" in d.phone_row()[1]

    def test_publicado_mostra_o_endereco(self, monkeypatch, plain):
        fake_tailscale(monkeypatch, RUNNING, SERVING, [])
        assert d.phone_row() == ("Celular", "https://meupc.tail1234.ts.net")

    def test_tailscale_json_aguenta_erro_e_lixo(self, monkeypatch):
        monkeypatch.setattr(
            d.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0, b"nao e json", b"")
        )
        assert d.tailscale_json("tailscale", "status") is None
        monkeypatch.setattr(d.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 1, b"{}", b""))
        assert d.tailscale_json("tailscale", "status") is None

        def boom(*a, **k):
            raise subprocess.TimeoutExpired(a[0], 8)

        monkeypatch.setattr(d.subprocess, "run", boom)
        assert d.tailscale_json("tailscale", "status") is None


class TestFrontendComDependenciaNova:
    """Regressão: depois de instalar um pacote novo (a biblioteca do Face
    ID), o Vite que já estava ligado continuava sem enxergá-lo e a tela
    quebrava com "Failed to resolve import". Agora o iniciador reinicia.
    """

    @pytest.mark.parametrize(
        "installed, up, action",
        [(False, False, "start"), (True, False, "start"), (False, True, "keep"), (True, True, "restart")],
    )
    def test_decisao(self, installed, up, action):
        assert d.frontend_action(installed, up) == action

    def _iniciar(self, monkeypatch, plain, installed, up):
        calls = []
        monkeypatch.setattr(d, "STATE", d.STATE)
        monkeypatch.setattr(d, "ensure_backend_env", lambda task=None: Path("python"))
        monkeypatch.setattr(d, "ensure_frontend_env", lambda task=None: installed)
        monkeypatch.setattr(d, "ensure_database", lambda python: None)
        monkeypatch.setattr(d, "backend_health", lambda: None)
        monkeypatch.setattr(d, "start_backend", lambda python: calls.append("backend"))
        monkeypatch.setattr(d, "web_up", lambda: up)
        monkeypatch.setattr(d, "stop_frontend", lambda: calls.append("stop") or True)
        monkeypatch.setattr(d, "port_open", lambda host, port: False)
        monkeypatch.setattr(d, "start_frontend", lambda: calls.append("start"))
        monkeypatch.setattr(d, "load_inbox", lambda: None)
        monkeypatch.setattr(d, "phone_row", lambda: None)
        monkeypatch.setattr(d.webbrowser, "open", lambda url: None)
        monkeypatch.setattr(d.STATE.__class__, "mkdir", lambda self, **k: None)
        d.cmd_iniciar(type("A", (), {"widget": False, "sem_navegador": True})())
        return calls

    def test_dependencia_nova_reinicia_o_frontend_ja_ligado(self, monkeypatch, plain):
        assert self._iniciar(monkeypatch, plain, installed=True, up=True) == ["backend", "stop", "start"]
        assert "reiniciando o frontend" in plain.stream.getvalue()

    def test_sem_mudanca_aproveita_o_frontend_ligado(self, monkeypatch, plain):
        assert self._iniciar(monkeypatch, plain, installed=False, up=True) == ["backend"]
        assert "frontend já estava no ar" in plain.stream.getvalue()

    def test_desligado_liga(self, monkeypatch, plain):
        assert self._iniciar(monkeypatch, plain, installed=True, up=False) == ["backend", "start"]


class TestPararFrontendNoWindows:
    """Regressão: `netstat -ano -p TCP` só lista IPv4; o Vite no Windows
    escuta em [::1] (IPv6), o PID não aparecia e o "Parar Dashboard"
    terminava em "Não consegui desligar o frontend na porta 5173".
    """

    def test_netstat_sem_filtro_de_ipv4(self, monkeypatch):
        seen = []

        def fake_run(command, **kwargs):
            seen.append(command)
            return subprocess.CompletedProcess(command, 0, NETSTAT, "")

        monkeypatch.setattr(d, "WINDOWS", True)
        monkeypatch.setattr(d.subprocess, "run", fake_run)

        assert d.listening_pids(5173) == {9090}  # [::1]:5173
        assert seen == [["netstat", "-ano"]]

    def test_so_ipv6_escutando(self):
        only_v6 = "  TCP    [::1]:5173             [::]:0                 LISTENING       4321\n"
        assert d.listening_pids_windows(only_v6, 5173) == {4321}
