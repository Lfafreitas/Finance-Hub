import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api/insights";
import { alert } from "../../test/kpiFixtures";
import { AlertBanner } from "./AlertBanner";

vi.mock("../../api/insights");

const index = (items: { read: boolean; severity?: "ALTA" | "CRITICA"; id: string; title?: string }[]) => ({
  alerts: items.map((i) => ({
    day: "2026-10-15",
    read: i.read,
    alert: alert({ id: i.id, severity: i.severity ?? "ALTA", title: i.title ?? `Alerta ${i.id}` }),
  })),
  unread_count: items.filter((i) => !i.read).length,
  invalid_files: [],
});

describe("AlertBanner", () => {
  beforeEach(() => vi.resetAllMocks());

  it("sem alerta não lido não aparece", async () => {
    vi.mocked(api.getAlerts).mockResolvedValue(index([{ id: "a", read: true }]));
    render(<AlertBanner onOpen={() => {}} />);

    await waitFor(() => expect(api.getAlerts).toHaveBeenCalledWith(2));
    expect(screen.queryByTestId("alert-banner")).toBeNull();
  });

  it("mostra o mais novo, quantos mais e leva aos detalhes", async () => {
    const onOpen = vi.fn();
    vi.mocked(api.getAlerts).mockResolvedValue(
      index([
        { id: "b", read: false, title: "Kospi cai 7%" },
        { id: "c", read: false },
        { id: "d", read: true },
      ]),
    );
    render(<AlertBanner onOpen={onOpen} />);

    const banner = await screen.findByTestId("alert-banner");
    expect(banner).toHaveTextContent("Alerta (AAXJ):Kospi cai 7%+1 não lido(s)");
    await userEvent.setup().click(screen.getByRole("button", { name: "Ver detalhes" }));
    expect(onOpen).toHaveBeenCalled();
  });

  it("crítico é dito no texto, não só na cor", async () => {
    vi.mocked(api.getAlerts).mockResolvedValue(index([{ id: "x", read: false, severity: "CRITICA" }]));
    render(<AlertBanner onOpen={() => {}} />);

    expect(await screen.findByTestId("alert-banner")).toHaveTextContent("Alerta crítico");
  });

  it("marcar como lido some com a faixa", async () => {
    vi.mocked(api.getAlerts).mockResolvedValue(index([{ id: "x", read: false }]));
    vi.mocked(api.markAllAlertsRead).mockResolvedValue(index([{ id: "x", read: true }]));
    render(<AlertBanner onOpen={() => {}} />);

    const button = await screen.findByRole("button", { name: "Marcar como lido" });
    // Depois de marcar, o backend já responde tudo lido.
    vi.mocked(api.getAlerts).mockResolvedValue(index([{ id: "x", read: true }]));
    await userEvent.setup().click(button);

    await waitFor(() => expect(screen.queryByTestId("alert-banner")).toBeNull());
    expect(api.markAllAlertsRead).toHaveBeenCalledTimes(1);
  });

  it("erro ao ler os alertas não mostra nada", async () => {
    vi.mocked(api.getAlerts).mockRejectedValue(new Error("x"));
    render(<AlertBanner onOpen={() => {}} />);

    await waitFor(() => expect(api.getAlerts).toHaveBeenCalled());
    expect(screen.queryByTestId("alert-banner")).toBeNull();
  });
});
