"""Saída do iniciador no terminal: cores, etapas com spinner e cartão final.

Só biblioteca padrão (o iniciador roda antes de qualquer dependência ser
instalada). Mesma identidade do dashboard: fundo do terminal, texto frio,
acento azul-gelo, verde/âmbar/vermelho só para sinal.

Três níveis, escolhidos sozinhos:
- RICO: Windows Terminal, VS Code, Linux/macOS com cores — glifos
  arredondados (╭╮), spinner ◐◓◑◒, ✓/✗ e link clicável;
- SEGURO: console antigo do Windows (conhost com Consolas) — cores, mas só
  glifos que essa fonte desenha (┌┐, |/-\\, OK/X);
- SIMPLES: saída redirecionada para arquivo ou NO_COLOR definido — texto
  puro, uma linha por evento, sem códigos de controle.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

# Paleta (a mesma do dashboard).
ACCENT = (143, 193, 227)  # azul-gelo
TEXT = (228, 233, 236)
MUTED = (115, 132, 143)
FAINT = (83, 99, 109)
GOOD = (76, 195, 138)
WARN = (226, 177, 73)
BAD = (240, 122, 106)


@dataclass(frozen=True)
class Glyphs:
    tl: str
    tr: str
    bl: str
    br: str
    h: str
    v: str
    ok: str
    fail: str
    warn: str
    bullet: str
    spinner: tuple[str, ...]
    spark: str


RICH = Glyphs("╭", "╮", "╰", "╯", "─", "│", "✓", "✗", "!", "•", ("◐", "◓", "◑", "◒"), "▁▃▂▅▇")
SAFE = Glyphs("┌", "┐", "└", "┘", "─", "│", "OK", "X", "!", "-", ("|", "/", "-", "\\"), "")


def _enable_windows_vt() -> bool:
    """Liga as sequências de cor no console do Windows (10 ou mais novo)."""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))  # VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        return False


def detect(stream=None, env=None, platform: str | None = None) -> tuple[bool, Glyphs]:
    """(usa cor?, glifos). Puro o bastante para testar com env/plataforma falsos."""
    stream = stream or sys.stdout
    env = os.environ if env is None else env
    platform = platform or sys.platform
    if env.get("NO_COLOR") or not getattr(stream, "isatty", lambda: False)():
        return False, SAFE
    if platform.startswith("win"):
        modern = bool(env.get("WT_SESSION") or env.get("TERM_PROGRAM") == "vscode")
        color = _enable_windows_vt() if stream is sys.stdout else True
        return color, RICH if modern else SAFE
    return env.get("TERM") != "dumb", RICH


def _visible_len(text: str) -> int:
    """Comprimento na tela (ignora as sequências de cor e de link)."""
    out, i = 0, 0
    while i < len(text):
        if text[i] == "\x1b":
            if text.startswith("\x1b]", i):  # OSC: até o ST (\x1b\\)
                end = text.find("\x1b\\", i)
                i = len(text) if end < 0 else end + 2
            else:  # CSI: até a letra final
                j = i + 2
                while j < len(text) and not text[j].isalpha():
                    j += 1
                i = j + 1
            continue
        out += 1
        i += 1
    return out


def format_seconds(seconds: float) -> str:
    """0,8 s · 12 s · 1 min 05 s"""
    if seconds < 10:
        return f"{seconds:.1f} s".replace(".", ",")
    if seconds < 60:
        return f"{seconds:.0f} s"
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes} min {rest:02d} s"


@dataclass
class Task:
    doing: str
    done: str
    notes: list[str] = field(default_factory=list)


class Console:
    def __init__(self, stream=None, color: bool | None = None, glyphs: Glyphs | None = None) -> None:
        self.stream = stream or sys.stdout
        if self.stream is sys.stdout:
            try:  # acentos e glifos sem depender da página de código do Windows
                sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
            except (AttributeError, ValueError):
                pass
        detected_color, detected_glyphs = detect(self.stream)
        self.color = detected_color if color is None else color
        self.g = glyphs or (detected_glyphs if self.color else SAFE)
        self.live = self.color  # spinner só onde dá para reescrever a linha
        self._lock = threading.Lock()
        self.started = time.monotonic()

    # --- estilo ---------------------------------------------------------------

    def paint(self, text: str, rgb: tuple[int, int, int] | None = None, *, bold=False, dim=False) -> str:
        if not self.color:
            return text
        codes = []
        if bold:
            codes.append("1")
        if dim:
            codes.append("2")
        if rgb:
            codes.append(f"38;2;{rgb[0]};{rgb[1]};{rgb[2]}")
        return f"\x1b[{';'.join(codes)}m{text}\x1b[0m" if codes else text

    def link(self, url: str, label: str | None = None) -> str:
        """Link clicável (OSC 8) onde o terminal entende; texto puro nos outros."""
        label = label or url
        if not self.color or self.g is SAFE:
            return label
        return f"\x1b]8;;{url}\x1b\\{label}\x1b]8;;\x1b\\"

    def write(self, text: str = "") -> None:
        with self._lock:
            self.stream.write(text + "\n")
            self.stream.flush()

    # --- blocos ---------------------------------------------------------------

    def header(self, title: str, subtitle: str) -> None:
        spark = self.paint(self.g.spark + "  ", ACCENT) if self.g.spark else ""
        self.write()
        self.write(f"  {spark}{self.paint(title, TEXT, bold=True)}  {self.paint(subtitle, MUTED)}")
        self.write(f"  {self.paint(self.g.h * (_visible_len(spark) + len(title) + 2 + len(subtitle)), FAINT)}")
        self.write()

    def card(self, title: str, rows: list[tuple[str, str]], tone=ACCENT) -> None:
        """Cartão com borda: título na borda de cima e linhas "rótulo  valor"."""
        label_w = max((len(k) for k, _ in rows), default=0)
        if label_w:
            body = [f"{self.paint(k.ljust(label_w), MUTED)}   {v}" for k, v in rows]
        else:
            body = [v for _k, v in rows]
        width = max([_visible_len(b) for b in body] + [len(title) + 2]) + 4
        top_fill = width - len(title) - 3
        self.write(
            f"  {self.paint(self.g.tl + self.g.h, tone)} {self.paint(title, tone, bold=True)} "
            f"{self.paint(self.g.h * top_fill + self.g.tr, tone)}"
        )
        for b in body:
            pad = width - _visible_len(b) - 2
            self.write(f"  {self.paint(self.g.v, tone)}  {b}{' ' * pad}{self.paint(self.g.v, tone)}")
        self.write(f"  {self.paint(self.g.bl + self.g.h * width + self.g.br, tone)}")

    def note(self, text: str, rgb=MUTED) -> None:
        self.write(f"  {self.paint(text, rgb)}")

    def detail(self, text: str) -> None:
        """Linha de detalhe embaixo de uma etapa (ex.: arquivos carregados)."""
        if self.g is SAFE:  # Consolas não desenha ✓/✗
            text = text.replace("✓", "OK").replace("✗", "X")
        self.write(f"      {self.paint(text, MUTED)}")

    def info(self, text: str) -> None:
        self.write(f"  {self.paint(self.g.bullet, FAINT)} {self.paint(text, MUTED)}")

    # --- etapas ---------------------------------------------------------------

    @contextmanager
    def task(self, doing: str, done: str | None = None) -> Iterator[Task]:
        """Etapa com spinner enquanto roda; no fim, ✓ + tempo (ou ✗).
        O texto pode mudar no meio (`t.doing = ...`, `t.done = ...`).
        """
        handle = Task(doing, done or doing)
        start = time.monotonic()
        stop = threading.Event()
        spinner = None
        if self.live:

            def spin() -> None:
                frames = self.g.spinner
                i = 0
                while not stop.wait(0.12):
                    elapsed = format_seconds(time.monotonic() - start)
                    frame = self.paint(frames[i % len(frames)], ACCENT)
                    line = f"  {frame} {self.paint(handle.doing, TEXT)}  {self.paint(elapsed, FAINT)}"
                    with self._lock:
                        self.stream.write("\r\x1b[2K" + line)
                        self.stream.flush()
                    i += 1

            with self._lock:
                self.stream.write(f"  {self.paint(self.g.spinner[0], ACCENT)} {self.paint(doing, TEXT)}")
                self.stream.flush()
            spinner = threading.Thread(target=spin, daemon=True)
            spinner.start()
        else:
            self.write(f"  {self.g.bullet} {doing}")
        try:
            yield handle
        except BaseException:
            self._finish(stop, spinner, start, self.paint(self.g.fail, BAD, bold=True), handle.doing, failed=True)
            raise
        self._finish(stop, spinner, start, self.paint(self.g.ok, GOOD, bold=True), handle.done)
        for line in handle.notes:
            self.detail(line)

    def done(self, text: str) -> None:
        """Etapa que não precisou fazer nada (ex.: já estava ligado)."""
        self.write(f"  {self.paint(self.g.ok, GOOD, bold=True)} {self.paint(text, TEXT)}")

    def panel(self, title: str, lines: list[str], tone=BAD) -> None:
        """Quadro de texto livre (ex.: erro com o que fazer)."""
        self.card(title, [("", line) for line in lines], tone=tone)

    def _finish(self, stop, spinner, start, mark: str, text: str, failed: bool = False) -> None:
        stop.set()
        if spinner is not None:
            spinner.join()
        elapsed = format_seconds(time.monotonic() - start)
        if self.live:
            line = f"  {mark} {self.paint(text, BAD if failed else TEXT)}  {self.paint(elapsed, FAINT)}"
            with self._lock:
                self.stream.write("\r\x1b[2K" + line + "\n")
                self.stream.flush()
        else:
            self.write(f"    {'falhou' if failed else 'ok'}: {text} ({elapsed})")

    def total(self) -> str:
        return format_seconds(time.monotonic() - self.started)

    def countdown(self, seconds: int, message: str) -> None:
        """Contagem para fechar a janela (só no terminal ao vivo)."""
        if not self.live:
            return
        try:
            for left in range(seconds, 0, -1):
                with self._lock:
                    self.stream.write("\r\x1b[2K  " + self.paint(message.format(left), FAINT))
                    self.stream.flush()
                time.sleep(1)
        finally:
            with self._lock:
                self.stream.write("\r\x1b[2K")
                self.stream.flush()
