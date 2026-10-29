import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../api/analytics";
import * as client from "../api/client";
import * as insights from "../api/insights";
import { ApiError } from "../api/client";
import { makeAnalytics, makeAnalyticsBlock, refreshFixture } from "../test/analyticsFixtures";
import { Analyses } from "./Analyses";

vi.mock("../api/analytics");
vi.mock("../api/insights");
vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  getPortfolios: vi.fn(),
}));

const text = (el: Element) => el.textContent?.replace(/ /g, " ") ?? "";
const fresh = () => new Date().toISOString();
const old = () => new Date(Date.now() - 60 * 60 * 1000).toISOString();

describe("Analyses — carga e atualização de cotações", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(client.getPortfolios).mockResolvedValue([{ id: "p-1", name: "Exterior" }]);
    vi.mocked(api.getPortfolioAnalytics).mockResolvedValue(makeAnalytics({ quotes_refreshed_at: fresh() }));
    vi.mocked(api.refreshQuotes).mockResolvedValue(refreshFixture);
    vi.mocked(insights.writeSnapshot).mockResolvedValue({ written_at: "x", positions: 4 });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("com cotação recente, só carrega: não busca na fonte", async () => {
    render(<Analyses />);

    await screen.findByTestId("scenarios-USD");
    expect(api.getPortfolioAnalytics).toHaveBeenCalledWith(null, null);
    expect(api.refreshQuotes).not.toHaveBeenCalled();
    expect(screen.getByTestId("quotes-refreshed")).toHaveTextContent("atualiza sozinho a cada 15 min");
  });

  it("com cotação velha, busca na fonte e carrega de novo", async () => {
    vi.mocked(api.getPortfolioAnalytics).mockResolvedValueOnce(makeAnalytics({ quotes_refreshed_at: old() }));

    render(<Analyses />);

    await waitFor(() => expect(api.refreshQuotes).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getPortfolioAnalytics).toHaveBeenCalledTimes(2));
  });

  it("nunca buscada também dispara a busca", async () => {
    vi.mocked(api.getPortfolioAnalytics).mockResolvedValueOnce(makeAnalytics({ quotes_refreshed_at: null }));

    render(<Analyses />);

    await waitFor(() => expect(api.refreshQuotes).toHaveBeenCalledTimes(1));
  });

  it("o botão busca na hora e recarrega os números", async () => {
    const user = userEvent.setup();
    render(<Analyses />);
    await screen.findByTestId("scenarios-USD");

    await user.click(screen.getByRole("button", { name: "Atualizar cotações agora" }));

    await waitFor(() => expect(api.getPortfolioAnalytics).toHaveBeenCalledTimes(2));
    expect(api.refreshQuotes).toHaveBeenCalledTimes(1);
  });

  it("busca sozinho a cada 15 minutos enquanto a tela está aberta", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<Analyses />);
    await screen.findByTestId("scenarios-USD");
    expect(api.refreshQuotes).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(15 * 60 * 1000);
    });

    await waitFor(() => expect(api.refreshQuotes).toHaveBeenCalledTimes(1));
  });

  it("depois de buscar cotações, atualiza o retrato que a análise do Claude lê", async () => {
    const user = userEvent.setup();
    vi.mocked(insights.writeSnapshot).mockResolvedValue({ written_at: "x", positions: 4 });
    render(<Analyses />);
    await screen.findByTestId("scenarios-USD");
    expect(insights.writeSnapshot).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Atualizar cotações agora" }));

    await waitFor(() => expect(insights.writeSnapshot).toHaveBeenCalledTimes(1));
  });

  it("ativos sem cotação automática são listados com o motivo", async () => {
    const user = userEvent.setup();
    render(<Analyses />);
    await screen.findByTestId("scenarios-USD");

    await user.click(screen.getByRole("button", { name: "Atualizar cotações agora" }));

    const problems = await screen.findByTestId("refresh-problems");
    expect(problems).toHaveTextContent("1 ativo sem cotação automática");
    expect(problems).toHaveTextContent("CDUS: sem fonte automática");
    expect(problems).not.toHaveTextContent("SPY");
  });

  it("falha na fonte não derruba a tela: avisa e mostra os números gravados", async () => {
    const user = userEvent.setup();
    vi.mocked(api.refreshQuotes).mockRejectedValue(new Error("rede"));
    render(<Analyses />);
    await screen.findByTestId("scenarios-USD");

    await user.click(screen.getByRole("button", { name: "Atualizar cotações agora" }));

    expect(await screen.findByTestId("refresh-error")).toHaveTextContent("Os números usam a última cotação gravada");
    expect(screen.getByTestId("scenarios-USD")).toBeInTheDocument();
  });

  it("trocar carteira ou data final recarrega com os novos parâmetros", async () => {
    const user = userEvent.setup();
    render(<Analyses />);
    await screen.findByTestId("scenarios-USD");

    await user.selectOptions(screen.getByLabelText("Selecionar carteira"), "p-1");
    await waitFor(() => expect(api.getPortfolioAnalytics).toHaveBeenLastCalledWith("p-1", null));
    await user.type(screen.getByLabelText("Cenários até"), "2027-06-30");

    await waitFor(() => expect(api.getPortfolioAnalytics).toHaveBeenLastCalledWith("p-1", "2027-06-30"));
  });

  it("erro ao carregar aparece com o motivo", async () => {
    vi.mocked(api.getPortfolioAnalytics).mockRejectedValue(new ApiError(404, "Not Found", '{"detail":"carteira não encontrada"}'));

    render(<Analyses />);

    expect(await screen.findByRole("alert")).toHaveTextContent("carteira não encontrada");
  });

  it("sem posição, diz isso", async () => {
    vi.mocked(api.getPortfolioAnalytics).mockResolvedValue(makeAnalytics({ blocks: [] }));

    render(<Analyses />);

    expect(await screen.findByTestId("analyses-empty")).toBeInTheDocument();
  });
});

