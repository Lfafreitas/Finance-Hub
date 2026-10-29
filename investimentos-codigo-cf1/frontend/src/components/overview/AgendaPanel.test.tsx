import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Agenda, DividendsSummary } from "../../api/performance";
import { setPrivate } from "../../lib/privacy";
import { AgendaPanel } from "./AgendaPanel";

const text = (el: HTMLElement) => el.textContent?.replace(/ /g, " ");

function agenda(overrides: Partial<Agenda> = {}): Agenda {
  return {
    as_of: "2026-10-16",
    maturities: [
      {
        ticker: "CD-23NOV",
        name: "CD Exemplo",
        currency_code: "USD",
        maturity_date: "2026-11-30",
        days_left: 38,
        annual_rate: "0.0385",
        cost: "100",
        value: "100.73",
        estimated_at_maturity: "103.85",
      },
      {
        ticker: "CD-VELHO",
        name: "CD antigo",
        currency_code: "USD",
        maturity_date: "2026-10-13",
        days_left: -3,
        annual_rate: null,
        cost: "50",
        value: null,
        estimated_at_maturity: null,
      },
    ],
    missing_maturity: [],
    ...overrides,
  };
}

const dividends: DividendsSummary = {
  totals_by_currency: [
    {
      currency_code: "USD",
      total_received: "3.10",
      total_last_12_months: "3.10",
      average_monthly_last_12_months: "0.26",
    },
  ],
  by_month: [
    { month: "2026-09", currency_code: "USD", amount: "2.00" },
    { month: "2026-06", currency_code: "USD", amount: "1.10" },
    { month: "2024-01", currency_code: "USD", amount: "9.00" },
  ],
  by_asset: [],
};

describe("AgendaPanel", () => {
  afterEach(() => setPrivate(false));

  it("vencimentos com data, taxa, prazo e a estimativa no vencimento", () => {
    render(<AgendaPanel agenda={agenda()} dividends={null} />);

    const row = screen.getByTestId("maturity-CD-23NOV");
    expect(text(row)).toContain("23");
    expect(text(row)).toContain("nov/26");
    expect(text(row)).toContain("3,85% a.a.");
    expect(text(row)).toContain("faltam 38 dias");
    expect(text(row)).toContain("US$ 100,73");
    expect(text(row)).toContain("≈ US$ 103,85 no vencimento");
  });

  it("vencido ainda na carteira avisa para conferir; sem cotação mostra o custo", () => {
    render(<AgendaPanel agenda={agenda()} dividends={null} />);

    const row = screen.getByTestId("maturity-CD-VELHO");
    expect(text(row)).toContain("venceu há 3 dias — confira se o valor já voltou para a conta");
    expect(text(row)).toContain("US$ 50,00");
    expect(text(row)).not.toContain("no vencimento");
  });

  it("renda fixa sem vencimento leva ao cadastro", async () => {
    const onOpenRegistry = vi.fn();
    render(
      <AgendaPanel
        agenda={agenda({ maturities: [], missing_maturity: ["TBILL"] })}
        dividends={null}
        onOpenRegistry={onOpenRegistry}
      />,
    );

    expect(screen.getByTestId("maturities-empty")).toBeInTheDocument();
    expect(text(screen.getByTestId("maturities-missing"))).toContain("Sem vencimento no cadastro: TBILL.");
    await userEvent.setup().click(screen.getByRole("button", { name: "Informar em Cadastros" }));
    expect(onOpenRegistry).toHaveBeenCalled();
  });

  it("proventos: 12 barras do mês, só a janela, total e média", () => {
    render(<AgendaPanel agenda={agenda()} dividends={dividends} />);

    const block = screen.getByTestId("dividends-USD");
    expect(text(block)).toContain("US$ 3,10 em 12 meses");
    expect(text(block)).toContain("Média de US$ 0,26 por mês");
    const bars = Array.from(block.querySelectorAll("[title]")).map((b) =>
      b.getAttribute("title")?.replace(/\u00a0/g, " "),
    );
    expect(bars).toHaveLength(12);
    expect(bars[0]).toContain("nov/25");
    expect(bars[11]).toContain("out/26");
    expect(bars[10]).toContain("set/26: US$ 2,00");
    // jan/24 está fora da janela
    expect(bars.some((b) => b?.includes("9,00"))).toBe(false);
  });

  it("sem provento registrado explica como entram", () => {
    render(<AgendaPanel agenda={agenda()} dividends={{ ...dividends, totals_by_currency: [], by_month: [] }} />);

    expect(screen.getByTestId("dividends-empty")).toBeInTheDocument();
  });

  it("modo privacidade esconde valores e estimativa", () => {
    setPrivate(true);
    render(<AgendaPanel agenda={agenda()} dividends={dividends} />);

    expect(text(screen.getByTestId("maturity-CD-23NOV"))).not.toMatch(/US\$ \d/);
    expect(text(screen.getByTestId("dividends-USD"))).toContain("US$ •••••");
  });
});
