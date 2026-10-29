import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as performanceApi from "../../api/performance";
import type { Allocation } from "../../api/performance";
import { setPrivate } from "../../lib/privacy";
import { AllocationPanel } from "./AllocationPanel";

vi.mock("../../api/performance", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/performance")>()),
  setAllocationTargets: vi.fn(),
}));

const text = (el: HTMLElement) => el.textContent?.replace(/ /g, " ");
const classes = [
  { code: "ETF_US", label: "ETF (Exterior)" },
  { code: "BOND", label: "Bond / Treasury" },
  { code: "REIT", label: "REIT" },
  { code: "STOCK_US", label: "Ação (Exterior)" },
];

function withTargets(): Allocation {
  return {
    currencies: [
      {
        currency_code: "USD",
        total: "1000",
        has_targets: true,
        rows: [
          {
            asset_class: "ETF_US",
            label: "ETF (Exterior)",
            value: "750",
            current_weight: "0.75",
            target_weight: "0.6",
            gap: "0.15",
            value_gap: "-150",
          },
          {
            asset_class: "BOND",
            label: "Bond / Treasury",
            value: "200",
            current_weight: "0.2",
            target_weight: "0.21",
            gap: "-0.01",
            value_gap: "10",
          },
          {
            asset_class: "REIT",
            label: "REIT",
            value: "50",
            current_weight: "0.05",
            target_weight: "0.19",
            gap: "-0.14",
            value_gap: "140",
          },
        ],
      },
    ],
  };
}

function noTargets(): Allocation {
  const a = withTargets();
  a.currencies[0].has_targets = false;
  a.currencies[0].rows = a.currencies[0].rows.map((r) => ({ ...r, target_weight: null, gap: null, value_gap: null }));
  return a;
}

describe("AllocationPanel", () => {
  beforeEach(() => vi.resetAllMocks());
  afterEach(() => setPrivate(false));

  it("mostra peso atual, alvo e a distância em p.p. e em valor", () => {
    render(<AllocationPanel allocation={withTargets()} assetClasses={classes} onChange={() => {}} />);

    expect(text(screen.getByTestId("allocation-USD-ETF_US"))).toContain("75,00% de alvo 60,00%");
    expect(text(screen.getByTestId("allocation-status-USD-ETF_US"))).toBe(
      "+15,0 p.p., acima do alvo (≈ US$ 150,00 acima)",
    );
    expect(text(screen.getByTestId("allocation-status-USD-REIT"))).toBe(
      "-14,0 p.p., abaixo do alvo (≈ US$ 140,00 abaixo)",
    );
    // 1 p.p. de diferença: no alvo
    expect(text(screen.getByTestId("allocation-status-USD-BOND"))).toBe("No alvo");
  });

  it("sem alvo convida a definir", () => {
    render(<AllocationPanel allocation={noTargets()} assetClasses={classes} onChange={() => {}} />);

    expect(screen.getByRole("button", { name: "Definir alvos" })).toBeInTheDocument();
    expect(screen.queryByTestId("allocation-status-USD-ETF_US")).toBeNull();
  });

  it("editar: soma precisa dar 100% e salva em fração", async () => {
    const onChange = vi.fn();
    vi.mocked(performanceApi.setAllocationTargets).mockResolvedValue(withTargets());
    const user = userEvent.setup();
    render(<AllocationPanel allocation={noTargets()} assetClasses={classes} onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: "Definir alvos" }));
    await user.type(screen.getByLabelText("ETF (Exterior)"), "60");
    await user.type(screen.getByLabelText("Bond / Treasury"), "30");
    expect(text(screen.getByTestId("target-sum-USD"))).toContain("90% — precisa dar 100%");
    expect(screen.getByRole("button", { name: "Salvar alvos" })).toBeDisabled();

    await user.selectOptions(screen.getByLabelText("Adicionar classe"), "STOCK_US");
    await user.type(screen.getByLabelText("Ação (Exterior)"), "10");
    await user.click(screen.getByRole("button", { name: "Salvar alvos" }));

    await waitFor(() =>
      expect(performanceApi.setAllocationTargets).toHaveBeenCalledWith("USD", [
        { asset_class_code: "ETF_US", target_weight: "0.6" },
        { asset_class_code: "BOND", target_weight: "0.3" },
        { asset_class_code: "STOCK_US", target_weight: "0.1" },
      ]),
    );
    expect(onChange).toHaveBeenCalled();
  });

  it("apagar alvos manda lista vazia", async () => {
    vi.mocked(performanceApi.setAllocationTargets).mockResolvedValue(noTargets());
    const user = userEvent.setup();
    render(<AllocationPanel allocation={withTargets()} assetClasses={classes} onChange={() => {}} />);

    await user.click(screen.getByRole("button", { name: "Editar alvos" }));
    expect(screen.getByLabelText("ETF (Exterior)")).toHaveValue("60");
    await user.click(screen.getByRole("button", { name: "Apagar alvos" }));

    await waitFor(() => expect(performanceApi.setAllocationTargets).toHaveBeenCalledWith("USD", []));
  });

  it("modo privacidade esconde a distância em valor", () => {
    setPrivate(true);
    render(<AllocationPanel allocation={withTargets()} assetClasses={classes} onChange={() => {}} />);

    expect(text(screen.getByTestId("allocation-status-USD-ETF_US"))).toBe(
      "+15,0 p.p., acima do alvo (≈ US$ ••••• acima)",
    );
  });
});
