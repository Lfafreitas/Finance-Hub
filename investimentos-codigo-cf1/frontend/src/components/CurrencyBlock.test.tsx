import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeBlock, MARKET_REASON, usdBlock, usdPosition, valuedBlock, valuedPosition } from "../test/dashboardFixtures";
import { CurrencyBlock } from "./CurrencyBlock";

describe("CurrencyBlock", () => {
  it("todos os cards com valor são formatados na moeda do bloco", () => {
    render(<CurrencyBlock block={usdBlock} positions={[usdPosition]} />);

    const block = screen.getByTestId("currency-block-USD");
    expect(block).toHaveTextContent(/US\$\s7\.777,00/); // custo
    expect(block).toHaveTextContent(/-US\$\s888,00/); // resultado realizado
    expect(block).toHaveTextContent(/US\$\s99,00/); // proventos
    expect(block).toHaveTextContent(/US\$\s6\.666,00/); // aportes
    expect(block).not.toHaveTextContent("R$");
  });

  it("resultado negativo usa o tom negativo; os de mercado seguem indisponíveis com o motivo", () => {
    render(<CurrencyBlock block={usdBlock} positions={[usdPosition]} />);

    expect(screen.getByText(/-US\$\s888,00/)).toHaveClass("text-red-400");
    expect(screen.getAllByTestId("indicator-unavailable")).toHaveLength(3);
    expect(screen.getAllByText("sem cotação utilizável para: AAPL")).toHaveLength(3);
  });

  it("mostra só as posições que recebeu", () => {
    render(<CurrencyBlock block={usdBlock} positions={[usdPosition]} />);

    const table = screen.getByTestId("positions-table");
    expect(within(table).getByText("AAPL")).toBeInTheDocument();
    expect(within(table).getAllByRole("row")).toHaveLength(2);
    expect(screen.queryByTestId("cash-only-note")).not.toBeInTheDocument();
  });

  it("com todas as posições cotadas, mostra patrimônio, P&L e rentabilidade em percentual", () => {
    render(<CurrencyBlock block={valuedBlock} positions={[valuedPosition]} />);

    const block = screen.getByTestId("currency-block-BRL");
    expect(block).toHaveTextContent(/R\$\s3\.300,00/); // patrimônio a mercado
    expect(block).toHaveTextContent(/R\$\s300,00/); // P&L não realizado
    expect(screen.getByText("10,00%")).toHaveClass("text-emerald-400"); // fração 0.1, não "R$ 0,10"
    expect(screen.queryByTestId("indicator-unavailable")).not.toBeInTheDocument();
    expect(screen.getByTestId("market-data-as-of")).toHaveTextContent("29/06/2026");
  });

  it("P&L e rentabilidade negativos usam o tom negativo", () => {
    const losing = makeBlock({
      market_value: "2700.00",
      unrealized_pnl: "-300.00",
      current_return: "-0.1",
      market_data_as_of: "2026-06-29",
      market_data_unavailable_reason: null,
    });

    render(<CurrencyBlock block={losing} positions={[valuedPosition]} />);

    expect(screen.getByText(/-R\$\s300,00/)).toHaveClass("text-red-400");
    expect(screen.getByText("-10,00%")).toHaveClass("text-red-400");
  });

  it("sem cotação completa, os três cards ficam indisponíveis com o motivo do bloco e sem nota de data", () => {
    render(<CurrencyBlock block={makeBlock()} positions={[]} />);

    expect(screen.getAllByTestId("indicator-unavailable")).toHaveLength(3);
    expect(screen.getAllByText(MARKET_REASON)).toHaveLength(3);
    expect(screen.queryByTestId("market-data-as-of")).not.toBeInTheDocument();
  });

  it("valorado mas sem custo: rentabilidade indisponível com motivo próprio", () => {
    const noCost = makeBlock({
      total_cost_basis: "0",
      market_value: "50.00",
      unrealized_pnl: "50.00",
      current_return: null,
      market_data_as_of: "2026-06-29",
      market_data_unavailable_reason: null,
    });

    render(<CurrencyBlock block={noCost} positions={[valuedPosition]} />);

    expect(screen.getAllByTestId("indicator-unavailable")).toHaveLength(1);
    expect(screen.getByText("Sem custo de aquisição em posições abertas.")).toBeInTheDocument();
  });
});
