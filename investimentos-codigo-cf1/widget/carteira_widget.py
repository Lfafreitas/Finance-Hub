"""Widget da carteira: uma janelinha que fica na área de trabalho
(Windows ou Linux) com o patrimônio, quanto rendeu, a variação do último
pregão, os últimos 30 dias e as notícias rápidas da análise do dia.

    python carteira_widget.py               # abre o widget
    python carteira_widget.py --ligar-backend   # liga o backend se estiver desligado

Só biblioteca padrão (tkinter vem com o Python do Windows; no Linux,
instale o pacote python3-tk). Lê tudo do backend local em 127.0.0.1:8000.

Arraste com o mouse para mudar de lugar. Botão direito: menu.
"""

from __future__ import annotations

import argparse
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import font as tkfont

import carteira_core as core

HERE = Path(__file__).resolve().parent
DASHBOARD_URL = "http://localhost:5173/"
SUMMARY_EVERY_MS = 60_000
NEWS_EVERY_MS = 15 * 60_000

# Mesmos tons do dashboard (fundo #171717). O sinal vai no texto, a cor só reforça.
COLORS = {
    "bg": "#171717",
    "panel": "#1f1f1f",
    "border": "#2e2e2e",
    "text": "#f5f5f5",
    "muted": "#a3a3a3",
    "faint": "#737373",
    "up": "#34d399",
    "down": "#f87171",
    "flat": "#d4d4d4",
    "line": "#3987e5",
    "ok": "#34d399",
    "stale": "#fbbf24",
    "offline": "#f87171",
}
WIDTH = 300


def _family(root: tk.Tk) -> str:
    available = set(tkfont.families(root))
    for name in ("Inter", "Segoe UI", "SF Pro Text", "Ubuntu", "Cantarell", "DejaVu Sans"):
        if name in available:
            return name
    return "TkDefaultFont"


