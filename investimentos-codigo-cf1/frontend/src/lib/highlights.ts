import { createContext } from "react";

/** Trechos destacados pelo leitor (das anotações), para marcar no Jornal. */
export const QuotesContext = createContext<string[]>([]);
