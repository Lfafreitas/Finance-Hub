import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "../api/client";
import { BackendStatus, HEALTH_EVERY_MS } from "./BackendStatus";

vi.mock("../api/client");

describe("BackendStatus", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => vi.useRealTimers());

  it("backend de pé: nada aparece", async () => {
    vi.mocked(apiClient.getHealth).mockResolvedValue({ status: "ok" });

    render(<BackendStatus />);

    await act(async () => {});
    expect(screen.queryByTestId("backend-down")).not.toBeInTheDocument();
  });

  it("backend fora: a faixa diz o que fazer e some quando ele volta", async () => {
    vi.mocked(apiClient.getHealth).mockRejectedValue(new TypeError("Failed to fetch"));

    render(<BackendStatus />);

    expect(await screen.findByTestId("backend-down")).toHaveTextContent("Ligue o uvicorn");
    vi.mocked(apiClient.getHealth).mockResolvedValue({ status: "ok" });
    await act(async () => {
      vi.advanceTimersByTime(HEALTH_EVERY_MS);
    });
    expect(screen.queryByTestId("backend-down")).not.toBeInTheDocument();
  });
});
