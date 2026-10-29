import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makePosition, valuedPosition } from "../test/dashboardFixtures";
import { PositionsTable } from "./PositionsTable";

const position = makePosition({
  quantity: "100.00000000",
  average_cost: "32.00000000",
  total_cost_basis: "3200.0000",
  realized_gain: "0.0000",
  dividends_received: "50.0000",
});

describe("PositionsTable", () => {
  it("renderiza uma linha por posição, formatada na moeda da posição, com o valor exato no title", () => {
    render(<PositionsTable positions={[position]} />);

    expect(screen.getByText("PETR4")).toBeInTheDocument();
    expect(screen.getByText("100")).toHaveAttribute("title", "100.00000000");
    expect(screen.getByText(/R\$\s3\.200,00/)).toHaveAttribute("title", "3200.0000");
    expect(screen.getByText(/R\$\s50,00/)).toHaveAttribute("title", "50.0000");
    expect(screen.getByText(/R\$\s32,00/)).toHaveAttribute("title", "32.00000000");
  });

  it("posição em USD é formatada em dólar, nunca em real", () => {
    render(<PositionsTable positions={[makePosition({ currency_code: "USD", total_cost_basis: "3200.0000" })]} />);

    expect(screen.getByText(/US\$\s3\.200,00/)).toBeInTheDocument();
    expect(screen.queryByText(/^R\$/)).not.toBeInTheDocument();
  });

  it("preço médio com dízima mostra até 8 casas e guarda o valor exato no title", () => {
    render(
      <PositionsTable
        positions={[makePosition({ average_cost: "30.67666666666666666666666667", quantity: "0.12345678" })]}
      />,
    );

    expect(screen.getByText(/R\$\s30,67666667/)).toHaveAttribute("title", "30.67666666666666666666666667");
    expect(screen.getByText("0,12345678")).toBeInTheDocument();
  });

  it("mostra 'Indisponível' na coluna de valor de mercado", () => {
    render(<PositionsTable positions={[position]} />);
    expect(screen.getByText("Indisponível")).toBeInTheDocument();
  });

  it("mostra mensagem de vazio quando não há posições", () => {
    render(<PositionsTable positions={[]} />);
    expect(screen.getByText("Nenhuma posição encontrada.")).toBeInTheDocument();
    expect(screen.queryByTestId("positions-table")).not.toBeInTheDocument();
  });

  it("posição cotada mostra cotação com data, valor de mercado e P&L não realizado", () => {
    render(<PositionsTable positions={[valuedPosition]} />);

    expect(screen.getByText(/R\$\s33,00/)).toHaveAttribute("title", "33.00000000");
    expect(screen.getByText("(29/06/2026)")).toBeInTheDocument();
    expect(screen.getByText(/R\$\s3\.300,00/)).toHaveAttribute("title", "3300.0000");
    expect(screen.getByText(/R\$\s300,00/)).toHaveAttribute("title", "300.0000");
    expect(screen.queryByText("Indisponível")).not.toBeInTheDocument();
  });

  it("posição sem cotação explica o motivo no valor de mercado", () => {
    render(<PositionsTable positions={[position]} />);

    expect(screen.getByText("Indisponível")).toHaveAttribute("title", "sem cotação cadastrada para PETR4");
  });
});
