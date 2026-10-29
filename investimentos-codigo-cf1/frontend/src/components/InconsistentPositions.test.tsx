import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { inconsistentPosition, INCONSISTENCY_REASON, makePosition } from "../test/dashboardFixtures";
import { InconsistentPositions } from "./InconsistentPositions";

describe("InconsistentPositions", () => {
  it("não renderiza nada quando não há posição inconsistente", () => {
    const { container } = render(<InconsistentPositions positions={[]} accounts={[]} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("mostra o motivo por extenso e nenhum valor monetário", () => {
    // Mesmo que o backend mandasse valores, o painel não tem coluna para eles.
    const comValores = makePosition({
      ...inconsistentPosition,
      total_cost_basis: "9999.0000",
      average_cost: "55.55000000",
      realized_gain: "123.0000",
    });

    render(<InconsistentPositions positions={[comValores]} accounts={[]} />);

    const panel = screen.getByTestId("inconsistent-positions");
    expect(panel).toHaveTextContent(INCONSISTENCY_REASON);
    expect(panel).not.toHaveTextContent("9999");
    expect(panel).not.toHaveTextContent("55.55");
    expect(panel).not.toHaveTextContent("123.0000");
    expect(panel).not.toHaveTextContent("R$");
  });

  it("situação reflete is_closed (quantidade), e a conta cai no id quando não há nome", () => {
    render(
      <InconsistentPositions
        positions={[inconsistentPosition, makePosition({ ...inconsistentPosition, asset_id: "x", is_closed: true })]}
        accounts={[]}
      />,
    );

    expect(screen.getByText("Aberta")).toBeInTheDocument();
    expect(screen.getByText("Zerada")).toBeInTheDocument();
    expect(screen.getAllByText("acc-mix")).toHaveLength(2);
    expect(screen.getByTestId("inconsistent-positions")).toHaveTextContent("(2)");
  });
});
