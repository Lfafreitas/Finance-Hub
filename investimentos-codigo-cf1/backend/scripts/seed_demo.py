"""Carrega uma carteira de DEMONSTRAÇÃO (tudo fictício) num backend vazio.

Serve para experimentar o dashboard e tirar prints sem dado real:

    # backend ligado num banco vazio (ex.: investimentos_demo)
    python scripts/seed_demo.py
    python scripts/seed_demo.py --analises ../claude-analises   # + um "Jornal" de exemplo

Fala só com a API local (http://127.0.0.1:8000), pelos mesmos endpoints da
tela. Só biblioteca padrão.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

API = "http://127.0.0.1:8000"
BRT = timezone(timedelta(hours=-3))
MONTHS = 10


def call(method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        API + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        sys.exit(f"{method} {path}: {exc.code} {exc.read().decode(errors='replace')}")


def month_start(back: int, today: date) -> date:
    index = today.year * 12 + today.month - 1 - back
    return date(index // 12, index % 12 + 1, 1)


def path_price(start: float, end: float, step: int, wiggle: float) -> float:
    """Caminho suave de `start` a `end` com uma oscilação determinística."""
    t = step / MONTHS
    return round(start + (end - start) * t + wiggle * math.sin(step * 1.7), 2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analises", help="pasta claude-analises para gravar um Jornal de exemplo")
    args = parser.parse_args()
    today = date.today()

    if call("GET", "/accounts"):
        sys.exit("Este banco já tem contas: use um banco vazio para a demonstração.")

    broker = call(
        "POST",
        "/institutions",
        {"name": "Corretora Exemplo", "institution_type": "BROKER", "country": "US"},
    )
    bank = call(
        "POST",
        "/institutions",
        {"name": "Banco Exemplo", "institution_type": "BANK", "country": "BR"},
    )

    def account(name, inst, currency, kind):
        body = {
            "name": name,
            "institution_id": inst["id"],
            "currency_code": currency,
            "account_type": kind,
        }
        return call("POST", "/accounts", body)

    usd = account("Corretora Exemplo (US$)", broker, "USD", "BROKERAGE")
    brl = account("Corretora Exemplo (R$)", broker, "BRL", "BROKERAGE")
    checking = account("Conta corrente", bank, "BRL", "CHECKING")
    reserve = account("Reserva", bank, "BRL", "SAVINGS")
    card = account("Cartão de crédito", bank, "BRL", "CREDIT_CARD")

    # ticker, nome, classe, país, moeda, preço inicial, final, oscilação, (vencimento, taxa)
    specs = [
        ("VOO", "Vanguard S&P 500 ETF", "ETF_US", "US", "USD", 520, 610, 9, None),
        ("QQQ", "Invesco QQQ Trust", "ETF_US", "US", "USD", 470, 545, 14, None),
        ("VNQ", "Vanguard Real Estate ETF", "REIT", "US", "USD", 86, 93, 3, None),
        ("BND", "Vanguard Total Bond Market ETF", "ETF_US", "US", "USD", 72, 74, 0.6, None),
        ("CD-EXEMPLO", "CD de exemplo 4% a.a.", "BOND", "US", "USD", 1.0, 1.033, 0, (400, 0.04)),
        ("IVVB11", "iShares S&P 500 (B3)", "ETF_BR", "BR", "BRL", 330, 385, 8, None),
        ("TD-SELIC", "Tesouro Selic de exemplo", "TESOURO_DIRETO", "BR", "BRL", 100, 111, 0, None),
    ]
    assets = {}
    for ticker, name, klass, country, currency, start, end, wiggle, fixed in specs:
        body = {
            "ticker": ticker,
            "name": name,
            "asset_class_code": klass,
            "country": country,
            "currency_code": currency,
        }
        if fixed:
            body["maturity_date"] = (today + timedelta(days=fixed[0])).isoformat()
            body["annual_rate"] = str(fixed[1])
        asset = call("POST", "/assets", body)
        assets[ticker] = (asset, currency, start, end, wiggle)
        for step in range(MONTHS + 1):
            day = month_start(MONTHS - step, today) if step < MONTHS else today - timedelta(days=1)
            price = path_price(start, end, step, wiggle)
            call(
                "PUT",
                f"/assets/{asset['id']}/prices",
                {"price_date": day.isoformat(), "price": str(price)},
            )

    def tx(acc, kind, amount, currency, when, ticker=None, qty=None):
        body = {
            "account_id": acc["id"],
            "transaction_type": kind,
            "gross_amount": str(round(amount, 2)),
            "currency_code": currency,
            "transaction_date": when.isoformat(),
        }
        if ticker:
            asset, _cur, start, end, wiggle = assets[ticker]
            step = MONTHS - (today.year * 12 + today.month - when.year * 12 - when.month)
            price = path_price(start, end, max(step, 0), wiggle)
            qty = qty or round(amount / price, 6)
            body.update(
                asset_id=asset["id"],
                quantity=str(qty),
                unit_price=str(price),
                gross_amount=str(round(qty * price, 2)),
            )
        call("POST", "/transactions", body)

    # Aporte mensal: US$ 400 em dólar e R$ 800 em reais.
    for back in range(MONTHS, 0, -1):
        when = month_start(back, today) + timedelta(days=4)
        tx(usd, "DEPOSIT", 400, "USD", when)
        tx(usd, "BUY", 160, "USD", when, "VOO")
        tx(usd, "BUY", 120, "USD", when, "QQQ")
        tx(usd, "BUY", 50 if back % 2 else 30, "USD", when, "VNQ")
        tx(usd, "BUY", 40, "USD", when, "BND")
        tx(brl, "DEPOSIT", 800, "BRL", when)
        tx(brl, "BUY", 500, "BRL", when, "IVVB11")
        tx(brl, "BUY", 300, "BRL", when, "TD-SELIC")
    tx(usd, "DEPOSIT", 300, "USD", month_start(MONTHS, today) + timedelta(days=6))
    tx(
        usd,
        "BUY",
        300,
        "USD",
        month_start(MONTHS, today) + timedelta(days=6),
        "CD-EXEMPLO",
        qty=300,
    )

    # Controle financeiro: seis meses de renda e gastos, já classificados.
    categories = {c["name"]: c["id"] for c in call("POST", "/cashflow/categories/defaults")}

    def entry(acc, when, amount, description, nature, category=None):
        created = call(
            "POST",
            "/cashflow/entries",
            {
                "account_id": acc["id"],
                "entry_date": when.isoformat(),
                "amount": str(amount),
                "description": description,
                "nature": nature,
            },
        )
        if category:
            call(
                "PUT",
                f"/cashflow/entries/{created['id']}/classification",
                {"nature": nature, "category_id": categories[category]},
            )

    entry(reserve, month_start(7, today), "18000", "Saldo inicial da reserva", "ADJUSTMENT")
    for back in range(6, -1, -1):
        first = month_start(back, today)
        if back == 0 and today.day < 6:
            break
        entry(checking, first + timedelta(days=4), "7500", "Salário", "INCOME", "Salário")
        entry(
            checking, first + timedelta(days=5), "-2100", "Aluguel", "EXPENSE", "Moradia e contas"
        )
        entry(checking, first + timedelta(days=9), "-180", "Energia", "EXPENSE", "Energia")
        entry(
            checking,
            first + timedelta(days=9),
            "-120",
            "Internet",
            "EXPENSE",
            "Telefone e internet",
        )
        entry(
            card, first + timedelta(days=2), str(-640 - back * 35), "Mercado", "EXPENSE", "Mercado"
        )
        entry(
            card,
            first + timedelta(days=12),
            "-210",
            "Restaurante",
            "EXPENSE",
            "Restaurantes e delivery",
        )
        entry(
            card,
            first + timedelta(days=15),
            "-95",
            "Aplicativo de transporte",
            "EXPENSE",
            "Aplicativo",
        )
        entry(
            card,
            first + timedelta(days=18),
            "-55",
            "Streaming",
            "EXPENSE",
            "Assinaturas e software",
        )
        entry(card, first + timedelta(days=20), "-120", "Academia", "EXPENSE", "Academia")
        card_total = 640 + back * 35 + 210 + 95 + 55 + 120
        if first + timedelta(days=24) <= today:
            call(
                "POST",
                "/cashflow/transfers",
                {
                    "from_account_id": checking["id"],
                    "to_account_id": card["id"],
                    "entry_date": (first + timedelta(days=24)).isoformat(),
                    "amount": str(card_total),
                    "description": "Pagamento da fatura",
                },
            )
        call(
            "POST",
            "/cashflow/transfers",
            {
                "from_account_id": checking["id"],
                "to_account_id": reserve["id"],
                "entry_date": (first + timedelta(days=6)).isoformat(),
                "amount": "600",
                "description": "Guardar na reserva",
            },
        )

    call(
        "PUT",
        "/performance/allocation/USD",
        {
            "targets": [
                {"asset_class_code": "ETF_US", "target_weight": "0.7"},
                {"asset_class_code": "REIT", "target_weight": "0.1"},
                {"asset_class_code": "BOND", "target_weight": "0.2"},
            ]
        },
    )

    if args.analises:
        folder = Path(args.analises) / "relatorios"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{today.isoformat()}.json").write_text(
            json.dumps(demo_report(today), ensure_ascii=False, indent=1), encoding="utf-8"
        )
    print("Demonstração carregada. Abra http://localhost:5173")


def demo_report(today: date) -> dict:
    """Um Jornal da carteira de exemplo (texto fictício, links de exemplo)."""
    day = today.isoformat()
    src = [{"title": "Fonte de exemplo", "url": "https://example.com/"}]

    def holding(ticker, signal, reading):
        return {
            "ticker": ticker,
            "signal": signal,
            "reading": reading,
            "metrics": [],
            "sources": src,
        }

    return {
        "schema_version": 3,
        "generated_at": datetime.now(BRT).replace(microsecond=0).isoformat(),
        "headline": "Exemplo: juros longos sobem e tecnologia devolve parte da alta do mês",
        "summary": [
            "Texto de exemplo. Este é o lide da edição: o que mexeu com a carteira desde ontem.",
            "Segundo parágrafo de exemplo, com o contexto de juros, inflação e câmbio.",
            "Terceiro parágrafo de exemplo, sobre o que o mercado espera para a semana.",
        ],
        "holdings": [
            holding("VOO", "NEUTRO", "Leitura de exemplo para o índice amplo americano."),
            holding("QQQ", "ATENCAO", "Leitura de exemplo: preço sobre lucro acima da média."),
            holding("VNQ", "NEUTRO", "Leitura de exemplo: REITs sensíveis a juros."),
            holding("BND", "POSITIVO", "Leitura de exemplo: títulos amortecem quedas."),
        ],
        "news": [
            {
                "ticker": "QQQ",
                "topic": "Tecnologia",
                "title": "Manchete de exemplo sobre tecnologia",
                "source": "Exemplo",
                "url": "https://example.com/noticia",
                "published_at": day,
                "summary": "Resumo de exemplo da notícia.",
            }
        ],
        "research": [],
        "watch": [
            {
                "topic": "Reunião do banco central (exemplo)",
                "why": "Juros mexem com ações de crescimento e com REITs.",
                "date": (today + timedelta(days=2)).isoformat(),
            }
        ],
        "portfolio_review": {
            "overall": "Avaliação de exemplo: carteira diversificada em índices amplos, com renda fixa.",
            "good": [{"title": "Custos baixos", "detail": "Exemplo.", "tickers": ["VOO"]}],
            "attention": [
                {"title": "Sobreposição VOO/QQQ", "detail": "Exemplo.", "tickers": ["QQQ"]}
            ],
            "risks": [{"title": "Juros longos", "detail": "Exemplo.", "tickers": ["VNQ"]}],
            "improve": [],
        },
        "market": [
            {
                "label": "S&P 500",
                "value": "6.700",
                "change": "-0,4%",
                "direction": "DOWN",
                "as_of": day,
                "source": "Exemplo",
            },
            {
                "label": "Treasury 10 anos",
                "value": "4,90%",
                "change": "+0,03 p.p.",
                "direction": "UP",
                "as_of": day,
                "source": "Exemplo",
            },
            {
                "label": "Dólar",
                "value": "R$ 5,40",
                "change": None,
                "direction": "FLAT",
                "as_of": day,
                "source": "Exemplo",
            },
        ],
        "opportunities": [
            {
                "title": "Ideia de exemplo para estudar",
                "thesis": "Tese de exemplo, em poucas frases.",
                "tickers": ["XLK"],
                "relation": "Como a ideia se liga à carteira (exemplo).",
                "why_now": "Por que agora (exemplo).",
                "risks": ["Risco de exemplo"],
                "how_to_follow": "O que acompanhar (exemplo).",
                "sources": src,
            }
        ],
        "etf_holdings": [
            {
                "etf": "VOO",
                "as_of": day,
                "source": "Exemplo",
                "url": None,
                "top": [
                    {"name": "Empresa A", "ticker": "AAA", "weight": 0.07},
                    {"name": "Empresa B", "ticker": "BBB", "weight": 0.06},
                    {"name": "Empresa C", "ticker": "CCC", "weight": 0.05},
                ],
            },
            {
                "etf": "QQQ",
                "as_of": day,
                "source": "Exemplo",
                "url": None,
                "top": [
                    {"name": "Empresa A", "ticker": "AAA", "weight": 0.09},
                    {"name": "Empresa B", "ticker": "BBB", "weight": 0.08},
                    {"name": "Empresa D", "ticker": "DDD", "weight": 0.05},
                ],
            },
        ],
        "disclaimer": "Edição de exemplo, com texto fictício. Não é recomendação de compra ou venda.",
    }


if __name__ == "__main__":
    main()
