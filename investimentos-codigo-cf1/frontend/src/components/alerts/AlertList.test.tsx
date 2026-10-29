import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api/insights";
import { alert } from "../../test/kpiFixtures";
import { AlertList } from "./AlertList";

vi.mock("../../api/insights");

describe("AlertList", () => {
  beforeEach(() => vi.resetAllMocks());

  it("sem alertas explica que o normal é não haver", async () => {
    vi.mocked(api.getAlerts).mockResolvedValue({ alerts: [], unread_count: 0, invalid_files: [] });
    render(<AlertList />);

    expect(await screen.findByTestId("no-alerts")).toHaveTextContent("Nenhuma notícia séria");
    expect(api.getAlerts).toHaveBeenCalledWith(7);
  });

  it("mostra cada alerta com o porquê, as fontes e marca como lido", async () => {
    const unread = { day: "2026-10-15", read: false, alert: alert({ severity: "CRITICA" }) };
    vi.mocked(api.getAlerts).mockResolvedValue({ alerts: [unread], unread_count: 1, invalid_files: [] });
    vi.mocked(api.markAlertRead).mockResolvedValue({
      alerts: [{ ...unread, read: true }],
      unread_count: 0,
      invalid_files: [],
    });
    render(<AlertList />);

    const item = await screen.findByTestId("alert-a1");
    expect(item).toHaveTextContent("Crítico");
    expect(item).toHaveTextContent("novo");
    expect(item).toHaveTextContent("Para a sua carteira: AAXJ tem peso alto em Coreia.");
    expect(screen.getByRole("link", { name: "AP" })).toHaveAttribute("href", "https://apnews.com/x");

    await userEvent.setup().click(screen.getByRole("button", { name: "Marcar como lido" }));

    expect(api.markAlertRead).toHaveBeenCalledWith("a1");
    await waitFor(() => expect(screen.getByTestId("alert-a1")).not.toHaveTextContent("novo"));
  });

  it("arquivo recusado é avisado", async () => {
    vi.mocked(api.getAlerts).mockResolvedValue({
      alerts: [],
      unread_count: 0,
      invalid_files: [{ file_name: "2026-10-14.json", error: "x" }],
    });
    render(<AlertList />);

    expect(await screen.findByText(/1 arquivo\(s\) de alerta recusado\(s\): 2026-10-14.json/)).toBeInTheDocument();
  });
});

describe("AlertList no jornal", () => {
  it("sem alerta, vira uma linha discreta em vez de um quadro", async () => {
    vi.mocked(api.getAlerts).mockResolvedValue({ alerts: [], unread_count: 0, invalid_files: [] });
    render(<AlertList compactWhenEmpty />);

    expect(await screen.findByTestId("no-alerts")).toHaveTextContent("Nenhum alerta sério nos últimos 7 dias");
    expect(screen.queryByTestId("alert-list")).toBeNull();
  });
});
