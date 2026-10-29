import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as notesApi from "../../api/notes";
import { DEFAULT_PREFS, type ReadingPrefs } from "../../lib/readingPrefs";
import { Highlighted } from "./Highlighted";
import { OtherReadings, SourcesPanel } from "./OtherReadings";
import { ReadingSettings } from "./ReadingSettings";
import { SelectionToolbar } from "./SelectionToolbar";

vi.mock("../../api/notes");

describe("Highlighted", () => {
  it("marca os trechos que aparecem inteiros e ignora o resto", () => {
    const { container } = render(
      <p>
        <Highlighted
          text="O Fed manteve os juros e o dólar caiu."
          quotes={["manteve os juros", "não existe", "ab", "dólar"]}
        />
      </p>,
    );
    expect([...container.querySelectorAll("mark")].map((m) => m.textContent)).toEqual(["manteve os juros", "dólar"]);
    expect(container.textContent).toBe("O Fed manteve os juros e o dólar caiu.");
  });

  it("trechos sobrepostos não duplicam o texto", () => {
    const { container } = render(<Highlighted text="abcdefgh" quotes={["abcde", "cdefg"]} />);
    expect(container.textContent).toBe("abcdefgh");
    expect(container.querySelectorAll("mark")).toHaveLength(1);
  });
});

function SettingsHarness({ onChange }: { onChange: (p: ReadingPrefs) => void }) {
  const [prefs, setPrefs] = useState(DEFAULT_PREFS);
  return (
    <ReadingSettings
      prefs={prefs}
      onChange={(p) => {
        setPrefs(p);
        onChange(p);
      }}
    />
  );
}

