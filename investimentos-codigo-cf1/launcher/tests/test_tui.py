"""Saída do iniciador: cores só no terminal, glifos pela capacidade, cartões alinhados."""

import io
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tui

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\]8;;.*?\x1b\\")


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


class TestDeteccao:
    def test_arquivo_ou_no_color_e_texto_puro(self):
        assert tui.detect(io.StringIO(), env={}, platform="linux") == (False, tui.SAFE)
        assert tui.detect(FakeTTY(), env={"NO_COLOR": "1"}, platform="linux") == (False, tui.SAFE)

    def test_windows_terminal_rico_console_antigo_seguro(self):
        assert tui.detect(FakeTTY(), env={"WT_SESSION": "x"}, platform="win32") == (True, tui.RICH)
        assert tui.detect(FakeTTY(), env={}, platform="win32") == (True, tui.SAFE)

    def test_linux_com_cor(self):
        assert tui.detect(FakeTTY(), env={"TERM": "xterm-256color"}, platform="linux") == (True, tui.RICH)
        assert tui.detect(FakeTTY(), env={"TERM": "dumb"}, platform="linux")[0] is False


class TestTextoPuro:
    def test_etapa_sem_codigos_de_controle(self):
        out = io.StringIO()
        c = tui.Console(stream=out, color=False)

        with c.task("aplicando as migrações", "banco em dia"):
            pass

        text = out.getvalue()
        assert "\x1b" not in text and "\r" not in text
        assert "- aplicando as migrações" in text
        assert "ok: banco em dia (" in text

    def test_etapa_que_falha_avisa_e_repassa_o_erro(self):
        out = io.StringIO()
        c = tui.Console(stream=out, color=False)

        with pytest.raises(RuntimeError), c.task("ligando o backend"):
            raise RuntimeError("x")

        assert "falhou: ligando o backend (" in out.getvalue()

    def test_link_vira_texto_sem_cor(self):
        c = tui.Console(stream=io.StringIO(), color=False)
        assert c.link("http://localhost:5173/", "localhost") == "localhost"


class TestTerminalVivo:
    def test_etapa_termina_com_marca_e_texto_final(self):
        out = FakeTTY()
        c = tui.Console(stream=out, color=True, glyphs=tui.RICH)

        with c.task("ligando o frontend", "frontend no ar") as t:
            t.notes.append("✓ arquivo.ofx")

        plain = ANSI.sub("", out.getvalue())
        last = plain.split("\r")[-1]
        assert "✓ frontend no ar" in last
        assert "✓ arquivo.ofx" in last

    def test_console_antigo_troca_glifos_que_a_fonte_nao_tem(self):
        out = FakeTTY()
        c = tui.Console(stream=out, color=True, glyphs=tui.SAFE)
        c.detail("✓ a.ofx / ✗ b.pdf")
        assert "OK a.ofx / X b.pdf" in ANSI.sub("", out.getvalue())

    def test_link_clicavel_so_no_terminal_rico(self):
        rich = tui.Console(stream=FakeTTY(), color=True, glyphs=tui.RICH)
        safe = tui.Console(stream=FakeTTY(), color=True, glyphs=tui.SAFE)
        assert "\x1b]8;;http://x/\x1b\\" in rich.link("http://x/", "x")
        assert safe.link("http://x/", "x") == "x"


@pytest.mark.parametrize("glyphs", [tui.RICH, tui.SAFE])
def test_cartao_com_todas_as_linhas_da_mesma_largura(glyphs):
    out = FakeTTY()
    c = tui.Console(stream=out, color=True, glyphs=glyphs)

    c.card("Pronto em 6,4 s", [("Dashboard", c.link("http://localhost:5173/", "http://localhost:5173")), ("API", "x")])

    lines = [ANSI.sub("", line) for line in out.getvalue().splitlines()]
    assert len({len(line) for line in lines}) == 1, lines


def test_largura_visivel_ignora_cor_e_link():
    c = tui.Console(stream=FakeTTY(), color=True, glyphs=tui.RICH)
    assert tui._visible_len(c.paint("abc", tui.GOOD, bold=True) + c.link("http://x/", "de")) == 5


@pytest.mark.parametrize(("seconds", "text"), [(0.84, "0,8 s"), (12.4, "12 s"), (65, "1 min 05 s")])
def test_tempo_por_extenso(seconds, text):
    assert tui.format_seconds(seconds) == text
