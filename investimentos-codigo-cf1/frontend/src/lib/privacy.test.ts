import { afterEach, describe, expect, it, vi } from "vitest";

import { formatCompactCurrency, formatCurrency, formatPercent, formatQuantity, formatSignedCurrency } from "./formatCurrency";
import { exactTitle, isPrivate, setPrivate, subscribePrivacy } from "./privacy";

const plain = (s: string) => s.replace(/ /g, " ");

describe("modo privacidade", () => {
  afterEach(() => setPrivate(false));

  it("esconde dinheiro e quantidade, mantém percentual", () => {
    setPrivate(true);

    expect(plain(formatCurrency("1234.5", "BRL"))).toBe("R$ •••••");
    expect(plain(formatSignedCurrency("-10", "USD"))).toBe("US$ •••••");
    expect(plain(formatCompactCurrency(1200, "USD"))).toBe("US$ •••••");
    expect(formatQuantity("0.25751347")).toBe("•••••");
    expect(formatPercent("0.1")).toContain("10,00");
    expect(exactTitle("123.45")).toBeUndefined();
  });

  it("desligado mostra tudo e o title exato volta", () => {
    expect(plain(formatCurrency("1234.5", "BRL"))).toBe("R$ 1.234,50");
    expect(exactTitle("123.45")).toBe("123.45");
  });

  it("avisa quem assina e lembra a escolha", () => {
    const listener = vi.fn();
    const off = subscribePrivacy(listener);

    setPrivate(true);

    expect(listener).toHaveBeenCalledTimes(1);
    expect(isPrivate()).toBe(true);
    expect(window.localStorage.getItem("dashboard:privacy")).toBe("1");
    off();
    setPrivate(false);
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
