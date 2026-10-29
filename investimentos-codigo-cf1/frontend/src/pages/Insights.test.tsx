import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import type { InsightIndex, InsightReport } from "../api/insights";
import * as api from "../api/insights";
import * as notesApi from "../api/notes";
import { Insights } from "./Insights";

vi.mock("../api/insights");
vi.mock("../api/notes");

function report(overrides: Partial<InsightReport> = {}): InsightReport {
  return {
    schema_version: 1,
    generated_at: "2026-10-09T11:00:00Z",
    headline: "Juros americanos seguem pressionando tecnologia",
    summary: ["O Fed sinalizou mais uma alta.", "O S&P 500 está perto da média histórica de P/L."],
    holdings: [
      {
        ticker: "QQQ",
        signal: "ATENCAO",
        reading: "P/L acima da mediana histórica.",
        metrics: [{ label: "P/L", value: "29,4", context: "mediana histórica 23,2" }],
        sources: [{ title: "GuruFocus", url: "https://www.gurufocus.com/x" }],
      },
      { ticker: "SPY", signal: "NEUTRO", reading: "P/L perto da média.", metrics: [], sources: [] },
      { ticker: "AAXJ", signal: "POSITIVO", reading: "Lucros de chips em alta.", metrics: [], sources: [] },
    ],
    news: [
      {
        ticker: "SPY",
        topic: "Mercado americano",
        title: "Índices recuam de recordes",
        source: "Yahoo Finance",
        url: "https://finance.yahoo.com/a",
        published_at: "2026-10-07",
        summary: "Juros longos subiram.",
      },
      {
        ticker: "QQQ",
        topic: "Tecnologia",
        title: "Big techs puxam o Nasdaq",
        source: "CNBC",
        url: "https://www.cnbc.com/b",
        published_at: "2026-10-08",
        summary: "IA segue no centro.",
      },
      {
        ticker: null,
        topic: "Juros",
        title: "Treasury de 10 anos a 5,3%",
        source: "Bloomberg",
        url: "javascript:alert(1)",
        published_at: null,
        summary: "Nível mais alto em anos.",
      },
    ],
    research: [
      {
        house: "FactSet",
        title: "Earnings Insight",
        url: "https://www.factset.com/earningsinsight",
        published_at: "2026-10-02",
        summary: "P/L projetado do S&P 500 em 19,0.",
        relevance: "SPY: preço perto da média de 10 anos.",
      },
    ],
    watch: [{ topic: "Reunião do Fed", why: "Juros mexem em crescimento.", date: "2026-10-28" }],
    disclaimer: "Leitura de dados públicos, não recomendação de compra ou venda.",
    ...overrides,
  };
}

function index(overrides: Partial<InsightIndex> = {}): InsightIndex {
  return {
    latest: { report_date: "2026-10-09", report: report() },
    history: [
      { report_date: "2026-10-09", headline: "Juros americanos seguem pressionando tecnologia" },
      { report_date: "2026-10-08", headline: "Ontem" },
    ],
    invalid_files: [],
    snapshot_written_at: "2026-10-09T10:00:00Z",
    ...overrides,
  };
}