class CarteiraWidget:
    def __init__(self, root: tk.Tk, start_backend: bool) -> None:
        self.root = root
        self.config = core.load_config()
        self.summary: dict | None = None
        self.insights: dict | None = None
        self.alerts: dict | None = None
        self.offline = False
        self.busy_quotes = False
        self.results: queue.Queue = queue.Queue()
        self.start_backend = start_backend
        self.backend_started = False

        family = _family(root)
        self.f_title = tkfont.Font(root=root, family=family, size=9, weight="bold")
        self.f_small = tkfont.Font(root=root, family=family, size=8)
        self.f_big = tkfont.Font(root=root, family=family, size=16, weight="bold")
        self.f_body = tkfont.Font(root=root, family=family, size=9)

        root.title("Carteira")
        root.configure(bg=COLORS["border"])
        root.overrideredirect(True)
        root.attributes("-topmost", bool(self.config["topmost"]))
        try:
            root.attributes("-alpha", float(self.config["alpha"]))
        except tk.TclError:
            pass  # alguns gerenciadores de janela do Linux não têm transparência
        self._place()

        self.frame = tk.Frame(root, bg=COLORS["bg"], padx=12, pady=10)
        self.frame.pack(fill="both", expand=True, padx=1, pady=1)
        self._menu()
        self._bind_drag(self.frame)
        self.render()
        self.root.after(200, self._loop)
        self.root.after(400, self._news_loop)
        self.root.after(250, self._pump)

    # --- janela -------------------------------------------------------------

    def _place(self) -> None:
        x, y = self.config.get("x"), self.config.get("y")
        if x is None or y is None:
            x = self.root.winfo_screenwidth() - WIDTH - 24
            y = 48
        self.root.geometry(f"+{int(x)}+{int(y)}")

    def _bind_drag(self, widget: tk.Widget) -> None:
        widget.bind("<ButtonPress-1>", self._drag_start)
        widget.bind("<B1-Motion>", self._drag_move)
        widget.bind("<ButtonRelease-1>", self._drag_end)
        widget.bind("<Button-3>", self._popup)
        widget.bind("<Button-2>", self._popup)  # macOS/alguns Linux

    def _drag_start(self, event) -> None:
        self._offset = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _drag_move(self, event) -> None:
        dx, dy = self._offset
        self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    def _drag_end(self, _event) -> None:
        self.config["x"], self.config["y"] = self.root.winfo_x(), self.root.winfo_y()
        core.save_config(self.config)

    def _menu(self) -> None:
        self.menu = tk.Menu(self.root, tearoff=0)
        self.topmost_var = tk.BooleanVar(value=bool(self.config["topmost"]))
        self.compact_var = tk.BooleanVar(value=bool(self.config["compact"]))
        self.news_var = tk.BooleanVar(value=bool(self.config["news"]))
        self.hidden_var = tk.BooleanVar(value=bool(self.config.get("hidden", False)))
        self.menu.add_command(label="Atualizar agora", command=self.load_summary)
        self.menu.add_command(label="Buscar cotações agora", command=lambda: self.refresh_quotes(force=True))
        self.menu.add_command(label="Abrir o dashboard", command=lambda: webbrowser.open(DASHBOARD_URL))
        self.menu.add_separator()
        self.menu.add_checkbutton(
            label="Sempre por cima", variable=self.topmost_var, command=self._toggle_topmost
        )
        self.menu.add_checkbutton(label="Compacto", variable=self.compact_var, command=self._toggle_compact)
        self.menu.add_checkbutton(label="Notícias", variable=self.news_var, command=self._toggle_news)
        self.menu.add_checkbutton(
            label="Esconder valores", variable=self.hidden_var, command=self._toggle_hidden
        )
        opacity = tk.Menu(self.menu, tearoff=0)
        for value in (1.0, 0.96, 0.9, 0.8, 0.7):
            opacity.add_command(label=f"{int(value * 100)}%", command=lambda v=value: self._set_alpha(v))
        self.menu.add_cascade(label="Opacidade", menu=opacity)
        self.menu.add_separator()
        self.menu.add_command(label="Fechar", command=self.root.destroy)

    def _popup(self, event) -> None:
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _toggle_topmost(self) -> None:
        self.config["topmost"] = self.topmost_var.get()
        self.root.attributes("-topmost", self.config["topmost"])
        core.save_config(self.config)

    def _toggle_compact(self) -> None:
        self.config["compact"] = self.compact_var.get()
        core.save_config(self.config)
        self.render()

    def _toggle_news(self) -> None:
        self.config["news"] = self.news_var.get()
        core.save_config(self.config)
        self.render()

    def _toggle_hidden(self) -> None:
        self.config["hidden"] = self.hidden_var.get()
        core.save_config(self.config)
        self.render()

    def _set_alpha(self, value: float) -> None:
        self.config["alpha"] = value
        try:
            self.root.attributes("-alpha", value)
        except tk.TclError:
            pass
        core.save_config(self.config)

    # --- dados (HTTP fora da thread da interface) -----------------------------

    def _background(self, kind: str, job) -> None:
        def run():
            try:
                self.results.put((kind, job(), None))
            except core.BackendOffline as exc:
                self.results.put((kind, None, exc))

        threading.Thread(target=run, daemon=True).start()

    def _pump(self) -> None:
        while not self.results.empty():
            kind, data, error = self.results.get_nowait()
            if kind == "summary":
                self.offline = error is not None
                if data is not None:
                    self.summary = data
                    if core.quotes_need_refresh(data.get("quotes_refreshed_at")):
                        self.refresh_quotes()
                elif self.start_backend and not self.backend_started:
                    self._launch_backend()
                self.render()
            elif kind == "insights":
                if data is not None:
                    self.insights = data
                    self.render()
            elif kind == "alerts":
                if data is not None:
                    self.alerts = data
                    self.render()
            elif kind == "quotes":
                self.busy_quotes = False
                if error is None:
                    self.load_summary()
        self.root.after(250, self._pump)

    def load_summary(self) -> None:
        """Busca o resumo uma vez (o menu "Atualizar agora" usa esta)."""
        self._background("summary", core.fetch_summary)

    def _loop(self) -> None:
        """Ciclo único de atualização, a cada minuto."""
        self.load_summary()
        self.root.after(SUMMARY_EVERY_MS, self._loop)

    def _news_loop(self) -> None:
        """A análise muda uma vez por dia; basta olhar a cada 15 minutos."""
        self._background("insights", core.fetch_insights)
        self._background("alerts", core.fetch_alerts)
        self.root.after(NEWS_EVERY_MS, self._news_loop)

    def refresh_quotes(self, force: bool = False) -> None:
        if self.busy_quotes and not force:
            return
        self.busy_quotes = True
        self._background("quotes", core.refresh_quotes)

    def _launch_backend(self) -> None:
        found = core.backend_command(HERE)
        self.backend_started = True
        if found is None:
            return
        command, cwd = found
        log = core.config_path().with_name("backend.log")
        log.parent.mkdir(parents=True, exist_ok=True)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with open(log, "ab") as handle:
            subprocess.Popen(command, cwd=cwd, stdout=handle, stderr=handle, creationflags=flags)
        self.root.after(6000, self.load_summary)

    # --- desenho ------------------------------------------------------------

    @property
    def hidden(self) -> bool:
        return bool(self.config.get("hidden", False))

    def _label(self, parent, text, font, color="text", **pack) -> tk.Label:
        label = tk.Label(
            parent, text=text, font=font, fg=COLORS[color], bg=COLORS["bg"], anchor="w", justify="left"
        )
        label.pack(fill="x", **pack)
        self._bind_drag(label)
        return label

    def render(self) -> None:
        for child in self.frame.winfo_children():
            child.destroy()

        state = core.freshness(self.summary, self.offline)
        header = tk.Frame(self.frame, bg=COLORS["bg"])
        header.pack(fill="x")
        self._bind_drag(header)
        title = tk.Label(header, text="Carteira", font=self.f_title, fg=COLORS["text"], bg=COLORS["bg"])
        title.pack(side="left")
        self._bind_drag(title)
        status = tk.Label(
            header, text=f"● {state.label}", font=self.f_small, fg=COLORS[state.level], bg=COLORS["bg"]
        )
        status.pack(side="right")
        self._bind_drag(status)

        if state.level == "offline":
            self._label(self.frame, "Não consegui falar com o backend.", self.f_body, "muted", pady=(8, 0))
            self._label(
                self.frame,
                "Ligue o uvicorn (pasta backend) ou use\n“Abrir o dashboard” no botão direito.",
                self.f_small,
                "faint",
                pady=(2, 0),
            )
            return

        alert = core.alert_line(self.alerts)
        if alert is not None:
            text, level = alert
            line = tk.Label(
                self.frame,
                text=text,
                font=self.f_body,
                fg=COLORS[level],
                bg=COLORS["bg"],
                anchor="w",
                justify="left",
                wraplength=WIDTH - 30,
                cursor="hand2",
            )
            line.pack(fill="x", pady=(8, 0))
            line.bind("<Button-1>", lambda _e: webbrowser.open(DASHBOARD_URL))
            line.bind("<Button-3>", self._popup)

        items = core.blocks(self.summary)
        if not items:
            self._label(self.frame, "Nenhum investimento ou saldo ainda.", self.f_body, "muted", pady=(8, 0))
            return
        for block in items:
            self._render_block(block)
        if self.config.get("news", True):
            self._render_news()

    def _render_news(self) -> None:
        label, old = core.report_label(self.insights)
        header = tk.Frame(self.frame, bg=COLORS["bg"])
        header.pack(fill="x", pady=(12, 0))
        self._bind_drag(header)
        parts = (("NOTÍCIAS", "faint", "left"), (label, "stale" if old else "faint", "right"))
        for text, color, side in parts:
            item = tk.Label(header, text=text, font=self.f_small, fg=COLORS[color], bg=COLORS["bg"])
            item.pack(side=side)
            self._bind_drag(item)
        items = core.news_items(self.insights)
        if not items:
            self._label(self.frame, "A análise do dia ainda não chegou.", self.f_small, "faint", pady=(2, 0))
            return
        for news in items:
            row = tk.Frame(self.frame, bg=COLORS["bg"])
            row.pack(fill="x", pady=(4, 0))
            title = tk.Label(
                row,
                text=f"{news['ticker']} · {news['title']}" if news["ticker"] else news["title"],
                font=self.f_small,
                fg=COLORS["text"],
                bg=COLORS["bg"],
                anchor="w",
                justify="left",
                wraplength=WIDTH - 26,
                cursor="hand2" if news["url"] else "",
            )
            title.pack(fill="x")
            meta = tk.Label(
                row,
                text=" · ".join(p for p in (news["source"], news["date"]) if p),
                font=self.f_small,
                fg=COLORS["faint"],
                bg=COLORS["bg"],
                anchor="w",
            )
            meta.pack(fill="x")
            if news["url"]:
                # Clique abre a notícia no navegador; o resto da janela continua arrastável.
                title.bind("<Button-1>", lambda _e, url=news["url"]: webbrowser.open(url))
            for widget in (row, meta):
                self._bind_drag(widget)
            title.bind("<Button-3>", self._popup)
        more = tk.Label(
            self.frame,
            text="Ver a análise completa no dashboard",
            font=self.f_small,
            fg=COLORS["line"],
            bg=COLORS["bg"],
            anchor="w",
            cursor="hand2",
        )
        more.pack(fill="x", pady=(6, 0))
        more.bind("<Button-1>", lambda _e: webbrowser.open(DASHBOARD_URL))

    def _render_block(self, block: dict) -> None:
        currency = block["currency_code"]
        compact = bool(self.config["compact"])
        self._label(
            self.frame,
            f"{core.TITLES.get(currency, 'Em ' + currency).upper()} · {currency}",
            self.f_small,
            "faint",
            pady=(10, 0),
        )
        self._label(self.frame, core.money(block["total"], currency, self.hidden), self.f_big)

        has_investments = core._decimal(block["investments_cost"]) not in (None, 0)
        if has_investments:
            result = block["result"]
            pct = core.signed_percent(block["result_pct"])
            line = f"{core.signed_money(result, currency, self.hidden)} ({pct}) desde o início"
            self._label(self.frame, line, self.f_body, core.tone(result))
        if block.get("day_change") is not None:
            day = block["day_change"]
            line = (
                f"Último pregão ({core.short_date(block['day_date'])}): "
                f"{core.signed_money(day, currency, self.hidden)} "
                f"({core.signed_percent(block['day_change_pct'])})"
            )
            self._label(self.frame, line, self.f_body, core.tone(day))
        if block.get("unpriced"):
            self._label(
                self.frame, f"Sem cotação: {', '.join(block['unpriced'])} (pelo custo)", self.f_small, "faint"
            )

        if compact:
            return
        values = [point["value"] for point in block.get("spark", [])]
        if len(values) >= 2:
            canvas = tk.Canvas(self.frame, width=WIDTH - 26, height=36, bg=COLORS["bg"], highlightthickness=0)
            canvas.pack(fill="x", pady=(6, 2))
            self._bind_drag(canvas)
            points = core.spark_points(values, WIDTH - 26, 36)
            flat = [c for point in points for c in point]
            canvas.create_line(*flat, fill=COLORS["line"], width=2, capstyle="round", joinstyle="round")
            x, y = points[-1]
            canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=COLORS["line"], outline=COLORS["bg"], width=2)
            self._label(self.frame, "investimentos · últimos 30 dias", self.f_small, "faint")
        for move in block.get("movers", [])[:3]:
            row = tk.Frame(self.frame, bg=COLORS["bg"])
            row.pack(fill="x", pady=(2, 0))
            self._bind_drag(row)
            for text, color, side, gap in (
                (move["ticker"], "text", "left", 0),
                (core.signed_percent(move["change_pct"]), core.tone(move["change_pct"]), "right", 0),
                (core.price(move["price"], currency), "muted", "right", 10),
            ):
                label = tk.Label(row, text=text, font=self.f_small, fg=COLORS[color], bg=COLORS["bg"], padx=0)
                label.pack(side=side, padx=(gap, 0) if side == "right" else 0)
                self._bind_drag(label)


def main() -> None:
    parser = argparse.ArgumentParser(description="Widget da carteira")
    parser.add_argument(
        "--ligar-backend", action="store_true", help="liga o backend local se estiver desligado"
    )
    args = parser.parse_args()
    root = tk.Tk()
    CarteiraWidget(root, start_backend=args.ligar_backend)
    root.mainloop()


if __name__ == "__main__":
    sys.exit(main())
