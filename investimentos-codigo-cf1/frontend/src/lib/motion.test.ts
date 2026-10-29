import { afterEach, describe, expect, it, vi } from "vitest";

import { navigate, shouldPlayIntro } from "./motion";

function reducedMotion(on: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: on && query.includes("reduce") }));
  window.matchMedia = globalThis.matchMedia;
}

describe("movimento", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
    delete (document as { startViewTransition?: unknown }).startViewTransition;
    delete document.documentElement.dataset.nav;
  });

  it("sem View Transitions, só troca", () => {
    reducedMotion(false);
    const update = vi.fn();
    navigate(update, "push");
    expect(update).toHaveBeenCalledOnce();
    expect(document.documentElement.dataset.nav).toBeUndefined();
  });

  it("com View Transitions, marca a direção e troca dentro da transição", () => {
    reducedMotion(false);
    const start = vi.fn((cb: () => void) => cb());
    (document as { startViewTransition?: unknown }).startViewTransition = start;
    const update = vi.fn();
    navigate(update, "pop");
    expect(start).toHaveBeenCalledOnce();
    expect(update).toHaveBeenCalledOnce();
    expect(document.documentElement.dataset.nav).toBe("pop");
  });

  it("com 'reduzir movimento', nada de transição nem abertura", () => {
    reducedMotion(true);
    const start = vi.fn();
    (document as { startViewTransition?: unknown }).startViewTransition = start;
    navigate(vi.fn());
    expect(start).not.toHaveBeenCalled();
    expect(shouldPlayIntro()).toBe(false);
  });

  it("abertura toca uma vez por sessão", () => {
    reducedMotion(false);
    expect(shouldPlayIntro()).toBe(true);
    expect(shouldPlayIntro()).toBe(false);
  });
});
