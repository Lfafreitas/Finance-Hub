import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { readingsByTicker } from "../../lib/kpis";
import { setPrivate } from "../../lib/privacy";
import { kpiBlock, reportWithReview } from "../../test/kpiFixtures";
import { PortfolioKpis } from "./PortfolioKpis";

const text = (el: HTMLElement) => el.textContent?.replace(/ /g, " ");

describe("PortfolioKpis", () => {
  afterEach(() => setPrivate(false));

  it("mostra concentração, diversificação, renda e a composição atual em 12 meses", () => {
    render(<PortfolioKpis block={kpiBlock()} readings={new Map()} />);

    expect(text(screen.getByTestId("kpi-top"))).toContain("QQQ 43,00%");
    expect(text(screen.getByTestId("kpi-top"))).toContain("as 3 maiores somam 79,00%");
    expect(text(screen.getByTestId("kpi-effective"))).toContain("3,4 ativos");
    expect(text(screen.getByTestId("kpi-positive"))).toContain("3 de 6");
    expect(text(screen.getByTestId("kpi-positive"))).toContain("melhor QQQ, pior VNQ");
    expect(text(screen.getByTestId("kpi-income"))).toContain("US$ 1,20");
    expect(text(screen.getByTestId("kpi-income"))).toContain("0,15% sobre o custo");
    expect(text(screen.getByTestId("kpi-basket"))).toContain("+15,20%");
    expect(text(screen.getByTestId("kpi-basket"))).toContain("pior queda -11,10%");
  });

  it("sem um ano de cotações a composição diz o que falta", () => {
    render(<PortfolioKpis block={kpiBlock({ basket: null })} readings={new Map()} />);

    expect(text(screen.getByTestId("kpi-basket"))).toContain("precisa de um ano de cotações");
  });

  it("exposição por classe com valor e peso", () => {
    render(<PortfolioKpis block={kpiBlock()} readings={new Map()} />);

    expect(text(screen.getByTestId("exposure-USD-REIT"))).toContain("REIT");
    expect(text(screen.getByTestId("exposure-USD-REIT"))).toContain("10,00%");
    // A cor segue a classe (REIT é sempre a mesma), não a posição na lista.
    const dot = screen.getByTestId("exposure-USD-REIT").querySelector("span") as HTMLElement;
    expect(dot.style.backgroundColor).toBe("rgb(201, 133, 0)");
  });

  it("ativo sem cotação é nomeado no rodapé", () => {
    render(<PortfolioKpis block={kpiBlock({ unpriced: ["AAXJ"] })} readings={new Map()} />);

    expect(screen.getByText(/Sem cotação, entram pelo custo: AAXJ\./)).toBeInTheDocument();
  });

  it("tabela por ativo com resultado, períodos e faixa de 52 semanas", () => {
    render(<PortfolioKpis block={kpiBlock()} readings={new Map()} />);

    const qqq = screen.getByTestId("kpi-row-QQQ");
    expect(text(qqq)).toContain("+US$ 0,09");
    expect(text(qqq)).toContain("+22,50%");
    expect(text(qqq)).toContain("-1,84% da máxima");
    const vnq = screen.getByTestId("kpi-row-VNQ");
    expect(text(vnq)).toContain("-US$ 4,30");
    // sem 12 meses de histórico: traço, nunca um período menor
    expect(within(vnq).getAllByText("—").length).toBeGreaterThanOrEqual(2);
  });

  it("clicar no ativo mostra os indicadores de mercado do Claude, com fonte e data", async () => {
    const user = userEvent.setup();
    render(<PortfolioKpis block={kpiBlock()} readings={readingsByTicker(reportWithReview())} />);

    await user.click(within(screen.getByTestId("kpi-row-VNQ")).getByRole("button"));

    const detail = screen.getByTestId("kpi-detail-VNQ");
    expect(text(detail)).toContain("Dividend yield");
    expect(text(detail)).toContain("3,85%");
    expect(text(detail)).toContain("P/FFO");
    expect(text(detail)).toContain("17,2x");
    expect(text(detail)).toContain("Nareit, 14/10/2026");
    expect(text(detail)).toContain("Juros longos pesam sobre REITs.");
  });

  it("ativo sem indicadores do Claude diz que ainda não vieram", async () => {
    const user = userEvent.setup();
    render(<PortfolioKpis block={kpiBlock()} readings={new Map()} />);

    await user.click(within(screen.getByTestId("kpi-row-QQQ")).getByRole("button"));

    expect(text(screen.getByTestId("kpi-detail-QQQ"))).toContain("ainda não trouxe indicadores");
  });

  it("no modo privacidade os valores somem e os percentuais ficam", () => {
    setPrivate(true);
    render(<PortfolioKpis block={kpiBlock()} readings={new Map()} />);

    const qqq = text(screen.getByTestId("kpi-row-QQQ"));
    expect(qqq).toContain("US$ •••••");
    expect(qqq).not.toContain("334");
    expect(qqq).toContain("43,00%");
    expect(text(screen.getByTestId("kpi-income"))).toContain("US$ •••••");
  });
});

describe("PortfolioKpis · resultado com proventos", () => {
  it("coluna por ativo e resumo no bloco de proventos", async () => {
    const { asset } = await import("../../test/kpiFixtures");
    const block = kpiBlock({
      dividends: "8.00",
      yield_on_cost: "0.0101",
      total_return_pct: "0.0056",
      assets: [
        asset({ ticker: "VNQ", pnl: "-5.00", return_pct: "-0.0500", dividends: "8.00", total_return_pct: "0.0300" }),
      ],
    });
    render(<PortfolioKpis block={block} readings={new Map()} />);

    expect(text(screen.getByTestId("kpi-row-VNQ"))).toContain("+3,00%");
    expect(text(screen.getByTestId("kpi-income"))).toContain("resultado com proventos +0,56%");
  });

  it("sem cotação: traço, nunca um número inventado", async () => {
    const { asset } = await import("../../test/kpiFixtures");
    const block = kpiBlock({ assets: [asset({ ticker: "AAXJ", value: null, pnl: null, total_return_pct: null })] });
    render(<PortfolioKpis block={block} readings={new Map()} />);

    const cells = screen.getByTestId("kpi-row-AAXJ").querySelectorAll("td");
    expect(cells[4].textContent).toBe("—"); // coluna "Com proventos"
  });
});
