import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as authApi from "../../api/auth";
import { LOCKED_EVENT } from "../../api/client";
import { LockGate } from "./LockGate";

vi.mock("../../api/auth");

const status = (over: Partial<authApi.AuthStatus> = {}): authApi.AuthStatus => ({
  remote: true,
  unlocked: false,
  has_passkeys: true,
  idle_minutes: 15,
  ...over,
});

function notAllowed(): Error {
  const err = new Error("cancelado");
  err.name = "NotAllowedError";
  return err;
}

describe("LockGate", () => {
  beforeEach(() => vi.resetAllMocks());

  it("no computador, o app abre direto", async () => {
    vi.mocked(authApi.getAuthStatus).mockResolvedValue(status({ remote: false, unlocked: true }));
    render(<LockGate>dados</LockGate>);
    expect(await screen.findByText("dados")).toBeInTheDocument();
    expect(screen.queryByTestId("lock-screen")).toBeNull();
  });

  it("no celular, nada do app aparece antes do Face ID", async () => {
    vi.mocked(authApi.getAuthStatus).mockResolvedValue(status());
    render(<LockGate>dados</LockGate>);
    expect(await screen.findByTestId("lock-screen")).toBeInTheDocument();
    expect(screen.queryByText("dados")).toBeNull();
  });

  it("enquanto confere, não mostra os dados", () => {
    vi.mocked(authApi.getAuthStatus).mockReturnValue(new Promise(() => {}));
    render(<LockGate>dados</LockGate>);
    expect(screen.getByTestId("lock-loading")).toBeInTheDocument();
    expect(screen.queryByText("dados")).toBeNull();
  });

  it("Face ID abre; sessão vencida (401) tranca de novo", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.getAuthStatus).mockResolvedValue(status());
    vi.mocked(authApi.unlock).mockResolvedValue(status({ unlocked: true }));
    render(<LockGate>dados</LockGate>);

    await user.click(await screen.findByRole("button", { name: /Desbloquear com Face ID/ }));
    expect(await screen.findByText("dados")).toBeInTheDocument();

    act(() => {
      window.dispatchEvent(new Event(LOCKED_EVENT));
    });
    expect(await screen.findByTestId("lock-screen")).toBeInTheDocument();
    expect(screen.queryByText("dados")).toBeNull();
  });

  it("Face ID cancelado explica e deixa tentar de novo", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.getAuthStatus).mockResolvedValue(status());
    vi.mocked(authApi.unlock).mockRejectedValue(notAllowed());
    render(<LockGate>dados</LockGate>);

    await user.click(await screen.findByRole("button", { name: /Desbloquear com Face ID/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Face ID cancelado");
    expect(screen.getByRole("button", { name: /Desbloquear com Face ID/ })).toBeEnabled();
  });

  it("sem aparelho cadastrado, pede o código do computador", async () => {
    const user = userEvent.setup();
    vi.mocked(authApi.getAuthStatus).mockResolvedValue(status({ has_passkeys: false }));
    vi.mocked(authApi.registerThisDevice).mockResolvedValue(status({ unlocked: true, has_passkeys: true }));
    render(<LockGate>dados</LockGate>);

    const submit = await screen.findByRole("button", { name: /Cadastrar com Face ID/ });
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText("Código do computador"), "abcd-efgh");
    expect(screen.getByLabelText("Código do computador")).toHaveValue("ABCD-EFGH");
    await user.click(submit);

    expect(authApi.registerThisDevice).toHaveBeenCalledWith("ABCD-EFGH", "iPhone");
    expect(await screen.findByText("dados")).toBeInTheDocument();
  });

  it("ao ir para segundo plano, uma cortina cobre a tela", async () => {
    vi.mocked(authApi.getAuthStatus).mockResolvedValue(status({ unlocked: true }));
    render(<LockGate>dados</LockGate>);
    await screen.findByText("dados");
    // O ouvinte de "visibilitychange" entra num efeito depois de mostrar a tela;
    // com a máquina ocupada o evento chegava antes dele (teste instável).
    await act(async () => {});

    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(screen.getByTestId("privacy-curtain")).toBeInTheDocument();

    visibility.mockReturnValue("visible");
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await waitFor(() => expect(screen.queryByTestId("privacy-curtain")).toBeNull());
    expect(authApi.getAuthStatus).toHaveBeenCalledTimes(2); // voltou: confere a sessão
    visibility.mockRestore();
  });

  it("backend fora do ar: deixa o app mostrar o aviso dele", async () => {
    vi.mocked(authApi.getAuthStatus).mockRejectedValue(new Error("offline"));
    render(<LockGate>dados</LockGate>);
    expect(await screen.findByText("dados")).toBeInTheDocument();
  });
});