describe("Analyses — conteúdo", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(client.getPortfolios).mockResolvedValue([]);
    vi.mocked(api.getPortfolioAnalytics).mockResolvedValue(makeAnalytics());
    vi.mocked(api.refreshQuotes).mockResolvedValue(refreshFixture);
    vi.mocked(insights.writeSnapshot).mockResolvedValue({ written_at: "x", positions: 4 });
  });

  it("cenários mostram variação e valor exatamente como o backend calculou", async () => {
    render(<Analyses />);

    await screen.findByTestId("scenarios-USD");
    expect(text(screen.getByTestId("scenario-Pessimista"))).toContain("-9,40%");
    expect(text(screen.getByTestId("scenario-Pessimista"))).toContain("US$ 322,55");
    expect(text(screen.getByTestId("scenario-Realista"))).toContain("1,20%");
    expect(text(screen.getByTestId("scenario-Realista"))).toContain("US$ 360,28");
    expect(text(screen.getByTestId("scenario-Otimista"))).toContain("13,30%");
    expect(text(screen.getByTestId("scenario-Otimista"))).toContain("US$ 403,36");
    expect(screen.getByTestId("probability-USD")).toHaveTextContent("45,00%");
    expect(screen.getByTestId("scenarios-USD")).toHaveTextContent("Cenários até 31/12/2026 · 84 dias");
  });

  it("aportes no ritmo médio aparecem junto dos cenários, sem somar nada na tela", async () => {
    render(<Analyses />);

    expect(text(await screen.findByTestId("scenarios-contributions-USD"))).toContain("US$ 234,16");
  });

  it("em dezembro (nada mais a aportar no ano) a frase de aportes não aparece", async () => {
    const block = makeAnalyticsBlock();
    const december = {
      ...block.contributions!,
      remaining_months: 0,
      projections: block.contributions!.projections.map((p) => ({ ...p, remaining_total: "0.00" })),
    };
    vi.mocked(api.getPortfolioAnalytics).mockResolvedValue(makeAnalytics({ blocks: [makeAnalyticsBlock({ contributions: december })] }));

    render(<Analyses />);

    await screen.findByTestId("scenarios-USD");
    expect(screen.queryByTestId("scenarios-contributions-USD")).not.toBeInTheDocument();
  });

  it("premissas dizem de onde veio cada volatilidade, e o que ficou de fora", async () => {
    render(<Analyses />);

    const table = await screen.findByTestId("assumptions-USD");
    expect(table).toHaveTextContent("histórico (250 dias)");
    expect(table).toHaveTextContent("padrão da classe");
    expect(screen.getByTestId("excluded-USD")).toHaveTextContent("CDUS: renda fixa");
  });

  it("sem cenário, mostra o motivo do backend", async () => {
    vi.mocked(api.getPortfolioAnalytics).mockResolvedValue(
      makeAnalytics({
        blocks: [makeAnalyticsBlock({ scenarios: null, scenarios_unavailable_reason: "a data final dos cenários precisa ser depois de hoje" })],
      }),
    );

    render(<Analyses />);

    expect(await screen.findByTestId("scenarios-USD")).toHaveTextContent("precisa ser depois de hoje");
  });

  it("ritmo de aporte: meses, total e as três projeções", async () => {
    render(<Analyses />);

    const panel = await screen.findByTestId("contributions-USD");
    expect(text(panel)).toContain("US$ 351,24 aportados no ano · faltam 2 meses");
    expect(text(panel)).toContain("ago/2026");
    const rows = Array.from(screen.getByTestId("projections-USD").querySelectorAll("tbody tr")).map(text);
    expect(rows).toEqual([
      "Média do anoUS$ 117,08+US$ 234,16US$ 585,40",
      "Últimos 3 mesesUS$ 117,08+US$ 234,16US$ 585,40",
      "Este mêsUS$ 200,59+US$ 401,18US$ 752,42",
    ]);
  });

  it("sem aporte no ano, explica o que conta como aporte", async () => {
    vi.mocked(api.getPortfolioAnalytics).mockResolvedValue(makeAnalytics({ blocks: [makeAnalyticsBlock({ contributions: null })] }));

    render(<Analyses />);

    expect(await screen.findByTestId("contributions-USD")).toHaveTextContent("Aporte é depósito");
    expect(screen.queryByTestId("scenarios-contributions-USD")).not.toBeInTheDocument();
  });

  it("concentração: base, sinais e pesos por ativo, classe e conta", async () => {
    render(<Analyses />);

    await screen.findByTestId("concentration-USD");
    expect(screen.getByTestId("basis-USD")).toHaveTextContent("Pesos pelo valor de mercado");
    expect(screen.getByTestId("basis-USD")).toHaveTextContent("Os 3 maiores somam 97,09%");
    expect(screen.getByTestId("flags-USD")).toHaveTextContent("QQQ sozinho é mais de 40%");
    const assets = Array.from(screen.getByTestId("by-asset-USD").querySelectorAll("li")).map(text);
    expect(assets[0]).toBe("QQQ47,40%");
    expect(screen.getByTestId("by-class-USD")).toHaveTextContent("REIT2,91%");
    expect(screen.getByTestId("by-account-USD")).toHaveTextContent("Inter US100,00%");
  });

  it("pesos pelo custo avisam que falta cotação", async () => {
    const block = makeAnalyticsBlock();
    vi.mocked(api.getPortfolioAnalytics).mockResolvedValue(
      makeAnalytics({ blocks: [makeAnalyticsBlock({ concentration: { ...block.concentration!, basis: "COST" } })] }),
    );

    render(<Analyses />);

    expect(await screen.findByTestId("basis-USD")).toHaveTextContent("Pesos pelo custo");
  });

  it("alertas aparecem; sem alerta, não há painel", async () => {
    vi.mocked(api.getPortfolioAnalytics).mockResolvedValue(
      makeAnalytics({ blocks: [makeAnalyticsBlock({ alerts: ["cotação de VNQ é de 08/09/2026"] })] }),
    );
    const { unmount } = render(<Analyses />);
    expect(await screen.findByTestId("alerts-USD")).toHaveTextContent("cotação de VNQ é de 08/09/2026");
    unmount();

    vi.mocked(api.getPortfolioAnalytics).mockResolvedValue(makeAnalytics());
    render(<Analyses />);
    await screen.findByTestId("scenarios-USD");
    expect(screen.queryByTestId("alerts-USD")).not.toBeInTheDocument();
  });

  it("uma aba por moeda; cada aba mostra só a sua moeda", async () => {
    const user = userEvent.setup();
    vi.mocked(api.getPortfolioAnalytics).mockResolvedValue(
      makeAnalytics({
        blocks: [
          makeAnalyticsBlock({ currency_code: "BRL", scenarios: { ...makeAnalyticsBlock().scenarios!, value_today: "1000.00" } }),
          makeAnalyticsBlock(),
        ],
      }),
    );
    render(<Analyses />);

    await screen.findByTestId("scenarios-BRL");
    expect(screen.queryByTestId("scenarios-USD")).not.toBeInTheDocument();
    expect(text(screen.getByTestId("scenarios-BRL"))).toContain("R$ 1.000,00");
    await user.click(within(screen.getByRole("tablist", { name: "Moeda" })).getByRole("tab", { name: "USD" }));

    expect(screen.getByTestId("scenarios-USD")).toBeInTheDocument();
    expect(screen.queryByTestId("scenarios-BRL")).not.toBeInTheDocument();
  });

  it("deixa claro que é leitura de números, não recomendação", async () => {
    render(<Analyses />);

    expect(await screen.findByText(/não recomendação de compra ou venda/)).toBeInTheDocument();
  });
});
