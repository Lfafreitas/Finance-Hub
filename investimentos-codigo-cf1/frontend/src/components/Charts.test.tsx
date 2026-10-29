import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { ConcentrationRead } from "../api/analytics";
import type { AllocationSlice, ContributionPoint } from "../api/types";
import { AllocationChart } from "./AllocationChart";
import { BarList } from "./charts/BarList";
import { ShareBar } from "./charts/ShareBar";
import { ContributionChart } from "./ContributionChart";

const text = (el: Element) => el.textContent?.replace(/ /g, " ") ?? "";

const allocation: AllocationSlice[] = [
  { asset_id: "1", asset_ticker: "PETR4", asset_name: "Petrobras", cost_basis: "100.00", percentage: "25.00" },
  { asset_id: "2", asset_ticker: "VALE3", asset_name: "Vale", cost_basis: "300.00", percentage: "75.00" },
];

const concentration: ConcentrationRead = {
  basis: "MARKET",
  total: "551.70",
  by_asset: [
    { key: "a-qqq", label: "QQQ", value: "313.04", weight: "0.5674" },
    { key: "a-spy", label: "SPY", value: "177.72", weight: "0.3221" },
    { key: "a-cd", label: "CD-EXEMPLO", value: "60.94", weight: "0.1105" },
  ],
  by_class: [],
  by_account: [],
  by_group: [
    { key: "VARIABLE", label: "Renda variável", value: "490.76", weight: "0.8895" },
    { key: "FIXED", label: "Renda fixa", value: "60.94", weight: "0.1105" },
  ],
  top3_weight: "1.0000",
  flags: [],
};

describe("AllocationChart", () => {
  it("com as análises: barras por ativo pelo valor de mercado, com porcentagem formatada", () => {
    render(<AllocationChart currency="USD" concentration={concentration} allocation={allocation} />);

    expect(screen.getByTestId("allocation-basis")).toHaveTextContent("Pelo valor de mercado.");
    const rows = Array.from(screen.getByTestId("allocation-assets").querySelectorAll("li")).map(text);
    expect(rows).toEqual(["QQQUS$ 313,0456,74%", "SPYUS$ 177,7232,21%", "CD-EXEMPLOUS$ 60,9411,05%"]);
  });

  it("alterna para renda fixa × variável numa barra de 100%", async () => {
    const user = userEvent.setup();
    render(<AllocationChart currency="USD" concentration={concentration} allocation={allocation} />);

    await user.click(screen.getByRole("button", { name: "Renda fixa × variável" }));

    const groups = screen.getByTestId("allocation-groups");
    expect(text(within(groups).getByTestId("allocation-groups-VARIABLE"))).toBe("Renda variávelUS$ 490,7688,95%");
    expect(text(within(groups).getByTestId("allocation-groups-FIXED"))).toBe("Renda fixaUS$ 60,9411,05%");
    expect(screen.queryByTestId("allocation-assets")).not.toBeInTheDocument();
  });

  it("sem as análises, usa o custo do resumo e diz isso", () => {
    render(<AllocationChart currency="BRL" concentration={null} allocation={allocation} />);

    expect(screen.getByTestId("allocation-basis")).toHaveTextContent("Pelo valor aplicado (custo)");
    expect(text(screen.getByTestId("allocation-assets"))).toContain("PETR4R$ 100,0025,00%");
    expect(screen.queryByRole("button", { name: "Renda fixa × variável" })).not.toBeInTheDocument();
  });

  it("base de custo nas análises também é dita", () => {
    render(<AllocationChart currency="USD" concentration={{ ...concentration, basis: "COST" }} allocation={[]} />);

    expect(screen.getByTestId("allocation-basis")).toHaveTextContent("falta cotação");
  });

  it("mostra estado vazio quando não há alocação", () => {
    render(<AllocationChart currency="BRL" concentration={null} allocation={[]} />);
    expect(screen.getByText("Sem posições para distribuir.")).toBeInTheDocument();
  });
});

describe("ContributionChart", () => {
  const points: ContributionPoint[] = [
    { date: "2026-01-01", cumulative_net_contribution: "1000.00" },
    { date: "2026-02-01", cumulative_net_contribution: "1500.00" },
  ];

  it("explica que é dinheiro colocado, não patrimônio, e mostra o total de hoje", () => {
    render(<ContributionChart currency="BRL" points={points} />);
    expect(screen.getByText(/não é patrimônio/)).toBeInTheDocument();
    expect(text(screen.getByTestId("contribution-last"))).toBe("R$ 1.500,00");
  });

  it("mostra estado vazio quando não há pontos", () => {
    render(<ContributionChart currency="BRL" points={[]} />);
    expect(screen.getByText("Sem movimentações de aporte/retirada ainda.")).toBeInTheDocument();
  });
});

describe("ShareBar e BarList", () => {
  it("fatias com legenda de valor e porcentagem; nada quando vazio", () => {
    const { container, rerender } = render(
      <ShareBar
        label="x"
        currency="BRL"
        testId="share"
        items={[{ key: "RESERVE", label: "Reserva", value: "13200", weight: "1", color: "#199e70" }]}
      />,
    );
    expect(text(screen.getByTestId("share-RESERVE"))).toBe("ReservaR$ 13.200,00100,00%");
    expect(screen.getByRole("img", { name: "x" })).toBeInTheDocument();

    rerender(<ShareBar label="x" currency="BRL" testId="share" items={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("a maior barra ocupa a largura toda e as outras são proporcionais", () => {
    render(
      <BarList
        currency="BRL"
        testId="bars"
        items={[
          { key: "a", label: "A", value: "200" },
          { key: "b", label: "B", value: "50" },
        ]}
      />,
    );
    const width = (key: string) =>
      (screen.getByTestId(`bars-${key}`).querySelector("div[style]") as HTMLElement).style.width;
    expect(width("a")).toBe("100%");
    expect(width("b")).toBe("25%");
  });
});
