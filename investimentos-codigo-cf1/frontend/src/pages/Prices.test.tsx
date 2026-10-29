import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as apiClient from "../api/client";
import { ApiError } from "../api/client";
import type { AssetLatestPrice } from "../api/types";
import { Prices } from "./Prices";

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  getLatestPrices: vi.fn(),
  setAssetPrice: vi.fn(),
}));

const petr4: AssetLatestPrice = {
  asset_id: "asset-petr4",
  asset_ticker: "PETR4",
  asset_name: "Petrobras",
  currency_code: "BRL",
  price: "30.00000000",
  price_date: "2026-06-20",
};
const aapl: AssetLatestPrice = {
  asset_id: "asset-aapl",
  asset_ticker: "AAPL",
  asset_name: "Apple",
  currency_code: "USD",
  price: null,
  price_date: null,
};

describe("Prices", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(apiClient.getLatestPrices).mockResolvedValue([aapl, petr4]);
  });

  it("sem ativos, orienta a cadastrar um antes", async () => {
    vi.mocked(apiClient.getLatestPrices).mockResolvedValue([]);

    render(<Prices />);

    expect(await screen.findByTestId("no-assets")).toHaveTextContent("Cadastros");
  });

  it("lista a última cotação de cada ativo e marca quem não tem", async () => {
    render(<Prices />);

    const rows = within(await screen.findByTestId("latest-prices")).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("AAPL");
    expect(rows[1]).toHaveTextContent("USD");
    expect(rows[1]).toHaveTextContent("Sem cotação");
    expect(rows[2]).toHaveTextContent("PETR4");
    expect(rows[2]).toHaveTextContent("30.00000000");
    expect(rows[2]).toHaveTextContent("20/06/2026");
  });

  it("registra a cotação como digitada, sem moeda no corpo, e relê a lista", async () => {
    vi.mocked(apiClient.setAssetPrice).mockResolvedValue({} as never);
    vi.mocked(apiClient.getLatestPrices)
      .mockResolvedValueOnce([aapl, petr4])
      .mockResolvedValueOnce([{ ...aapl, price: "187.45000000", price_date: "2026-06-30" }, petr4]);
    const user = userEvent.setup();
    render(<Prices />);
    const button = await screen.findByRole("button", { name: "Registrar cotação" });

    expect(button).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Ativo"), aapl.asset_id);
    expect(screen.getByLabelText("Preço por unidade (USD)")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Data da cotação"), "2026-06-30");
    await user.type(screen.getByLabelText("Preço por unidade (USD)"), "187.45");
    await user.click(button);

    await waitFor(() =>
      expect(apiClient.setAssetPrice).toHaveBeenCalledWith(aapl.asset_id, {
        price_date: "2026-06-30",
        price: "187.45",
      }),
    );
    expect(await screen.findByText("187.45000000")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Cotação registrada");
    expect(apiClient.getLatestPrices).toHaveBeenCalledTimes(2);
  });

  it("recusa do backend é mostrada e a lista não é relida", async () => {
    vi.mocked(apiClient.setAssetPrice).mockRejectedValue(
      new ApiError(400, "Bad Request", JSON.stringify({ detail: "a data da cotação não pode estar no futuro" })),
    );
    const user = userEvent.setup();
    render(<Prices />);

    await user.selectOptions(await screen.findByLabelText("Ativo"), petr4.asset_id);
    await user.type(screen.getByLabelText("Data da cotação"), "2099-01-01");
    await user.type(screen.getByLabelText("Preço por unidade (BRL)"), "30");
    await user.click(screen.getByRole("button", { name: "Registrar cotação" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("não pode estar no futuro");
    expect(apiClient.getLatestPrices).toHaveBeenCalledTimes(1);
  });

  it("falha ao carregar mostra erro", async () => {
    vi.mocked(apiClient.getLatestPrices).mockRejectedValue(new Error("500 falha"));

    render(<Prices />);

    expect(await screen.findByRole("alert")).toHaveTextContent("500 falha");
  });
});
