"""Fatura do cartão em PDF, sintética, para os testes (Fatura-PDF).

Monta um PDF de verdade, à mão (sem biblioteca), com o mesmo desenho da
fatura real: células de texto em colunas na mesma altura. Nomes e
valores são fictícios.
"""

from __future__ import annotations

Line = list[tuple[int, str]]

# Uma fatura fictícia de fevereiro/2026 que confere com o próprio resumo:
# compras 326,94 - outros 21,46 = 305,48 lidos; pagamento 300,00.
FATURA_LINES: list[Line] = [
    [(40, "FATURA 06 FEV 2026"), (330, "EMISSÃO E ENVIO 30 JAN 2026")],
    # Simulação de parcelamento: "Total a pagar" aqui NÃO é o total.
    [(40, "Total a pagar"), (330, "R$ 800,00"), (450, "R$ 850,00")],
    [(40, "RESUMO DA FATURA ATUAL")],
    [(40, "Fatura anterior"), (450, "R$ 300,00")],
    [(40, "Pagamento recebido"), (450, "-R$ 300,00")],
    [(40, "Total de compras de todos os cartões, 30 DEZ a 30 JAN"), (450, "R$ 326,94")],
    [(40, "Outros lançamentos"), (450, "-R$ 21,46")],
    [(40, "Total a pagar"), (450, "R$ 305,48")],
    [(40, "TRANSAÇÕES"), (150, "DE 30 DEZ A 30 JAN")],
    [(40, "Titular Exemplo"), (450, "R$ 305,48")],
    [(40, "30 DEZ"), (90, "•••• 1234"), (150, "Loja Exemplo - Parcela 2/3"), (450, "R$ 50,00")],
    [(40, "03 JAN"), (150, "Lanche - NuPay"), (450, "R$ 35,40")],
    [(40, "10 JAN"), (90, "•••• 1234"), (150, "Mercado Exemplo"), (450, "R$ 100,00")],
    [(40, "12 JAN"), (150, "Estorno de Loja Devolvida"), (450, "-R$ 20,00")],
    [(40, "15 JAN"), (150, "Desconto Antecipação Loja Exemplo"), (450, "-R$ 1,46")],
    [(40, "Pagamentos e Financiamentos"), (450, "-R$ 158,46")],
    [(40, "05 JAN"), (150, "Pagamento em 05 JAN"), (450, "-R$ 300,00")],
    [(40, "06 JAN"), (150, "Saldo restante da fatura anterior"), (450, "R$ 0,00")],
    [(40, "08 JAN"), (150, "Pessoa Exemplo - Parcela 1/5"), (450, "R$ 141,54")],
    [(40, "Total a pagar: R$ 707,70 (valor da transação de R$ 600,00 + R$ 9,00 de IOF +")],
    [(40, "R$ 98,70 de juros) divididos em 5 parcelas de R$ 141,54.")],
    [(40, "3 de 3")],
]


def cells(lines: list[Line]) -> list[list[str]]:
    """O que `pdf_lines` devolve para essas linhas."""
    return [[text for _x, text in line] for line in lines]


def _escape(text: str) -> bytes:
    raw = text.encode("cp1252")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def build_pdf(pages: list[list[Line]]) -> bytes:
    """PDF mínimo, Helvetica/WinAnsi, uma linha a cada 18 pontos."""
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",  # páginas: preenchido abaixo
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    kids: list[int] = []
    for lines in pages:
        stream = b""
        y = 800
        for line in lines:
            for x, text in line:
                stream += b"BT /F1 9 Tf %d %d Td (" % (x, y) + _escape(text) + b") Tj ET\n"
            y -= 18
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream")
        content_id = len(objects)
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % content_id
        )
        kids.append(len(objects))
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids),
        len(kids),
    )

    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return out


def fatura_pdf(lines: list[Line] | None = None, split_at: int | None = None) -> bytes:
    """A fatura fictícia em PDF; `split_at` quebra em duas páginas."""
    lines = FATURA_LINES if lines is None else lines
    if split_at is None:
        return build_pdf([lines])
    return build_pdf([lines[:split_at], lines[split_at:]])
