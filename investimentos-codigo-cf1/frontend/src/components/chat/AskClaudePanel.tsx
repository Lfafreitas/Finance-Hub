import { useEffect, useState } from "react";

import { getChatContext } from "../../api/insights";
import { describeApiError } from "../../lib/apiErrors";
import { ASK_CLAUDE_EVENT } from "../../lib/notes";
import { isPrivate } from "../../lib/privacy";
import { SUGGESTIONS, buildPrompt, claudeLink, CLAUDE_NEW_CHAT } from "../../lib/askClaude";
import { BUTTON_CLASS, INPUT_CLASS, PANEL_CLASS, SECTION_TITLE_CLASS } from "../../lib/ui";

type Sent = { kind: "link" } | { kind: "clipboard" } | { kind: "manual" };

async function copy(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/**
 * Conversar com o Claude sobre a carteira, pela assinatura: a pergunta e
 * um resumo da carteira (sem extratos) vão para o Claude — já preenchidos
 * no link quando cabem, e sempre na área de transferência.
 */
export function AskClaudePanel() {
  const [question, setQuestion] = useState("");
  const [context, setContext] = useState<string | null>(null);
  const [contextError, setContextError] = useState<string | null>(null);
  const [sent, setSent] = useState<Sent | null>(null);
  const [manualText, setManualText] = useState<string | null>(null);

  // Pergunta pronta vinda de um trecho selecionado no Jornal.
  useEffect(() => {
    const onAsk = (event: Event) => {
      const question = (event as CustomEvent<{ question: string }>).detail?.question;
      if (!question) return;
      setQuestion(question);
      setSent(null);
      document.getElementById("ask-title")?.scrollIntoView({ behavior: "smooth", block: "start" });
    };
    window.addEventListener(ASK_CLAUDE_EVENT, onAsk);
    return () => window.removeEventListener(ASK_CLAUDE_EVENT, onAsk);
  }, []);

  useEffect(() => {
    getChatContext()
      .then((c) => setContext(c.text))
      .catch((err: unknown) => setContextError(describeApiError(err)));
  }, []);

  async function send(open: boolean) {
    if (context === null || question.trim() === "") return;
    const prompt = buildPrompt(question, context);
    const copied = await copy(prompt);
    if (!copied) setManualText(prompt);
    if (open) {
      const link = claudeLink(prompt);
      window.open(link ?? CLAUDE_NEW_CHAT, "_blank", "noopener,noreferrer");
      setSent(link ? { kind: "link" } : copied ? { kind: "clipboard" } : { kind: "manual" });
    } else {
      setSent(copied ? { kind: "clipboard" } : { kind: "manual" });
    }
  }

  return (
    <section aria-labelledby="ask-title" data-testid="ask-claude">
      <h2 id="ask-title" className={`mb-3 ${SECTION_TITLE_CLASS}`}>
        Conversar com o Claude sobre a carteira
      </h2>
      <div className={`${PANEL_CLASS} space-y-4`}>
        <p className="max-w-3xl text-sm leading-relaxed text-neutral-400">
          A conversa acontece no Claude, pela sua assinatura (sem custo extra), com busca na web. O dashboard leva junto
          um resumo da carteira — posições, pesos, resultados, alocação e a última análise — sem nenhum lançamento de
          extrato.
        </p>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Sugestões de pergunta">
          {SUGGESTIONS.map((text) => (
            <button
              key={text}
              type="button"
              className="rounded-full border border-neutral-800 px-3 py-1 text-left text-xs text-neutral-300 transition-colors hover:border-neutral-600 hover:text-neutral-100"
              onClick={() => {
                setQuestion(text);
                setSent(null);
              }}
            >
              {text.length > 70 ? `${text.slice(0, 68)}…` : text}
            </button>
          ))}
        </div>
        <div>
          <label htmlFor="ask-question" className="mb-1 block text-xs text-neutral-400">
            Sua pergunta
          </label>
          <textarea
            id="ask-question"
            rows={3}
            className={INPUT_CLASS}
            placeholder="Ex.: vale a pena comprar mais QQQ depois dessa queda ou diversificar com SPY?"
            value={question}
            onChange={(e) => {
              setQuestion(e.target.value);
              setSent(null);
            }}
          />
        </div>
        {contextError && (
          <p className="text-sm text-red-400" role="alert">
            Não consegui montar o resumo da carteira: {contextError}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className={`${BUTTON_CLASS} border-sky-400/60 text-sky-300`}
            disabled={context === null || question.trim() === ""}
            onClick={() => void send(true)}
          >
            Abrir no Claude
          </button>
          <button
            type="button"
            className={BUTTON_CLASS}
            disabled={context === null || question.trim() === ""}
            onClick={() => void send(false)}
          >
            Só copiar
          </button>
          {sent && (
            <p className="text-sm text-neutral-300" role="status" data-testid="ask-status">
              {sent.kind === "link" && "Abri o Claude com a pergunta e o resumo. Também está copiado, se precisar."}
              {sent.kind === "clipboard" &&
                "Pergunta e resumo copiados. No Claude, cole com Ctrl+V (ou no app do Claude, se preferir)."}
              {sent.kind === "manual" && "Não consegui copiar sozinho: selecione o texto abaixo e copie."}
            </p>
          )}
        </div>
        {manualText && sent?.kind === "manual" && (
          <textarea readOnly rows={6} className={`${INPUT_CLASS} font-mono text-xs`} value={manualText} />
        )}
        {context && (
          <details>
            <summary className="cursor-pointer text-xs text-neutral-400 hover:text-neutral-200">
              Ver o resumo que vai junto ({context.length.toLocaleString("pt-BR")} caracteres)
            </summary>
            <pre
              className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-md bg-neutral-950 p-3 text-xs text-neutral-300"
              data-testid="ask-context"
            >
              {isPrivate() ? "Escondido no modo privacidade. Os valores vão junto ao abrir no Claude." : context}
            </pre>
          </details>
        )}
      </div>
    </section>
  );
}
