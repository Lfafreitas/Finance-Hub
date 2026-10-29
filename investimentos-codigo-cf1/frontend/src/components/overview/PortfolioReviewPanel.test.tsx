import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { reportWithReview } from "../../test/kpiFixtures";
import { PortfolioReviewPanel } from "./PortfolioReviewPanel";

describe("PortfolioReviewPanel", () => {
  it("mostra a leitura geral e as quatro listas, com contagem e ativos", () => {
    render(<PortfolioReviewPanel report={reportWithReview()} />);

    expect(screen.getByTestId("review-overall")).toHaveTextContent("Carteira concentrada em tecnologia americana.");
    expect(screen.getByTestId("review-good")).toHaveTextContent("Está bem1Custos baixosSPY, QQQTaxas abaixo de 0,25%.");
    expect(screen.getByTestId("review-attention")).toHaveTextContent("Pede atenção1Concentração");
    expect(screen.getByTestId("review-risks")).toHaveTextContent("Riscos0Nada a destacar.");
    expect(screen.getByTestId("review-improve")).toHaveTextContent("Pode melhorar1Pouca renda");
    expect(screen.getByText(/Análise de 15\/10\/2026/)).toBeInTheDocument();
  });

  it("leva para a análise completa", async () => {
    const onOpen = vi.fn();
    render(<PortfolioReviewPanel report={reportWithReview()} onOpenReport={onOpen} />);

    await userEvent.setup().click(screen.getByRole("button", { name: "Ler a análise completa" }));

    expect(onOpen).toHaveBeenCalled();
  });

  it("relatório antigo sem avaliação e nenhum relatório têm mensagens próprias", () => {
    const old = reportWithReview();
    old.report.portfolio_review = null;
    const { rerender } = render(<PortfolioReviewPanel report={old} />);
    expect(screen.getByTestId("review-empty")).toHaveTextContent("passa a vir na próxima análise diária");

    rerender(<PortfolioReviewPanel report={null} />);
    expect(screen.getByTestId("review-empty")).toHaveTextContent("ainda não chegou");
  });
});
