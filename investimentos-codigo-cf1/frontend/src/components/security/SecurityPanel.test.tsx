import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as authApi from "../../api/auth";
import { SecurityPanel } from "./SecurityPanel";

vi.mock("../../api/auth");

const local = { remote: false, unlocked: true, has_passkeys: true, idle_minutes: 15 };
const key = {
  id: "k1",
  name: "iPhone 16e",
  rp_id: "pc.tail.ts.net",
  created_at: "2026-10-28T10:00:00Z",
  last_used_at: null,
};

describe("SecurityPanel", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(authApi.getAuthStatus).mockResolvedValue(local);
    vi.mocked(authApi.getPasskeys).mockResolvedValue([key]);
  });

  it("gera o código de cadastro", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.createPairingCode).mockResolvedValue({ code: "ABCD-EFGH", expires_at: "2026-10-28T10:10:00" });
    render(<SecurityPanel />);

    await user.click(await screen.findByRole("button", { name: "Gerar código" }));
    expect(await screen.findByTestId("pairing-code")).toHaveTextContent("ABCD-EFGH");
    expect(screen.getByTestId("pairing-code")).toHaveTextContent("Vale até 10:10");
  });

  it("remover pede confirmação", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.deletePasskey).mockResolvedValue(undefined);
    render(<SecurityPanel />);

    const device = await screen.findByTestId("device");
    expect(device).toHaveTextContent("iPhone 16e");
    expect(device).toHaveTextContent("nunca usado");
    await user.click(within(device).getByRole("button", { name: "Remover" }));
    expect(authApi.deletePasskey).not.toHaveBeenCalled();
    await user.click(within(device).getByRole("button", { name: "Remover de vez" }));
    expect(authApi.deletePasskey).toHaveBeenCalledWith("k1");
  });

  it("bloquear todos avisa quantas sessões caíram", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.revokeAllSessions).mockResolvedValue({ revoked: 2 });
    render(<SecurityPanel />);

    await user.click(await screen.findByRole("button", { name: "Bloquear todos os aparelhos agora" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Bloqueado em 2 sessão(ões)");
  });

  it("no celular, só bloquear agora (aparelhos ficam no computador)", async () => {
    vi.mocked(authApi.getAuthStatus).mockResolvedValue({ ...local, remote: true });
    render(<SecurityPanel />);

    expect(await screen.findByTestId("security-remote")).toHaveTextContent("só pelo computador");
    expect(screen.getByRole("button", { name: "Bloquear agora" })).toBeInTheDocument();
    expect(authApi.getPasskeys).not.toHaveBeenCalled();
  });
});