describe("ReadingSettings (Aa)", () => {
  it("troca fonte, tamanho, espaçamento, largura e fundo", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<SettingsHarness onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: "Ajustes de leitura" }));
    const panel = screen.getByTestId("reading-settings");
    await user.click(within(panel).getByRole("button", { name: /OpenDyslexic/ }));
    await user.click(within(panel).getByRole("button", { name: "Aumentar texto" }));
    await user.click(within(panel).getByRole("button", { name: "Amplo" }));
    await user.click(within(panel).getByRole("button", { name: "Linhas curtas" }));
    await user.click(within(panel).getByRole("button", { name: "Papel" }));

    expect(onChange).toHaveBeenLastCalledWith({
      font: "opendyslexic",
      size: 18,
      spacing: "amplo",
      width: "estreita",
      tint: "papel",
    });
    expect(within(panel).getByRole("button", { name: /OpenDyslexic/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("Esc fecha o painel", async () => {
    const user = userEvent.setup();
    render(<SettingsHarness onChange={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Ajustes de leitura" }));
    await user.keyboard("{Escape}");
    expect(screen.queryByTestId("reading-settings")).toBeNull();
  });
});

function ToolbarHarness(actions: Parameters<typeof SelectionToolbar>[0]["actions"]) {
  const ref = useRef<HTMLDivElement>(null);
  return (
    <>
      <div ref={ref}>
        <p data-quote-source="Fonte X · Título" data-quote-url="https://x.example.com">
          O Fed manteve os juros nesta reunião.
        </p>
      </div>
      <p>fora do jornal</p>
      <SelectionToolbar container={ref} actions={actions} />
    </>
  );
}

function select(text: string) {
  const node = [...document.querySelectorAll("p")].find((p) => p.textContent?.includes(text))!.firstChild!;
  const start = node.textContent!.indexOf(text);
  const range = document.createRange();
  range.setStart(node, start);
  range.setEnd(node, start + text.length);
  const selection = window.getSelection()!;
  selection.removeAllRanges();
  selection.addRange(range);
  act(() => {
    document.dispatchEvent(new Event("selectionchange"));
  });
}

describe("SelectionToolbar", () => {
  beforeEach(() => {
    Range.prototype.getBoundingClientRect = () => ({ top: 100, bottom: 120, left: 50, width: 80 }) as DOMRect;
  });
  afterEach(() => window.getSelection()?.removeAllRanges());

  it("aparece ao selecionar no jornal, com a fonte do trecho", async () => {
    const user = userEvent.setup();
    const actions = { onHighlight: vi.fn(), onNote: vi.fn(), onAsk: vi.fn() };
    render(<ToolbarHarness {...actions} />);

    select("manteve os juros");
    await user.click(within(screen.getByTestId("selection-toolbar")).getByRole("button", { name: /Destacar/ }));

    expect(actions.onHighlight).toHaveBeenCalledWith({
      text: "manteve os juros",
      sourceTitle: "Fonte X · Título",
      sourceUrl: "https://x.example.com",
    });
  });

  it("anotar e perguntar recebem o trecho", async () => {
    const user = userEvent.setup();
    const actions = { onHighlight: vi.fn(), onNote: vi.fn(), onAsk: vi.fn() };
    render(<ToolbarHarness {...actions} />);

    select("nesta reunião");
    await user.click(screen.getByRole("button", { name: /Anotar/ }));
    expect(actions.onNote.mock.calls[0][0].text).toBe("nesta reunião");
    select("nesta reunião");
    await user.click(screen.getByRole("button", { name: /Perguntar/ }));
    expect(actions.onAsk.mock.calls[0][0].text).toBe("nesta reunião");
  });

  it("fora do jornal ou seleção curta demais: nada aparece", () => {
    render(<ToolbarHarness onHighlight={vi.fn()} onNote={vi.fn()} onAsk={vi.fn()} />);
    select("fora do jornal");
    expect(screen.queryByTestId("selection-toolbar")).toBeNull();
    select("Fe");
    expect(screen.queryByTestId("selection-toolbar")).toBeNull();
  });
});

describe("Outras leituras e fontes", () => {
  beforeEach(() => vi.resetAllMocks());

  it("agrupa por fonte, com resumo, pontos e link", () => {
    render(
      <OtherReadings
        papers={[
          {
            source: "World Reports",
            title: "Crédito",
            url: "https://w.example.com/1",
            published_at: "2026-10-22",
            summary: "Resumo 1.",
            takeaways: ["Ponto"],
            relation: "Afeta o CDI.",
          },
          {
            source: "World Reports",
            title: "Juros",
            url: "https://w.example.com/2",
            published_at: null,
            summary: "Resumo 2.",
            takeaways: [],
            relation: null,
          },
          {
            source: "Outro",
            title: "X",
            url: "https://o.example.com",
            published_at: null,
            summary: "Resumo 3.",
            takeaways: [],
            relation: null,
          },
        ]}
      />,
    );
    const items = screen.getAllByTestId("paper");
    expect(items).toHaveLength(3);
    expect(within(items[0]).getByRole("link", { name: "Crédito" })).toHaveAttribute("href", "https://w.example.com/1");
    expect(items[0]).toHaveTextContent("Para a sua carteira: Afeta o CDI.");
    expect(items[0]).toHaveAttribute("data-quote-source", "World Reports · Crédito");
  });

  it("cadastra, pausa e remove fontes", async () => {
    const user = userEvent.setup();
    const source = { id: "s1", name: "World Reports", url: "https://worldreports.io", focus: null, active: true };
    vi.mocked(notesApi.getSources).mockResolvedValueOnce([]).mockResolvedValue([source]);
    vi.mocked(notesApi.createSource).mockResolvedValue(source);
    vi.mocked(notesApi.updateSource).mockResolvedValue({ ...source, active: false });
    vi.mocked(notesApi.deleteSource).mockResolvedValue(undefined);
    render(<SourcesPanel />);

    await user.click(screen.getByText(/Suas fontes de leitura/));
    await user.type(screen.getByLabelText("Nome da fonte"), "World Reports");
    await user.type(screen.getByLabelText("Link da fonte"), "https://worldreports.io");
    await user.click(screen.getByRole("button", { name: "Adicionar" }));
    expect(notesApi.createSource).toHaveBeenCalledWith({
      name: "World Reports",
      url: "https://worldreports.io",
      focus: null,
      active: true,
    });

    const row = await screen.findByTestId("source");
    await user.click(within(row).getByRole("button", { name: "Pausar" }));
    expect(notesApi.updateSource).toHaveBeenCalledWith("s1", { ...source, id: undefined, active: false });
    await user.click(within(row).getByRole("button", { name: "Remover" }));
    expect(notesApi.deleteSource).toHaveBeenCalledWith("s1");
  });
});
