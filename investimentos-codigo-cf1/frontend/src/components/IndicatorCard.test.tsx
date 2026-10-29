import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { IndicatorCard } from "./IndicatorCard";

describe("IndicatorCard", () => {
  it("renderiza o valor formatado quando presente", () => {
    render(<IndicatorCard label="Valor investido" value="1000.00" currencyCode="BRL" />);
    expect(screen.getByText("Valor investido")).toBeInTheDocument();
    expect(screen.getByText(/R\$\s1\.000,00/)).toBeInTheDocument();
  });

  it("formata na moeda recebida, não em BRL fixo", () => {
    render(<IndicatorCard label="Valor investido" value="1000.00" currencyCode="USD" />);
    expect(screen.getByText(/US\$\s1\.000,00/)).toBeInTheDocument();
    expect(screen.queryByText(/^R\$/)).not.toBeInTheDocument();
  });

  it("mostra 'Indisponível' e o motivo quando o valor é null", () => {
    render(
      <IndicatorCard
        label="Patrimônio a mercado"
        value={null}
        currencyCode="BRL"
        unavailableReason="Sem motor de cotações (Fase 12)"
      />,
    );
    expect(screen.getByTestId("indicator-unavailable")).toHaveTextContent("Indisponível");
    expect(screen.getByText("Sem motor de cotações (Fase 12)")).toBeInTheDocument();
  });

  it("nunca renderiza um número quando o valor é null", () => {
    render(<IndicatorCard label="P&L não realizado" value={null} currencyCode="BRL" />);
    expect(screen.queryByText(/R\$/)).not.toBeInTheDocument();
  });
});
