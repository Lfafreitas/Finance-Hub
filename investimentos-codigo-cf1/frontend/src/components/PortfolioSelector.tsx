import type { PortfolioRead } from "../api/types";

interface PortfolioSelectorProps {
  portfolios: PortfolioRead[];
  selectedPortfolioId: string | null;
  onChange: (portfolioId: string | null) => void;
}

export function PortfolioSelector({ portfolios, selectedPortfolioId, onChange }: PortfolioSelectorProps) {
  return (
    <select
      className="rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm text-neutral-100"
      value={selectedPortfolioId ?? ""}
      onChange={(event) => onChange(event.target.value === "" ? null : event.target.value)}
      aria-label="Selecionar carteira"
    >
      <option value="">Consolidado (todas as contas)</option>
      {portfolios.map((portfolio) => (
        <option key={portfolio.id} value={portfolio.id}>
          {portfolio.name}
        </option>
      ))}
    </select>
  );
}
