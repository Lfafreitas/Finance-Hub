"""Lógica do widget da carteira, sem interface gráfica (testável).

Só biblioteca padrão. Todo número vem calculado do backend local; aqui
só se formata para leitura e se decide o que mostrar.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

API = os.environ.get("CARTEIRA_API", "http://127.0.0.1:8000")
SYMBOLS = {"BRL": "R$", "USD": "US$", "EUR": "€"}
TITLES = {"BRL": "Em reais", "USD": "Em dólar"}
# Cotação mais velha que isto é buscada de novo (mesmo limite da tela Análises).
QUOTES_MAX_AGE_SECONDS = 15 * 60


class BackendOffline(Exception):
    """O backend local não respondeu."""


# --- Formatação ---------------------------------------------------------------


def _decimal(value: str | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _group(number: Decimal, places: int) -> str:
    text = f"{abs(number):,.{places}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


MASK = "•••••"


def money(value, currency: str, hidden: bool = False) -> str:
    """ "R$ 1.234,56", "US$ 506,86", "-R$ 13,60". Com `hidden`, "R$ •••••"
    (nem o sinal aparece: ele já diz se a carteira está no vermelho).
    """
    number = _decimal(value)
    if number is None:
        return "—"
    symbol = SYMBOLS.get(currency, currency)
    if hidden:
        return f"{symbol} {MASK}"
    sign = "-" if number < 0 else ""
    return f"{sign}{symbol} {_group(number, 2)}"


def signed_money(value, currency: str, hidden: bool = False) -> str:
    number = _decimal(value)
    if number is None:
        return "—"
    if hidden:
        return money(number, currency, hidden=True)
    text = money(abs(number), currency)
    if number > 0:
        return f"+{text}"
    if number < 0:
        return f"-{text}"
    return text


def signed_percent(fraction) -> str:
    """0.0112 → "+1,12%"."""
    number = _decimal(fraction)
    if number is None:
        return "—"
    text = f"{_group(number * 100, 2)}%"
    if number > 0:
        return f"+{text}"
    if number < 0:
        return f"-{text}"
    return text


def price(value, currency: str) -> str:
    number = _decimal(value)
    if number is None:
        return "—"
    return f"{SYMBOLS.get(currency, currency)} {_group(number, 2)}"


def tone(value) -> str:
    """ "up", "down" ou "flat" — a cor nunca é a única pista: o sinal vai no texto."""
    number = _decimal(value)
    if number is None or number == 0:
        return "flat"
    return "up" if number > 0 else "down"


def short_date(iso: str | None) -> str:
    if not iso:
        return ""
    return f"{iso[8:10]}/{iso[5:7]}"


# --- Sparkline ------------------------------------------------------------------


def spark_points(values: list, width: int, height: int, pad: int = 3) -> list[tuple[float, float]]:
    """Coordenadas de tela para a linha dos últimos dias. Série constante
    vira uma linha reta no meio; menos de 2 pontos, nada.
    """
    numbers = [n for n in (_decimal(v) for v in values) if n is not None]
    if len(numbers) < 2:
        return []
    low, high = min(numbers), max(numbers)
    span = high - low
    step = (width - 2 * pad) / (len(numbers) - 1)
    points = []
    for index, number in enumerate(numbers):
        x = pad + index * step
        if span == 0:
            y = height / 2
        else:
            y = pad + float((high - number) / span) * (height - 2 * pad)
        points.append((round(x, 2), round(y, 2)))
    return points


# --- Estado ---------------------------------------------------------------------


@dataclass(frozen=True)
class Freshness:
    level: str  # "ok" | "stale" | "offline"
    label: str


def quotes_need_refresh(refreshed_at: str | None, now: datetime | None = None) -> bool:
    if refreshed_at is None:
        return True
    now = now or datetime.now(timezone.utc)
    try:
        when = datetime.fromisoformat(refreshed_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (now - when).total_seconds() > QUOTES_MAX_AGE_SECONDS


def freshness(summary: dict | None, offline: bool, now: datetime | None = None) -> Freshness:
    if offline or summary is None:
        return Freshness("offline", "backend desligado")
    refreshed = summary.get("quotes_refreshed_at")
    if refreshed is None:
        return Freshness("stale", "sem cotação automática")
    when = datetime.fromisoformat(refreshed.replace("Z", "+00:00")).astimezone()
    label = f"cotações {when:%H:%M}"
    if quotes_need_refresh(refreshed, now):
        return Freshness("stale", f"{label} (buscando)")
    return Freshness("ok", label)


def blocks(summary: dict | None) -> list[dict]:
    """Moedas em ordem estável: real primeiro, dólar depois, o resto em
    ordem alfabética. Cada moeda é um bloco; nada é somado.
    """
    if not summary:
        return []
    order = {"BRL": 0, "USD": 1}
    return sorted(
        summary.get("totals_by_currency", []),
        key=lambda b: (order.get(b["currency_code"], 2), b["currency_code"]),
    )


# --- Notícias -------------------------------------------------------------------

NEWS_LIMIT = 4


def news_items(index: dict | None, limit: int = NEWS_LIMIT) -> list[dict]:
    """As primeiras notícias da análise mais recente, na ordem do relatório
    (quem escreveu já pôs as mais importantes primeiro). Link que não é
    http(s) não vira clique.
    """
    latest = (index or {}).get("latest")
    if not latest:
        return []
    items = []
    for item in latest["report"].get("news", [])[:limit]:
        url = item.get("url") or ""
        items.append(
            {
                "ticker": item.get("ticker") or item.get("topic") or "",
                "title": item["title"],
                "source": item.get("source") or "",
                "date": short_date(item.get("published_at")),
                "url": url if url.startswith(("https://", "http://")) else None,
            }
        )
    return items


def report_label(index: dict | None, today=None) -> tuple[str, bool]:
    """("análise de 13/10", velha?) — velha quando é de antes de ontem."""
    latest = (index or {}).get("latest")
    if not latest:
        return ("sem análise ainda", True)
    day = date.fromisoformat(latest["report_date"])
    today = today or date.today()
    return (f"análise de {day:%d/%m}", day < today - timedelta(days=1))


def headline(index: dict | None) -> str | None:
    latest = (index or {}).get("latest")
    return latest["report"].get("headline") if latest else None


# --- Alertas --------------------------------------------------------------------


def unread_alerts(index: dict | None) -> list[dict]:
    """Alertas ainda não lidos (o backend já manda o mais novo primeiro)."""
    return [item["alert"] for item in (index or {}).get("alerts", []) if not item.get("read")]


def alert_line(index: dict | None) -> tuple[str, str] | None:
    """("⚠ Título do alerta mais novo (+1)", nível) ou None sem alerta não
    lido. Nível "offline" (vermelho) para CRÍTICA, "stale" (âmbar) para ALTA.
    """
    unread = unread_alerts(index)
    if not unread:
        return None
    first = unread[0]
    level = "offline" if any(a["severity"] == "CRITICA" for a in unread) else "stale"
    extra = f" (+{len(unread) - 1})" if len(unread) > 1 else ""
    return (f"⚠ {first['title']}{extra}", level)


# --- HTTP -----------------------------------------------------------------------


def _request(method: str, path: str, timeout: float):
    request = urllib.request.Request(API + path, method=method, data=b"" if method == "POST" else None)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read() or b"null")
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
        raise BackendOffline(str(exc)) from exc


def fetch_summary(timeout: float = 15) -> dict:
    return _request("GET", "/performance/widget", timeout)


def fetch_insights(timeout: float = 15) -> dict:
    """Análise do dia (notícias) que a tarefa agendada deixa na pasta
    claude-analises; o backend só lê o arquivo.
    """
    return _request("GET", "/insights", timeout)


def fetch_alerts(timeout: float = 15) -> dict:
    """Alertas da busca de hora em hora (últimos 2 dias)."""
    return _request("GET", "/insights/alerts?days=2", timeout)


def refresh_quotes(timeout: float = 90) -> dict:
    """Pede ao backend para buscar as cotações (só os códigos dos ativos
    saem do computador, como na tela Análises).
    """
    return _request("POST", "/prices/refresh", timeout)


# --- Configuração ---------------------------------------------------------------


def config_path() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "carteira-widget" / "config.json"


DEFAULTS = {
    "x": None,
    "y": None,
    "topmost": True,
    "compact": False,
    "alpha": 0.96,
    "news": True,
    "hidden": False,
}


def load_config(path: Path | None = None) -> dict:
    path = path or config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}


def save_config(config: dict, path: Path | None = None) -> None:
    path = path or config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    except OSError:
        pass  # sem permissão de escrita: o widget segue funcionando


def backend_command(widget_dir: Path) -> tuple[list[str], Path] | None:
    """Comando para ligar o backend com o Python do venv do projeto, se
    ele existir em ../backend/.venv. Nada é instalado.
    """
    backend = widget_dir.parent / "backend"
    candidates = [
        backend / ".venv" / "Scripts" / "python.exe",
        backend / ".venv" / "bin" / "python",
    ]
    for python in candidates:
        if python.exists():
            return (
                [str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
                backend,
            )
    return None
