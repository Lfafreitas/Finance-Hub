// Leva uma pergunta + o resumo da carteira para o Claude (app ou
// claude.ai), pela assinatura. O dashboard não chama nenhuma IA.

export const CLAUDE_NEW_CHAT = "https://claude.ai/new";
/** Acima disto (link já codificado) o link fica grande demais; vai só pela área de transferência. */
export const MAX_URL_LENGTH = 8000;

export const SUGGESTIONS = [
  "A Tesla subiu com os anúncios recentes. Quanto disso chegou na minha carteira pelo SPY?",
  "O QQQ caiu nas últimas semanas. Pelos números de hoje (P/L, faixa de 52 semanas, juros), o preço está caro ou barato em relação ao histórico?",
  "Com os juros americanos de agora, quais são os prós e contras de ter mais SPY ou VNQ em vez de QQQ e AAXJ?",
  "Como a minha carteira ficaria numa divisão tipo ARCA? Quanto falta em cada parte, considerando a minha reserva em reais?",
  "Faz sentido ter de 3% a 5% em cripto para alguém com a minha carteira? Quais riscos e custos (imposto, corretora, custódia)?",
] as const;

// Nome opcional para o Claude chamar você pelo nome: VITE_USER_NAME no
// frontend/.env.local (fica só no seu computador).
const USER_NAME = (import.meta.env.VITE_USER_NAME ?? "").trim();

export function buildPrompt(question: string, context: string): string {
  return [
    'Use a skill "analista-da-carteira" se ela estiver instalada.',
    `${USER_NAME ? `Sou o ${USER_NAME} e quero` : "Quero"} conversar sobre a minha carteira de investimentos. Abaixo está o resumo do meu dashboard.`,
    "Pesquise na web o que precisar (notícias, preços e indicadores de hoje) e cite fonte e data.",
    "Me ajude a entender os números, os cenários e os prós e contras para EU decidir.",
    "",
    `Minha pergunta: ${question.trim()}`,
    "",
    context,
  ].join("\n");
}

/** Link que já abre o Claude com a pergunta, ou null se ficaria grande demais. */
export function claudeLink(prompt: string): string | null {
  const link = `${CLAUDE_NEW_CHAT}?q=${encodeURIComponent(prompt)}`;
  return link.length > MAX_URL_LENGTH ? null : link;
}
