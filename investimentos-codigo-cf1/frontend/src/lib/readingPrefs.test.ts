import { afterEach, describe, expect, it } from "vitest";

import { DEFAULT_PREFS, clampSize, loadPrefs, readingStyle, savePrefs } from "./readingPrefs";

describe("preferências de leitura", () => {
  afterEach(() => localStorage.clear());

  it("padrão quando nada foi salvo, e guarda neste aparelho", () => {
    expect(loadPrefs()).toEqual(DEFAULT_PREFS);
    savePrefs({ ...DEFAULT_PREFS, font: "opendyslexic", size: 21 });
    expect(loadPrefs()).toMatchObject({ font: "opendyslexic", size: 21 });
  });

  it("valores estranhos voltam para o padrão", () => {
    localStorage.setItem("reading-prefs-v1", JSON.stringify({ font: "comic", size: 99, spacing: "x" }));
    expect(loadPrefs()).toMatchObject({ font: "padrao", size: 26, spacing: "normal" });
    localStorage.setItem("reading-prefs-v1", "{quebrado");
    expect(loadPrefs()).toEqual(DEFAULT_PREFS);
  });

  it("tamanho entre 14 e 26", () => {
    expect(clampSize(3)).toBe(14);
    expect(clampSize(40)).toBe(26);
    expect(clampSize(Number.NaN)).toBe(17);
  });

  it("espaçamento amplo abre letras, palavras e linhas; largura estreita encurta a linha", () => {
    const style = readingStyle({ ...DEFAULT_PREFS, spacing: "amplo", width: "estreita", font: "lexend" }) as Record<
      string,
      string
    >;
    expect(style["--read-line"]).toBe("2.1");
    expect(style["--read-letter"]).toBe("0.05em");
    expect(style["--read-word"]).toBe("0.16em");
    expect(style["--read-width"]).toBe("58ch");
    expect(style["--read-font"]).toContain("Lexend");
  });
});
