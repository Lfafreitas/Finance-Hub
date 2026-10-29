"""Iniciador do dashboard: liga, desliga e carrega arquivos com um comando.

    python dashboard.py iniciar [--widget] [--sem-navegador]
    python dashboard.py parar
    python dashboard.py carregar
    python dashboard.py atalhos
    python dashboard.py celular

No Windows, use os atalhos da pasta "Dashboard Financeiro" (criados por
`atalhos`): "Iniciar Dashboard", "Parar Dashboard", "Abrir widget" e
"Carregar pasta Entrada" e "Ativar acesso pelo celular".

Celular: com o Tailscale (rede privada gratuita) no computador e no
iPhone, `celular` publica o dashboard SÓ dentro dessa rede, em
https://<computador>.<rede>.ts.net. Nada fica aberto para a internet; o
computador precisa estar ligado com o dashboard no ar.

`iniciar`, nesta ordem:

1. confere o Python do backend (backend/.venv) e instala as dependências
   quando o pyproject.toml mudou (ex.: o pdfminer da fatura em PDF);
2. faz o mesmo com o frontend (npm install quando o package-lock mudou);
3. confere o Postgres e aplica as migrações (alembic upgrade head);
4. liga o backend (127.0.0.1:8000) — se um backend deste projeto já
   estava ligado, ele é reiniciado para pegar o código novo;
5. liga o frontend (localhost:5173), ou reaproveita o que já estava;
6. carrega a pasta Entrada, se houver arquivo esperando;
7. abre o navegador (e o widget, com --widget).

Só biblioteca padrão. Nada sai do computador além do que pip e npm
baixam para instalar dependências.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # investimentos-codigo-cf1
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
WIDGET = ROOT / "widget"
DATA = ROOT.parent  # Dashboard Financeiro
STATE = ROOT / ".dashboard"
API = "http://127.0.0.1:8000"
WEB = "http://localhost:5173/"
BACKEND_PORT, FRONTEND_PORT = 8000, 5173
APP_NAME = "Sistema de Controle de Investimentos"  # /health deste backend
WEB_TITLE = "<title>Dashboard Financeiro</title>"  # index.html deste frontend
WINDOWS = sys.platform.startswith("win")


# --- Saída -----------------------------------------------------------------------

sys.path.insert(0, str(HERE))
import tui  # noqa: E402  (mesma pasta; o iniciador roda como script)

_UI: tui.Console | None = None
WEEKDAYS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def ui() -> tui.Console:
    global _UI
    if _UI is None:
        _UI = tui.Console()
    return _UI


def say(text: str = "") -> None:
    ui().write(text)


def now_label(moment: datetime | None = None) -> str:
    """ "sex 17/10 · 14:20" """
    moment = moment or datetime.now()
    return f"{WEEKDAYS[moment.weekday()]} {moment:%d/%m} · {moment:%H:%M}"


class Stop(Exception):
    """Parada com mensagem para o usuário (sem traceback)."""


# --- Partes puras (testadas) ----------------------------------------------------


def file_hash(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def needs_install(source: Path, stamp: Path, installed_marker: Path) -> bool:
    """Instala quando nunca instalou, quando a pasta instalada sumiu ou
    quando o arquivo de dependências mudou desde a última instalação.
    """
    if not installed_marker.exists():
        return True
    current = file_hash(source)
    try:
        saved = stamp.read_text(encoding="utf-8").strip()
    except OSError:
        return True
    return current != saved


def listening_pids_windows(netstat_output: str, port: int) -> set[int]:
    """PIDs ESCUTANDO na porta, a partir de `netstat -ano`."""
    pids: set[int] = set()
    for line in netstat_output.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper() == "TCP" and parts[3].upper() == "LISTENING":
            if re.search(rf":{port}$", parts[1]):
                try:
                    pids.add(int(parts[4]))
                except ValueError:
                    pass
    return pids


def listening_pids_posix(ss_output: str, port: int) -> set[int]:
    """PIDs escutando na porta, a partir de `ss -ltnpH`."""
    pids: set[int] = set()
    for line in ss_output.splitlines():
        parts = line.split()
        if len(parts) >= 4 and re.search(rf":{port}$", parts[3]):
            pids.update(int(p) for p in re.findall(r"pid=(\d+)", line))
    return pids


def is_our_backend(health: dict | None) -> bool:
    """Só o backend DESTE projeto pode ser desligado/reiniciado aqui."""
    return bool(health) and health.get("status") == "ok" and health.get("app") == APP_NAME


def is_our_frontend(html: str | None) -> bool:
    return bool(html) and WEB_TITLE in html


def database_address(env_text: str | None) -> tuple[str, int]:
    """Host e porta do Postgres a partir do backend/.env (padrão do
    projeto: localhost:5432).
    """
    host, port = "localhost", 5432
    match = re.search(r"^\s*DATABASE_URL\s*=\s*(\S+)", env_text or "", re.MULTILINE)
    if match:
        url = match.group(1).strip("'\"")
        found = re.search(r"@([^:/?]+)(?::(\d+))?", url)
        if found:
            host = found.group(1)
            port = int(found.group(2) or 5432)
    return host, port


def describe_inbox(files: list[dict]) -> list[str]:
    marks = {"IMPORTED": "✓", "NOTHING_NEW": "=", "REFUSED": "✗", "NO_ACCOUNT": "!"}
    lines = []
    for f in files:
        if f["status"] == "IMPORTED":
            detail = f"{f['account_name']}: {f['imported_count']} novo(s)"
            if f["duplicate_count"]:
                detail += f", {f['duplicate_count']} já existia(m)"
            if f["matched_transfers"]:
                detail += f", {f['matched_transfers']} pagamento(s) de fatura ligado(s)"
        elif f["status"] == "NOTHING_NEW":
            detail = f"{f['account_name']}: nada novo"
        else:
            detail = f"ficou na pasta — {f.get('message') or ''}"
        lines.append(f"  {marks.get(f['status'], '?')} {f['file_name']} — {detail}")
    return lines


# --- Sistema ---------------------------------------------------------------------


FRONTEND_TARGET = f"http://localhost:{FRONTEND_PORT}"


def phone_url(status: dict | None) -> str | None:
    """Endereço do dashboard no celular, a partir de `tailscale status --json`.
    None quando o Tailscale não está conectado ou não tem nome (MagicDNS).
    """
    if not status or status.get("BackendState") != "Running":
        return None
    name = str((status.get("Self") or {}).get("DNSName") or "").rstrip(".")
    if not name.endswith(".ts.net"):
        return None
    return f"https://{name}/"


def serve_points_to_frontend(serve: dict | None) -> bool:
    """`tailscale serve status --json` já publica a porta do frontend em "/"?"""
    for site in ((serve or {}).get("Web") or {}).values():
        handler = ((site or {}).get("Handlers") or {}).get("/") or {}
        proxy = str(handler.get("Proxy") or "").rstrip("/")
        if proxy.endswith(f":{FRONTEND_PORT}"):
            return True
    return False


def venv_python(windowed: bool = False) -> Path:
    if WINDOWS:
        name = "pythonw.exe" if windowed else "python.exe"
        return BACKEND / ".venv" / "Scripts" / name
    return BACKEND / ".venv" / "bin" / "python"


def run(command: list[str], cwd: Path, log: Path, what: str) -> None:
    STATE.mkdir(exist_ok=True)
    with open(log, "ab") as handle:
        handle.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} {' '.join(command)}\n".encode())
        handle.flush()
        code = subprocess.call(command, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT)
    if code != 0:
        tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-15:]
        raise Stop(f"{what} falhou (código {code}). Últimas linhas de {log}:\n" + "\n".join(tail))


def spawn(command: list[str], cwd: Path, log: Path) -> int:
    STATE.mkdir(exist_ok=True)
    handle = open(log, "ab")
    kwargs: dict = {"cwd": cwd, "stdout": handle, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
    if WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs).pid


def http_json(method: str, path: str, timeout: float = 5):
    request = urllib.request.Request(API + path, method=method, data=b"" if method == "POST" else None)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read() or b"null")


def backend_health() -> dict | None:
    try:
        return http_json("GET", "/health", timeout=2)
    except (urllib.error.URLError, OSError, ValueError):
        return None


def web_page() -> str | None:
    try:
        with urllib.request.urlopen(WEB, timeout=2) as response:
            return response.read(20000).decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError):
        return None


def web_up() -> bool:
    return is_our_frontend(web_page())


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


def frontend_port_free() -> bool:
    return not port_open("127.0.0.1", FRONTEND_PORT) and not port_open("::1", FRONTEND_PORT)


def wait_until(check, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.5)
    return check()


def listening_pids(port: int) -> set[int]:
    try:
        if WINDOWS:
            # Sem "-p TCP": esse filtro só lista IPv4, e o Vite no Windows escuta
            # em [::1] (IPv6). Sem ver o processo, o "Parar" não conseguia
            # desligar o frontend.
            output = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=15, check=False).stdout
            return listening_pids_windows(output, port)
        if shutil.which("ss"):
            output = subprocess.run(["ss", "-ltnpH"], capture_output=True, text=True, timeout=15, check=False).stdout
            return listening_pids_posix(output, port)
        command = ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"]
        output = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False).stdout
        return {int(p) for p in output.split() if p.isdigit()}
    except (OSError, subprocess.SubprocessError):
        return set()


def kill_tree(pid: int) -> None:
    if WINDOWS:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
        return
    import signal

    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass


# --- Etapas ----------------------------------------------------------------------


def tailscale_cli() -> str | None:
    found = shutil.which("tailscale")
    if found:
        return found
    if WINDOWS:
        default = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tailscale" / "tailscale.exe"
        if default.exists():
            return str(default)
    return None


def tailscale_json(cli: str, *args: str) -> dict | None:
    try:
        done = subprocess.run([cli, *args, "--json"], capture_output=True, timeout=8)
        return json.loads(done.stdout or b"null") if done.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def phone_row() -> tuple[str, str] | None:
    """Linha "Celular" do cartão final. Calada quando não há Tailscale."""
    cli = tailscale_cli()
    if cli is None:
        return None
    url = phone_url(tailscale_json(cli, "status"))
    if url is None:
        return ("Celular", "Tailscale desconectado (abra o app do Tailscale)")
    if not serve_points_to_frontend(tailscale_json(cli, "serve", "status")):
        return ("Celular", "atalho “Ativar acesso pelo celular” (uma vez só)")
    return ("Celular", ui().link(url, url.rstrip("/")))


def ensure_backend_env(task: tui.Task | None = None) -> Path:
    task = task or tui.Task("", "")
    python = venv_python()
    if not python.exists():
        task.doing = "criando o ambiente Python do backend (só na primeira vez)"
        task.notes.append("ambiente Python do backend criado")
        run(
            [sys.executable, "-m", "venv", str(BACKEND / ".venv")],
            BACKEND,
            STATE / "instalar.log",
            "criar o venv",
        )
    stamp = STATE / "backend-deps.sha"
    if needs_install(BACKEND / "pyproject.toml", stamp, python):
        task.doing = "instalando as dependências do backend (pode levar um minuto)"
        task.notes.append("dependências do backend atualizadas")
        run(
            [str(python), "-m", "pip", "install", "-q", "-e", "."],
            BACKEND,
            STATE / "instalar.log",
            "pip install",
        )
        stamp.write_text(file_hash(BACKEND / "pyproject.toml") or "", encoding="utf-8")
    return python


def ensure_frontend_env(task: tui.Task | None = None) -> bool:
    """Instala as dependências do frontend quando o package-lock mudou.
    Devolve True se instalou (aí um frontend já ligado precisa reiniciar).
    """
    task = task or tui.Task("", "")
    npm = shutil.which("npm")
    if npm is None:
        raise Stop("Node.js não encontrado. Instale o Node.js (nodejs.org) e rode de novo.")
    stamp = STATE / "frontend-deps.sha"
    if needs_install(FRONTEND / "package-lock.json", stamp, FRONTEND / "node_modules"):
        task.doing = "instalando as dependências do frontend (pode levar um minuto)"
        task.notes.append("dependências do frontend atualizadas")
        run([npm, "install", "--no-audit", "--no-fund"], FRONTEND, STATE / "instalar.log", "npm install")
        stamp.write_text(file_hash(FRONTEND / "package-lock.json") or "", encoding="utf-8")
        return True
    return False


def frontend_action(deps_installed: bool, up: bool) -> str:
    """ "start" (desligado), "keep" (ligado e nada mudou) ou "restart".

    Regressão: o Vite já ligado não enxerga pacote instalado depois que
    ele subiu (ex.: a biblioteca do Face ID) e a tela quebrava com
    "Failed to resolve import". Dependência nova = reiniciar o frontend.
    """
    if not up:
        return "start"
    return "restart" if deps_installed else "keep"


def ensure_database(python: Path) -> None:
    env = BACKEND / ".env"
    host, port = database_address(env.read_text(encoding="utf-8") if env.exists() else None)
    if not port_open(host, port):
        raise Stop(
            f"O Postgres não está respondendo em {host}:{port}.\n"
            "  Windows: abra 'Serviços', procure 'postgresql' e clique em Iniciar.\n"
            "  Linux: sudo systemctl start postgresql"
        )
    run(
        [str(python), "-m", "alembic", "upgrade", "head"],
        BACKEND,
        STATE / "migracoes.log",
        "alembic upgrade head",
    )


def stop_backend() -> bool:
    """Desliga o backend DESTE projeto na porta 8000 (confirmado pelo
    /health). Outro programa na porta nunca é tocado.
    """
    if not is_our_backend(backend_health()):
        return False
    for pid in listening_pids(BACKEND_PORT):
        kill_tree(pid)
    if not wait_until(lambda: not port_open("127.0.0.1", BACKEND_PORT), 10):
        raise Stop(f"Não consegui desligar o backend na porta {BACKEND_PORT}. Feche a janela dele ou reinicie o PC.")
    return True


def stop_frontend() -> bool:
    """Desliga o frontend DESTE projeto na porta 5173 (confirmado pela
    página). O Vite de outro projeto na mesma porta não é tocado.
    """
    if not web_up():
        return False
    for pid in listening_pids(FRONTEND_PORT):
        kill_tree(pid)
    if not wait_until(lambda: not web_up(), 10):
        raise Stop(
            f"Não consegui desligar o frontend na porta {FRONTEND_PORT}.\n"
            'Feche o processo "Node.js JavaScript Runtime" no Gerenciador de Tarefas e rode de novo.'
        )
    return True


def start_backend(python: Path) -> None:
    if port_open("127.0.0.1", BACKEND_PORT):
        if is_our_backend(backend_health()):
            stop_backend()
        else:
            raise Stop(
                f"A porta {BACKEND_PORT} está ocupada por outro programa. Feche-o ou rode "
                "'Parar Dashboard' e tente de novo."
            )
    if port_open("127.0.0.1", BACKEND_PORT):
        raise Stop(f"Não consegui liberar a porta {BACKEND_PORT}. Rode 'Parar Dashboard' e tente de novo.")
    command = [
        str(python),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(BACKEND_PORT),
    ]
    spawn(command, BACKEND, STATE / "backend.log")
    if not wait_until(lambda: is_our_backend(backend_health()), 45):
        tail = (STATE / "backend.log").read_text(encoding="utf-8", errors="replace").splitlines()[-15:]
        raise Stop("O backend não respondeu. Últimas linhas do log:\n" + "\n".join(tail))


def start_frontend() -> None:
    if web_up():
        return
    if port_open("127.0.0.1", FRONTEND_PORT) or port_open("::1", FRONTEND_PORT):
        raise Stop(f"A porta {FRONTEND_PORT} está ocupada por outro programa. Rode 'Parar Dashboard'.")
    node = shutil.which("node")
    vite = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
    if node is None or not vite.exists():
        raise Stop("Não encontrei o Node.js ou o Vite. Rode de novo para instalar as dependências.")
    command = [node, str(vite), "--port", str(FRONTEND_PORT), "--strictPort"]
    spawn(command, FRONTEND, STATE / "frontend.log")
    if not wait_until(web_up, 60):
        raise Stop(f"O frontend não respondeu. Veja {STATE / 'frontend.log'}.")


def load_inbox(quiet_when_empty: bool = True) -> None:
    (DATA / "Entrada").mkdir(exist_ok=True)
    listing = http_json("GET", "/cashflow/inbox")
    if not listing["files"]:
        if not quiet_when_empty:
            ui().info(f"Nenhum arquivo esperando em {listing['inbox_dir']}.")
        return
    count = len(listing["files"])
    with ui().task(f"carregando {count} arquivo(s) da pasta Entrada", "pasta Entrada carregada") as task:
        result = http_json("POST", "/cashflow/inbox/process", timeout=300)
        task.notes.extend(line.strip() for line in describe_inbox(result["files"]))


def open_widget() -> None:
    python = venv_python(windowed=True)
    command = [str(python if python.exists() else sys.executable), str(WIDGET / "carteira_widget.py")]
    spawn(command, WIDGET, STATE / "widget.log")


# --- Comandos ----------------------------------------------------------------------


def cmd_iniciar(args) -> None:
    out = ui()
    out.header("Dashboard Financeiro", f"iniciando · {now_label()}")
    STATE.mkdir(exist_ok=True)
    with out.task("conferindo o ambiente (Python e Node)", "ambiente pronto") as task:
        python = ensure_backend_env(task)
        frontend_deps_changed = ensure_frontend_env(task)
    with out.task("aplicando as migrações do banco", "banco em dia"):
        ensure_database(python)
    restarting = is_our_backend(backend_health())
    with out.task(
        "reiniciando o backend com o código novo" if restarting else "ligando o backend",
        f"backend no ar · 127.0.0.1:{BACKEND_PORT}",
    ):
        start_backend(python)
    action = frontend_action(frontend_deps_changed, web_up())
    if action == "keep":
        out.done(f"frontend já estava no ar · localhost:{FRONTEND_PORT}")
    elif action == "restart":
        with out.task(
            "reiniciando o frontend com as dependências novas", f"frontend no ar · localhost:{FRONTEND_PORT}"
        ):
            stop_frontend()
            if not wait_until(frontend_port_free, 15):
                raise Stop("O frontend antigo não desligou. Rode 'Parar Dashboard' e depois 'Iniciar Dashboard'.")
            start_frontend()
    else:
        with out.task("ligando o frontend", f"frontend no ar · localhost:{FRONTEND_PORT}"):
            start_frontend()
    try:
        load_inbox()
    except (urllib.error.URLError, OSError) as exc:
        out.info(f"não consegui carregar a pasta Entrada: {exc}")
    if args.widget:
        open_widget()
    if not args.sem_navegador:
        webbrowser.open(WEB)
    out.write()
    rows = [
        ("Dashboard", out.link(WEB, WEB.rstrip("/"))),
        ("API", out.link(f"{API}/docs", f"{API}/docs")),
    ]
    phone = phone_row()
    if phone:
        rows.append(phone)
    if args.widget:
        rows.append(("Widget", "aberto (botão direito para o menu)"))
    rows.append(("Desligar", "atalho “Parar Dashboard”"))
    out.card(f"Pronto em {out.total()}", rows, tone=tui.GOOD)
    out.write()
    out.countdown(8, "Esta janela fecha sozinha em {} s. O dashboard continua ligado.")


def cmd_parar(_args) -> None:
    out = ui()
    out.header("Dashboard Financeiro", f"desligando · {now_label()}")
    with out.task("desligando backend e frontend", "pedido enviado") as task:
        back, front = stop_backend(), stop_frontend()
        if back or front:
            task.done = "desligado"
        elif port_open("127.0.0.1", BACKEND_PORT) or port_open("127.0.0.1", FRONTEND_PORT):
            task.done = "nada desligado"
            task.notes.append("as portas 8000/5173 estão com outro programa (não é este dashboard)")
        else:
            task.done = "nada estava ligado"
    out.write()
    out.countdown(4, "Esta janela fecha sozinha em {} s.")


def cmd_carregar(_args) -> None:
    ui().header("Dashboard Financeiro", f"pasta Entrada · {now_label()}")
    if not is_our_backend(backend_health()):
        raise Stop("O backend está desligado. Use 'Iniciar Dashboard' (ele já carrega a pasta).")
    load_inbox(quiet_when_empty=False)


TAILSCALE_HELP = [
    "Para ver o dashboard no celular, longe de casa:",
    "1. instale o Tailscale neste computador: https://tailscale.com/download",
    "2. instale o app Tailscale no iPhone (App Store) e entre na MESMA conta",
    "3. rode este atalho de novo",
    "É gratuito para uso pessoal e o dashboard não fica aberto para a internet.",
]


SERVE_WAIT = 300  # segundos para aceitar o link do Tailscale na primeira vez
TAILSCALE_LINK = re.compile(r"https://login\.tailscale\.com/\S+")


def run_serve(cli: str, wait: float = SERVE_WAIT, popen=None, opener=None) -> None:
    """`tailscale serve --bg` com a saída na tela.

    Na primeira vez, o Tailscale pode pedir para ligar o Serve (HTTPS) na
    conta: ele mostra um link e FICA ESPERANDO alguém aceitar no navegador.
    Por isso a saída nunca é escondida, o link abre sozinho no navegador e,
    sem resposta em `wait` segundos, o comando para com o link na mensagem.
    """
    out = ui()
    popen = popen or subprocess.Popen
    opener = opener or webbrowser.open
    process = popen(
        [cli, "serve", "--bg", FRONTEND_TARGET],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    lines: list[str] = []
    links: list[str] = []

    def pump() -> None:
        for raw in process.stdout:
            line = raw.rstrip()
            if not line:
                continue
            lines.append(line)
            out.detail(line)
            for link in TAILSCALE_LINK.findall(line):
                if link not in links:
                    links.append(link)
                    opener(link)
                    out.info("abri esse link no navegador: aceite lá (é uma vez só) e volte para esta janela")

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    try:
        code = process.wait(timeout=wait)
    except subprocess.TimeoutExpired:
        process.kill()
        reader.join(timeout=2)
        raise Stop(
            "\n".join(
                [
                    f"O Tailscale ficou {int(wait // 60)} min esperando você aceitar no navegador.",
                    *(
                        [f"Abra este link, aceite e rode o atalho de novo: {links[0]}"]
                        if links
                        else ["Abra o Tailscale, confira se está conectado e rode o atalho de novo."]
                    ),
                ]
            )
        ) from None
    reader.join(timeout=2)
    if code != 0:
        raise Stop(
            "\n".join(
                [
                    "O Tailscale recusou publicar o dashboard. Ele disse:",
                    *lines[-6:],
                    "Se ele pediu para ligar HTTPS/Serve: abra o link, aceite e rode de novo.",
                ]
            )
        )


def cmd_celular(_args) -> None:
    out = ui()
    out.header("Dashboard Financeiro", f"acesso pelo celular · {now_label()}")
    cli = tailscale_cli()
    if cli is None:
        raise Stop("\n".join(["Não encontrei o Tailscale neste computador.", *TAILSCALE_HELP]))
    url = phone_url(tailscale_json(cli, "status"))
    if url is None:
        raise Stop(
            "O Tailscale está instalado, mas desconectado (ou sem nome de máquina).\n"
            "Abra o Tailscale, entre na sua conta e rode este atalho de novo."
        )
    if serve_points_to_frontend(tailscale_json(cli, "serve", "status")):
        out.done("já estava publicado na sua rede")
    else:
        out.info("publicando o dashboard na sua rede Tailscale…")
        run_serve(cli)
        out.done("publicado só na sua rede")
    if not web_up():
        out.info("o dashboard está desligado agora: use “Iniciar Dashboard” antes de abrir no celular")
    out.write()
    out.card(
        "No iPhone",
        [
            ("Endereço", out.link(url, url.rstrip("/"))),
            ("1.", "Tailscale ligado no iPhone (mesma conta)"),
            ("2.", "abra o endereço no Safari"),
            ("3.", "Compartilhar › Adicionar à Tela de Início"),
            ("Precisa", "este computador ligado, com o dashboard no ar"),
            ("Desfazer", f'"{cli}" serve reset'),
        ],
        tone=tui.GOOD,
    )
    out.write()


BATS = {
    "Iniciar Dashboard.bat": "iniciar",
    "Parar Dashboard.bat": "parar",
    "Carregar pasta Entrada.bat": "carregar",
    "Ativar acesso pelo celular.bat": "celular",
}


BAT_TITLES = {
    "iniciar": "Iniciar Dashboard",
    "parar": "Parar Dashboard",
    "carregar": "Carregar pasta Entrada",
    "celular": "Acesso pelo celular",
}
PAUSE_ALWAYS = {"carregar", "celular"}  # janelas para ler o resultado


def bat_text(command: str) -> str:
    """Atalho do Windows. Caminhos entre aspas: a pasta tem espaço.
    UTF-8 no console (acentos e desenhos). A janela só espera tecla quando
    deu errado — ou sempre, no "carregar", que é para ler o resultado.
    """
    wait = "pause\r\n" if command in PAUSE_ALWAYS else "if errorlevel 1 pause\r\n"
    return (
        "@echo off\r\n"
        "rem Criado por launcher\\dashboard.py (comando 'atalhos').\r\n"
        "setlocal\r\n"
        "chcp 65001 >nul\r\n"
        f"title {BAT_TITLES.get(command, 'Dashboard Financeiro')}\r\n"
        "set PYTHONIOENCODING=utf-8\r\n"
        'set "PROJ=%~dp0investimentos-codigo-cf1"\r\n'
        'if exist "%PROJ%\\backend\\.venv\\Scripts\\python.exe" (\r\n'
        f'  "%PROJ%\\backend\\.venv\\Scripts\\python.exe" "%PROJ%\\launcher\\dashboard.py" {command}\r\n'
        ") else (\r\n"
        f'  py -3 "%PROJ%\\launcher\\dashboard.py" {command}\r\n'
        ")\r\n"
        f"{wait}"
    )


WIDGET_BAT = (
    "@echo off\r\n"
    "rem Abre o widget da carteira (liga o backend se estiver desligado).\r\n"
    'call "%~dp0investimentos-codigo-cf1\\widget\\iniciar_widget.bat"\r\n'
)


def cmd_atalhos(_args) -> None:
    for name, command in BATS.items():
        (DATA / name).write_bytes(bat_text(command).encode("ascii"))
        say(f"+ {DATA / name}")
    (DATA / "Abrir widget.bat").write_bytes(WIDGET_BAT.encode("ascii"))
    say(f"+ {DATA / 'Abrir widget.bat'}")
    (DATA / "Entrada").mkdir(exist_ok=True)
    say(f"+ {DATA / 'Entrada'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Liga, desliga e carrega o Dashboard Financeiro.")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("iniciar", help="liga tudo e abre o navegador")
    start.add_argument("--widget", action="store_true", help="abre também o widget")
    start.add_argument("--sem-navegador", action="store_true", help="não abre o navegador")
    sub.add_parser("parar", help="desliga backend e frontend")
    sub.add_parser("carregar", help="carrega os arquivos da pasta Entrada")
    sub.add_parser("atalhos", help="cria os atalhos .bat na pasta Dashboard Financeiro")
    sub.add_parser("celular", help="publica o dashboard na sua rede Tailscale (acesso pelo celular)")
    args = parser.parse_args(argv)
    commands = {
        "iniciar": cmd_iniciar,
        "parar": cmd_parar,
        "carregar": cmd_carregar,
        "atalhos": cmd_atalhos,
        "celular": cmd_celular,
    }
    try:
        commands[args.command](args)
    except Stop as exc:
        out = ui()
        out.write()
        out.panel("Não deu", str(exc).splitlines(), tone=tui.BAD)
        out.write()
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # erro inesperado: mensagem curta na tela, detalhes no log
        log = STATE / "erro.log"
        try:
            STATE.mkdir(exist_ok=True)
            with open(log, "a", encoding="utf-8") as handle:
                handle.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} {args.command}\n{traceback.format_exc()}")
        except OSError:
            pass
        out = ui()
        out.write()
        out.panel(
            "Não deu",
            [f"Erro inesperado: {type(exc).__name__}: {exc}"[:300], f"Detalhes em {log}"],
            tone=tui.BAD,
        )
        out.write()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
