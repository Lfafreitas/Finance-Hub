"""Contexto da carteira para conversar com o Claude (pela assinatura).

O dashboard não chama nenhuma IA: ele monta este texto, e o usuário o leva
para o Claude (app ou claude.ai) junto com a pergunta. Por isso o texto é
curto (cabe num link) e só tem o que a conversa precisa:

- investimentos: posições, pesos, resultado, desempenho de preço;
- alocação por classe e o alvo que ele definiu;
- comparação com a referência (SPY/CDI) e vencimentos;
- caixa SÓ em totais por moeda (reserva, disponível, gasto médio, taxa
  de poupança) — nenhuma descrição de extrato sai daqui;
- empresas por trás dos ETFs (composição trazida pela análise diária);
- manchete e pontos da última análise diária e alertas não lidos.

Moedas nunca se somam: cada bloco é de uma moeda.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.services import insights_service, overview_service
from app.services.agenda_service import get_agenda
from app.services.allocation_service import get_allocation
from app.services.benchmark_service import get_benchmarks
from app.services.financial_health_service import get_financial_health
from app.services.lookthrough_service import get_look_through
from app.services.notes_service import list_notes
from app.services.performance_service import get_kpis

SYMBOLS = {"BRL": "R$", "USD": "US$", "EUR": "€"}
MAX_CHARS = 6000


def money(value: Decimal | None, currency: str) -> str:
    if value is None:
        return "—"
    sign = "-" if value < 0 else ""
    text = f"{abs(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sign}{SYMBOLS.get(currency, currency)} {text}"


def pct(value: Decimal | None, signed: bool = False) -> str:
    if value is None:
        return "—"
    text = f"{abs(value) * 100:.1f}".replace(".", ",") + "%"
    if signed and value > 0:
        return "+" + text
    if value < 0:
        return "-" + text
    return text


def _num(value: Decimal | None) -> str:
    return "—" if value is None else f"{value:.1f}".replace(".", ",")


def build_chat_context(db: Session, user_id: UUID, *, today: date | None = None) -> str:
    today = today or date.today()
    lines: list[str] = [
        f"# Minha carteira (dados do meu dashboard em {today.strftime('%d/%m/%Y')})",
        "Valores em moedas diferentes nunca são somados. Desempenho de preço sem proventos.",
    ]

    overview = overview_service.get_overview(db, user_id, as_of=today)
    if overview.totals_by_currency:
        lines.append("\n## Patrimônio por moeda")
        for block in overview.totals_by_currency:
            c = block.currency_code
            parts = ", ".join(
                f"{p.label} {money(p.value, c)} ({pct(p.weight)})" for p in block.parts
            )
            lines.append(f"- {c}: total {money(block.total, c)}. {parts}.")
            if block.investments_cost > 0:
                lines.append(
                    f"  Investimentos {money(block.investments_value, c)} sobre "
                    f"{money(block.investments_cost, c)} aplicados; resultado "
                    f"{money(block.result, c)} ({pct(block.result_pct, signed=True)})."
                )

    kpis = get_kpis(db, user_id, today=today)
    for block in kpis.totals_by_currency:
        c = block.currency_code
        lines.append(f"\n## Investimentos em {c}")
        lines.append(
            f"Diversificação: {_num(block.effective_assets)} ativos equivalentes; "
            f"maior posição {block.top_ticker} ({pct(block.top_weight)}); "
            f"proventos recebidos {money(block.dividends, c)}."
        )
        lines.append(
            "| Ativo | Classe | Peso | Valor | Resultado | 1 mês | No ano | 12 meses | Pior queda 12m |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for a in block.assets:
            s = a.stats
            lines.append(
                f"| {a.ticker} | {a.asset_class_label} | {pct(a.weight)} | {money(a.value, c)} | "
                f"{pct(a.return_pct, signed=True)} | {pct(s.return_1m, signed=True)} | "
                f"{pct(s.return_ytd, signed=True)} | {pct(s.return_1y, signed=True)} | "
                f"{pct(s.max_drawdown_1y, signed=True)} |"
            )
        if block.unpriced:
            lines.append(f"Sem cotação (entram pelo custo): {', '.join(block.unpriced)}.")

    allocation = get_allocation(db, user_id, today=today)
    if allocation.currencies:
        lines.append("\n## Alocação por classe (atual × meu alvo)")
        for block in allocation.currencies:
            rows = []
            for r in block.rows:
                target = f" (alvo {pct(r.target_weight)})" if r.target_weight is not None else ""
                rows.append(f"{r.label} {pct(r.current_weight)}{target}")
            suffix = "" if block.has_targets else " — ainda sem alvo definido"
            lines.append(f"- {block.currency_code}: {'; '.join(rows)}{suffix}.")

    benchmarks = get_benchmarks(db, user_id, today=today)
    available = [b for b in benchmarks.comparisons if b.available]
    if available:
        lines.append("\n## Comparação com a referência (mesmos aportes, mesmas datas)")
        for b in available:
            c = b.currency_code
            lines.append(
                f"- {c}: minha carteira {money(b.portfolio_value, c)} ({pct(b.portfolio_return, signed=True)}) × "
                f"{b.benchmark_label} {money(b.benchmark_value, c)} ({pct(b.benchmark_return, signed=True)}) "
                f"sobre {money(b.net_invested, c)} aportados."
            )

    health = get_financial_health(db, user_id, today=today)
    if health.currencies:
        lines.append("\n## Reserva e poupança (meses fechados)")
        for h in health.currencies:
            c = h.currency_code
            parts = [f"reserva {money(h.reserve, c)}"]
            if h.coverage_months is not None:
                prefix = "até " if not h.complete else ""
                parts.append(f"cobre {prefix}{_num(h.coverage_months)} meses de gasto")
            if h.avg_expenses is not None:
                parts.append(f"gasto médio {money(h.avg_expenses, c)}/mês")
            if h.savings_rate is not None:
                parts.append(f"taxa de poupança {pct(h.savings_rate, signed=True)}")
            if not h.complete:
                parts.append("gastos ainda incompletos (lançamentos sem classificação)")
            lines.append(f"- {c}: " + "; ".join(parts) + ".")

    look = get_look_through(db, user_id, today=today)
    for block in look.currencies:
        if not block.companies:
            continue
        top = ", ".join(f"{c.name} {pct(c.weight)}" for c in block.companies[:8])
        lines.append(f"\n## Empresas por trás dos ETFs ({block.currency_code})")
        lines.append(f"{top} (piso: só as maiores posições de cada ETF).")

    agenda = get_agenda(db, user_id, today=today)
    if agenda.maturities:
        lines.append("\n## Vencimentos da renda fixa")
        for m in agenda.maturities:
            rate = f" a {pct(m.annual_rate)} a.a." if m.annual_rate is not None else ""
            lines.append(
                f"- {m.ticker}: vence {m.maturity_date.strftime('%d/%m/%Y')} ({m.days_left} dias), "
                f"{money(m.value or m.cost, m.currency_code)}{rate}."
            )

    shared = list_notes(db, user_id, shared_only=True)[:8]
    if shared:
        lines.append("\n## Minhas anotações (marcadas para conversar com o Claude)")
        for n in shared:
            head = n.title or (n.quote or n.body)[:60]
            tickers = f" [{', '.join(n.tickers)}]" if n.tickers else ""
            text = " ".join(part for part in (f"“{n.quote}”" if n.quote else "", n.body) if part)
            lines.append(f"- {head}{tickers}: {text[:400]}")

    index = insights_service.list_reports()
    if index.latest is not None:
        report = index.latest.report
        lines.append(
            f"\n## Última análise diária ({index.latest.report_date.strftime('%d/%m/%Y')})"
        )
        lines.append(report.headline)
        review = report.portfolio_review
        if review is not None:
            for title, points in (
                ("Está bem", review.good),
                ("Pede atenção", review.attention),
                ("Riscos", review.risks),
                ("Pode melhorar", review.improve),
            ):
                if points:
                    lines.append(f"- {title}: " + "; ".join(p.title for p in points[:4]))

    alerts = [a for a in insights_service.list_alerts(days=3, today=today).alerts if not a.read]
    if alerts:
        lines.append("\n## Alertas não lidos")
        for a in alerts[:5]:
            lines.append(f"- {a.alert.title}")

    text = "\n".join(lines)
    if len(text) > MAX_CHARS:
        text = text[: MAX_CHARS - 40].rsplit("\n", 1)[0] + "\n(… resumo cortado por tamanho)"
    return text