describe("Insights", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.getInsights).mockResolvedValue(index());
    vi.mocked(api.getAlerts).mockResolvedValue({ alerts: [], unread_count: 0, invalid_files: [] });
    vi.mocked(api.getChatContext).mockReturnValue(new Promise(() => {}));
    vi.mocked(api.writeSnapshot).mockResolvedValue({ written_at: "x", positions: 4 });
    vi.mocked(api.getLookThrough).mockResolvedValue({ report_date: null, currencies: [] });
    vi.mocked(notesApi.getNotes).mockResolvedValue([]);
    vi.mocked(notesApi.getSources).mockResolvedValue([]);
  });

  it("ao abrir, atualiza o retrato da carteira e mostra a análise mais recente", async () => {
    render(<Insights />);

    expect(await screen.findByTestId("headline")).toHaveTextContent("Juros americanos seguem pressionando tecnologia");
    expect(api.writeSnapshot).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("report-date")).toHaveTextContent("Análise de 09/10/2026");
    expect(within(screen.getByTestId("summary")).getAllByText(/./)).toHaveLength(2);
  });

  it("cada ativo com o sinal, a leitura, as métricas e as fontes", async () => {
    render(<Insights />);

    const qqq = await screen.findByTestId("holding-QQQ");
    expect(qqq).toHaveTextContent("Atenção");
    expect(qqq).toHaveTextContent("P/L acima da mediana histórica.");
    expect(qqq).toHaveTextContent("29,4");
    expect(qqq).toHaveTextContent("mediana histórica 23,2");
    expect(within(qqq).getByRole("link", { name: "GuruFocus" })).toHaveAttribute("href", "https://www.gurufocus.com/x");
    expect(screen.getByTestId("holding-SPY")).toHaveTextContent("Neutro");
    expect(screen.getByTestId("holding-AAXJ")).toHaveTextContent("Leitura positiva");
  });

  it("links abrem em outra aba sem dar acesso à página", async () => {
    render(<Insights />);

    const link = await screen.findByRole("link", { name: "Índices recuam de recordes" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("link que não é http(s) vira texto, nunca link", async () => {
    render(<Insights />);

    await screen.findByTestId("news");
    expect(screen.getByText("Treasury de 10 anos a 5,3%").tagName).toBe("SPAN");
    expect(screen.queryByRole("link", { name: "Treasury de 10 anos a 5,3%" })).not.toBeInTheDocument();
  });

  it("notícias podem ser filtradas por ativo", async () => {
    const user = userEvent.setup();
    render(<Insights />);
    await screen.findByTestId("news");
    expect(screen.getAllByTestId("news-item")).toHaveLength(3);

    await user.click(
      within(screen.getByRole("group", { name: "Filtrar notícias" })).getByRole("button", { name: "QQQ" }),
    );

    expect(screen.getAllByTestId("news-item")).toHaveLength(1);
    expect(screen.getByTestId("news")).toHaveTextContent("Big techs puxam o Nasdaq");
    await user.click(screen.getByRole("button", { name: "Todas" }));
    expect(screen.getAllByTestId("news-item")).toHaveLength(3);
  });

  it("relatórios de grandes casas: casa, data, resumo e relevância para a carteira", async () => {
    render(<Insights />);

    const research = await screen.findByTestId("research");
    expect(research).toHaveTextContent("FactSet · 02/10/2026");
    expect(research).toHaveTextContent("P/L projetado do S&P 500 em 19,0.");
    expect(research).toHaveTextContent("Para a sua carteira: SPY: preço perto da média de 10 anos.");
    expect(research).toHaveTextContent("o texto completo fica na fonte");
  });

  it("o que acompanhar, com a data", async () => {
    render(<Insights />);

    const watch = await screen.findByTestId("watch");
    expect(watch).toHaveTextContent("28/10/2026");
    expect(watch).toHaveTextContent("Reunião do Fed");
    expect(watch).toHaveTextContent("Juros mexem em crescimento.");
  });

  it("aviso de que não é recomendação vem do próprio relatório", async () => {
    render(<Insights />);

    expect(await screen.findByTestId("disclaimer")).toHaveTextContent("não recomendação de compra ou venda");
  });

  it("abre a análise de outro dia", async () => {
    const user = userEvent.setup();
    vi.mocked(api.getInsight).mockResolvedValue({
      report_date: "2026-10-08",
      report: report({ headline: "Ontem", news: [] }),
    });
    render(<Insights />);
    await screen.findByTestId("headline");

    await user.selectOptions(screen.getByLabelText("Outra edição"), "2026-10-08");

    await waitFor(() => expect(screen.getByTestId("headline")).toHaveTextContent("Ontem"));
    expect(api.getInsight).toHaveBeenCalledWith("2026-10-08");
    expect(screen.queryByTestId("news")).not.toBeInTheDocument();
    // Edição antiga escolhida de propósito: não é "atraso" da análise.
    expect(screen.queryByTestId("stale-edition")).not.toBeInTheDocument();
  });

  it("dia que não abre mostra o motivo e mantém a análise atual", async () => {
    const user = userEvent.setup();
    vi.mocked(api.getInsight).mockRejectedValue(
      new ApiError(404, "Not Found", '{"detail":"a análise de 08/10/2026 está com formato inválido"}'),
    );
    render(<Insights />);
    await screen.findByTestId("headline");

    await user.selectOptions(screen.getByLabelText("Outra edição"), "2026-10-08");

    expect(await screen.findByRole("alert")).toHaveTextContent("formato inválido");
    expect(screen.getByTestId("headline")).toHaveTextContent("Juros americanos");
  });

  it("sem análise ainda, explica como ela chega", async () => {
    vi.mocked(api.getInsights).mockResolvedValue(index({ latest: null, history: [] }));

    render(<Insights />);

    const empty = await screen.findByTestId("no-insights");
    expect(empty).toHaveTextContent("dias úteis de manhã");
    expect(empty).toHaveTextContent("Retrato da carteira atualizado em");
  });

  it("arquivos recusados aparecem com o motivo", async () => {
    vi.mocked(api.getInsights).mockResolvedValue(
      index({ invalid_files: [{ file_name: "2026-10-10.json", error: "news.0.url: link precisa começar com http" }] }),
    );

    render(<Insights />);

    expect(await screen.findByTestId("invalid-files")).toHaveTextContent("1 arquivo de análise foi recusado");
  });

  it("falha ao gravar o retrato avisa, mas a análise aparece", async () => {
    vi.mocked(api.writeSnapshot).mockRejectedValue(new ApiError(500, "Error", '{"detail":"pasta sem permissão"}'));

    render(<Insights />);

    expect(await screen.findByTestId("snapshot-error")).toHaveTextContent("pasta sem permissão");
    expect(screen.getByTestId("headline")).toBeInTheDocument();
  });

  it("falha ao carregar aparece como erro", async () => {
    vi.mocked(api.getInsights).mockRejectedValue(new Error("rede"));

    render(<Insights />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível carregar as análises");
  });

  describe("jornal (relatório v3)", () => {
    const v3 = (): Partial<InsightReport> => ({
      schema_version: 3,
      summary: ["Lide do dia.", "Segundo.", "Terceiro.", "Quarto parágrafo escondido."],
      market: [
        {
          label: "S&P 500",
          value: "6.712",
          change: "-0,4%",
          direction: "DOWN",
          as_of: "2026-10-24",
          source: "Yahoo Finance",
        },
        { label: "Selic", value: "15,00%", change: null, direction: null, as_of: "2026-10-24", source: "BCB" },
      ],
      opportunities: [
        {
          title: "Semicondutores depois da correção",
          thesis: "Lucros seguem crescendo enquanto o preço caiu.",
          tickers: ["SMH"],
          relation: "O QQQ já tem chips.",
          why_now: "Queda de 12% em um mês.",
          risks: ["Demanda de IA desacelerar"],
          how_to_follow: "Resultados da TSMC.",
          sources: [{ title: "FactSet", url: "https://insight.factset.com/x" }],
        },
      ],
    });

    it("faixa do mercado com direção em texto, não só cor", async () => {
      vi.mocked(api.getInsights).mockResolvedValue(
        index({ latest: { report_date: "2026-10-09", report: report(v3()) } }),
      );
      render(<Insights />);

      const items = await screen.findAllByTestId("market-item");
      expect(items[0]).toHaveTextContent("S&P 500");
      expect(within(items[0]).getByLabelText("caiu")).toBeInTheDocument();
      expect(items[1]).toHaveTextContent("15,00%");
    });

    it("oportunidades vêm com o aviso de que não são recomendação, riscos e fontes", async () => {
      vi.mocked(api.getInsights).mockResolvedValue(
        index({ latest: { report_date: "2026-10-09", report: report(v3()) } }),
      );
      render(<Insights />);

      const card = await screen.findByTestId("opportunity");
      expect(screen.getByTestId("opportunities-caveat")).toHaveTextContent("não são recomendação de compra");
      expect(card).toHaveTextContent("Por que agora");
      expect(card).toHaveTextContent("Demanda de IA desacelerar");
      expect(within(card).getByRole("link", { name: "FactSet" })).toHaveAttribute(
        "href",
        "https://insight.factset.com/x",
      );
    });

    it("lide com três parágrafos; o resto esmaece e abre em 'Continuar lendo'", async () => {
      const user = userEvent.setup();
      vi.mocked(api.getInsights).mockResolvedValue(
        index({ latest: { report_date: "2026-10-09", report: report(v3()) } }),
      );
      render(<Insights />);

      const summary = await screen.findByTestId("summary");
      const rest = within(summary).getByTestId("read-more-text");
      expect(rest).toHaveTextContent("Quarto parágrafo escondido.");
      expect(rest).toHaveAttribute("aria-hidden", "true");
      expect(within(summary).getByText("Lide do dia.").closest("[data-testid=read-more-text]")).toBeNull();
      expect(within(summary).getByText("Terceiro.").closest("[data-testid=read-more-text]")).toBeNull();

      await user.click(within(summary).getByRole("button", { name: "Continuar lendo" }));
      expect(rest).toHaveAttribute("aria-hidden", "false");
      expect(within(summary).queryByRole("button", { name: "Continuar lendo" })).toBeNull();
    });

    it("relatório v1 continua abrindo, sem faixa nem oportunidades", async () => {
      render(<Insights />);

      await screen.findByTestId("headline");
      expect(screen.queryByTestId("market-strip")).toBeNull();
      expect(screen.queryByTestId("opportunities")).toBeNull();
    });

    it("edição antiga avisa que a análise não rodou", async () => {
      render(<Insights />); // edição de 09/10/2026, bem antes de hoje

      expect(await screen.findByTestId("stale-edition")).toHaveTextContent("dias atrás");
    });

    it("empresas por trás dos ETFs, com a soma pelos fundos", async () => {
      vi.mocked(api.getLookThrough).mockResolvedValue({
        report_date: "2026-10-09",
        currencies: [
          {
            currency_code: "USD",
            companies: [
              {
                name: "NVIDIA",
                ticker: "NVDA",
                weight: "0.071",
                via: [
                  { ticker: "QQQ", weight: "0.05" },
                  { ticker: "SPY", weight: "0.021" },
                ],
              },
              { name: "Microsoft", ticker: "MSFT", weight: "0.04", via: [{ ticker: "QQQ", weight: "0.04" }] },
            ],
            funds: [{ ticker: "QQQ", weight: "0.5", coverage: "0.18", as_of: "2026-10-08", source: "Invesco" }],
            missing: ["VNQ"],
            explained: "0.111",
          },
        ],
      });
      render(<Insights />);

      const panel = await screen.findByTestId("lookthrough");
      const rows = within(panel).getAllByTestId("lookthrough-company");
      expect(rows[0]).toHaveTextContent("NVIDIA");
      expect(rows[0]).toHaveTextContent("7,1%");
      expect(rows[0]).toHaveTextContent("QQQ 5,0% + SPY 2,1%");
      expect(rows[1]).not.toHaveTextContent("QQQ 4,0%"); // um fundo só: sem a conta "via"
      expect(screen.getByTestId("lookthrough-explained-USD")).toHaveTextContent("somam 11,1% da carteira");
      expect(panel).toHaveTextContent("Sem composição: VNQ.");
    });
  });

  describe("leitura (dislexia), destaques e outras leituras", () => {
    it("Aa troca a fonte do texto e fica salvo neste aparelho", async () => {
      const user = userEvent.setup();
      render(<Insights />);
      const article = await screen.findByTestId("newspaper");

      await user.click(screen.getByRole("button", { name: "Ajustes de leitura" }));
      await user.click(screen.getByRole("button", { name: /Lexend/ }));
      await user.click(screen.getByRole("button", { name: "Papel" }));

      expect(article.style.getPropertyValue("--read-font")).toContain("Lexend");
      expect(article).toHaveAttribute("data-tint", "papel");
      expect(JSON.parse(localStorage.getItem("reading-prefs-v1")!).font).toBe("lexend");
      localStorage.clear();
    });

    it("trechos destacados antes aparecem marcados", async () => {
      vi.mocked(notesApi.getNotes).mockResolvedValue([
        {
          id: "n",
          title: null,
          body: "",
          quote: "sinalizou mais uma alta",
          source_title: null,
          source_url: null,
          tickers: [],
          pinned: false,
          share_with_claude: false,
          created_at: "2026-10-09T10:00:00Z",
          updated_at: "2026-10-09T10:00:00Z",
        },
      ]);
      render(<Insights />);
      const summary = await screen.findByTestId("summary");
      expect(await within(summary).findByText("sinalizou mais uma alta")).toHaveProperty("tagName", "MARK");
    });

    it("outras leituras do relatório v4 e o painel de fontes", async () => {
      vi.mocked(api.getInsights).mockResolvedValue(
        index({
          latest: {
            report_date: "2026-10-09",
            report: report({
              schema_version: 4,
              papers: [
                {
                  source: "World Reports",
                  title: "Prancha nova",
                  url: "https://worldreports.io/brasil/pt/",
                  published_at: null,
                  summary: "Resumo.",
                  takeaways: [],
                  relation: null,
                },
              ],
            }),
          },
        }),
      );
      render(<Insights />);
      expect(await screen.findByTestId("papers")).toHaveTextContent("World Reports");
      expect(screen.getByTestId("sources")).toBeInTheDocument();
    });

    it("destacar um trecho do jornal guarda nas anotações, com a edição como fonte", async () => {
      const user = userEvent.setup();
      Range.prototype.getBoundingClientRect = () => ({ top: 100, bottom: 120, left: 50, width: 80 }) as DOMRect;
      vi.mocked(notesApi.createNote).mockImplementation(async (n) => ({
        id: "x",
        title: null,
        body: "",
        quote: n.quote ?? null,
        source_title: n.source_title ?? null,
        source_url: null,
        tickers: [],
        pinned: false,
        share_with_claude: false,
        created_at: "2026-10-09T10:00:00Z",
        updated_at: "2026-10-09T10:00:00Z",
      }));
      render(<Insights />);
      const summary = await screen.findByTestId("summary");

      const node = within(summary).getByText("O Fed sinalizou mais uma alta.").firstChild!;
      const range = document.createRange();
      range.setStart(node, 2);
      range.setEnd(node, 5);
      window.getSelection()!.removeAllRanges();
      window.getSelection()!.addRange(range);
      act(() => {
        document.dispatchEvent(new Event("selectionchange"));
      });

      await user.click(await screen.findByRole("button", { name: /Destacar/ }));
      expect(notesApi.createNote).toHaveBeenCalledWith(
        expect.objectContaining({
          quote: "Fed",
          source_title: "Jornal da carteira · 09/10/2026",
          share_with_claude: false,
        }),
      );
      expect(await screen.findByRole("status")).toHaveTextContent("Trecho destacado");
    });
  });
});
