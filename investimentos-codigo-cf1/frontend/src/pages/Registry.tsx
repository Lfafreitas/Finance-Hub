import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from "react";

import {
  createAccount,
  createAsset,
  createInstitution,
  createPortfolio,
  deleteAccount,
  deleteAsset,
  deleteInstitution,
  deletePortfolio,
  getAccounts,
  getAssetClasses,
  getAssets,
  getCurrencies,
  getInstitutions,
  getPortfolios,
  updateAccount,
  updateAsset,
  updateInstitution,
  updatePortfolio,
} from "../api/client";
import type {
  AccountRead,
  AccountType,
  AssetClassRead,
  AssetRead,
  CurrencyRead,
  InstitutionRead,
  InstitutionType,
  PortfolioRead,
} from "../api/types";
import { ACCOUNT_TYPE_LABELS, ACCOUNT_TYPES } from "../lib/accountTypes";
import { describeApiError } from "../lib/apiErrors";
import { isFixedIncome, parseRatePercent, rateToPercentText } from "../lib/fixedIncome";
import { formatIsoDate } from "../lib/formatCurrency";
import { BUTTON_CLASS, INPUT_CLASS, LABEL_CLASS, PANEL_CLASS } from "../lib/ui";

interface RegistryData {
  institutions: InstitutionRead[];
  accounts: AccountRead[];
  portfolios: PortfolioRead[];
  assets: AssetRead[];
  currencies: CurrencyRead[];
  assetClasses: AssetClassRead[];
}

type State = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: RegistryData };

const INSTITUTION_TYPES: { value: InstitutionType; label: string }[] = [
  { value: "BROKER", label: "Corretora" },
  { value: "BANK", label: "Banco" },
  { value: "OTHER", label: "Outra" },
];

interface SectionProps {
  title: string;
  formLabel: string;
  canSubmit: boolean;
  /** Nome do item em edição; `null` = o formulário cria um item novo. */
  editingName: string | null;
  onCancelEdit: () => void;
  /** Executa a criação ou a edição; lança em caso de erro. */
  onSubmit: () => Promise<void>;
  children: ReactNode;
  list: ReactNode;
}

/**
 * Um bloco de cadastro: um formulário (que cria, ou edita o item
 * escolhido na lista) + a lista do que já existe.
 */
function Section({ title, formLabel, canSubmit, editingName, onCancelEdit, onSubmit, children, list }: SectionProps) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit();
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={PANEL_CLASS}>
      <h2 className="mb-3 text-[15px] font-semibold tracking-tight text-neutral-100">{title}</h2>
      <form className="space-y-3" onSubmit={handleSubmit} aria-label={formLabel}>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">{children}</div>
        {editingName !== null && (
          <p className="text-xs text-amber-300" data-testid="editing-note">
            Editando: {editingName}
          </p>
        )}
        <div className="flex gap-2">
          <button type="submit" className={BUTTON_CLASS} disabled={submitting || !canSubmit}>
            {submitting ? "Salvando…" : editingName !== null ? "Salvar alterações" : "Adicionar"}
          </button>
          {editingName !== null && (
            <button type="button" className={BUTTON_CLASS} onClick={onCancelEdit} disabled={submitting}>
              Cancelar edição
            </button>
          )}
        </div>
        {error && (
          <p className="text-sm text-red-400" role="alert">
            {error}
          </p>
        )}
      </form>
      <div className="mt-4 text-sm text-neutral-300">{list}</div>
    </div>
  );
}

function EmptyList({ text }: { text: string }) {
  return <p className="text-neutral-500">{text}</p>;
}

const SMALL_BUTTON_CLASS =
  "rounded border border-neutral-700 px-2 py-0.5 text-xs text-neutral-200 hover:bg-neutral-800 disabled:opacity-40";

interface ItemRowProps {
  /** Texto do item e nome usado nos rótulos dos botões. */
  label: string;
  name: string;
  onEdit: () => void;
  /** Exclui no backend; lança em caso de erro (ex.: cadastro em uso). */
  onDelete: () => Promise<void>;
}

/**
 * Uma linha da lista com Editar e Excluir. A exclusão pede uma segunda
 * confirmação na própria linha, e a recusa do backend (cadastro já
 * usado) aparece ali mesmo, com o motivo.
 */
function ItemRow({ label, name, onEdit, onDelete }: ItemRowProps) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    setDeleting(true);
    setError(null);
    try {
      await onDelete();
    } catch (err) {
      setError(describeApiError(err));
      setConfirming(false);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <li className="flex flex-wrap items-center gap-2 py-1">
      <span>{label}</span>
      {confirming ? (
        <>
          <button type="button" className={SMALL_BUTTON_CLASS} onClick={() => void handleDelete()} disabled={deleting}>
            Confirmar exclusão de {name}
          </button>
          <button type="button" className={SMALL_BUTTON_CLASS} onClick={() => setConfirming(false)} disabled={deleting}>
            Manter
          </button>
        </>
      ) : (
        <>
          <button type="button" className={SMALL_BUTTON_CLASS} onClick={onEdit} aria-label={`Editar ${name}`}>
            Editar
          </button>
          <button
            type="button"
            className={SMALL_BUTTON_CLASS}
            onClick={() => {
              setError(null);
              setConfirming(true);
            }}
            aria-label={`Excluir ${name}`}
          >
            Excluir
          </button>
        </>
      )}
      {error && (
        <span className="w-full text-xs text-red-400" role="alert">
          {error}
        </span>
      )}
    </li>
  );
}

type EditTarget = { kind: "institution" | "portfolio" | "account" | "asset"; id: string } | null;

export function Registry() {
  const [state, setState] = useState<State>({ status: "loading" });

  // Depois de cada criação a tela relê tudo do backend.
  const load = useCallback(() => {
    return Promise.all([
      getInstitutions(),
      getAccounts(),
      getPortfolios(),
      getAssets(),
      getCurrencies(),
      getAssetClasses(),
    ])
      .then(([institutions, accounts, portfolios, assets, currencies, assetClasses]) =>
        setState({
          status: "ready",
          data: { institutions, accounts, portfolios, assets, currencies, assetClasses },
        }),
      )
      .catch((err: Error) => setState({ status: "error", message: err.message }));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const [instName, setInstName] = useState("");
  const [instType, setInstType] = useState<InstitutionType>("BROKER");
  const [instCountry, setInstCountry] = useState("BR");

  const [portfolioName, setPortfolioName] = useState("");

  const [accName, setAccName] = useState("");
  const [accInstitution, setAccInstitution] = useState("");
  const [accCurrency, setAccCurrency] = useState("BRL");
  const [accPortfolio, setAccPortfolio] = useState("");
  const [accType, setAccType] = useState<AccountType>("BROKERAGE");

  const [assetTicker, setAssetTicker] = useState("");
  const [assetName, setAssetName] = useState("");
  const [assetClass, setAssetClass] = useState("");
  const [assetCountry, setAssetCountry] = useState("BR");
  const [assetCurrency, setAssetCurrency] = useState("BRL");
  const [assetMaturity, setAssetMaturity] = useState("");
  const [assetRate, setAssetRate] = useState("");

  // Um item em edição por vez: o formulário do bloco dele passa a
  // salvar a alteração em vez de criar.
  const [editing, setEditing] = useState<EditTarget>(null);
  const editingId = (kind: NonNullable<EditTarget>["kind"]) => (editing?.kind === kind ? editing.id : null);

  function clearForm(kind: NonNullable<EditTarget>["kind"]) {
    if (kind === "institution") {
      setInstName("");
      setInstType("BROKER");
      setInstCountry("BR");
    } else if (kind === "portfolio") {
      setPortfolioName("");
    } else if (kind === "account") {
      setAccName("");
      setAccInstitution("");
      setAccCurrency("BRL");
      setAccPortfolio("");
      setAccType("BROKERAGE");
    } else {
      setAssetTicker("");
      setAssetName("");
      setAssetClass("");
      setAssetCountry("BR");
      setAssetCurrency("BRL");
      setAssetMaturity("");
      setAssetRate("");
    }
  }

  /**
   * Entra em edição de um item. Se outro bloco estava em edição, ele é
   * limpo: os valores do item antigo não podem sobrar no formulário
   * como se fossem um cadastro novo.
   */
  function startEdit(target: NonNullable<EditTarget>) {
    if (editing && editing.kind !== target.kind) clearForm(editing.kind);
    setEditing(target);
  }

  function cancelEdit() {
    if (editing) clearForm(editing.kind);
    setEditing(null);
  }

  /** Depois de salvar ou excluir: sai da edição, limpa o bloco e relê tudo. */
  async function finish(kind: NonNullable<EditTarget>["kind"]) {
    if (editing?.kind === kind) setEditing(null);
    clearForm(kind);
    await load();
  }

  if (state.status === "loading") {
    return (
      <p className="text-neutral-400" role="status">
        Carregando…
      </p>
    );
  }
  if (state.status === "error") {
    return (
      <p className="text-red-400" role="alert">
        Não foi possível carregar os cadastros: {state.message}
      </p>
    );
  }

  const { institutions, accounts, portfolios, assets, currencies, assetClasses } = state.data;
  const currencyOptions = currencies.map((currency) => (
    <option key={currency.code} value={currency.code}>
      {currency.code} — {currency.name}
    </option>
  ));

  return (
    <div className="space-y-6">
      <Section
        title="Instituições"
        formLabel="Nova instituição"
        canSubmit={instName.trim() !== "" && instCountry.trim().length === 2}
        editingName={institutions.find((item) => item.id === editingId("institution"))?.name ?? null}
        onCancelEdit={cancelEdit}
        onSubmit={async () => {
          const payload = { name: instName, institution_type: instType, country: instCountry };
          const id = editingId("institution");
          if (id !== null) {
            await updateInstitution(id, payload);
            await finish("institution");
          } else {
            await createInstitution(payload);
            setInstName("");
            await load();
          }
        }}
        list={
          institutions.length === 0 ? (
            <EmptyList text="Nenhuma instituição cadastrada." />
          ) : (
            <ul data-testid="institution-list">
              {institutions.map((institution) => (
                <ItemRow
                  key={institution.id}
                  label={`${institution.name} (${institution.country})`}
                  name={institution.name}
                  onEdit={() => {
                    setInstName(institution.name);
                    setInstType(institution.institution_type);
                    setInstCountry(institution.country);
                    startEdit({ kind: "institution", id: institution.id });
                  }}
                  onDelete={async () => {
                    await deleteInstitution(institution.id);
                    await finish("institution");
                  }}
                />
              ))}
            </ul>
          )
        }
      >
        <div className="col-span-2">
          <label className={LABEL_CLASS} htmlFor="inst-name">
            Nome da instituição
          </label>
          <input
            id="inst-name"
            className={INPUT_CLASS}
            value={instName}
            onChange={(e) => setInstName(e.target.value)}
          />
        </div>
        <div>
          <label className={LABEL_CLASS} htmlFor="inst-type">
            Tipo
          </label>
          <select
            id="inst-type"
            className={INPUT_CLASS}
            value={instType}
            onChange={(e) => setInstType(e.target.value as InstitutionType)}
          >
            {INSTITUTION_TYPES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={LABEL_CLASS} htmlFor="inst-country">
            País (2 letras)
          </label>
          <input
            id="inst-country"
            maxLength={2}
            className={INPUT_CLASS}
            value={instCountry}
            onChange={(e) => setInstCountry(e.target.value)}
          />
        </div>
      </Section>

      <Section
        title="Carteiras"
        formLabel="Nova carteira"
        canSubmit={portfolioName.trim() !== ""}
        editingName={portfolios.find((item) => item.id === editingId("portfolio"))?.name ?? null}
        onCancelEdit={cancelEdit}
        onSubmit={async () => {
          const id = editingId("portfolio");
          if (id !== null) {
            await updatePortfolio(id, { name: portfolioName });
            await finish("portfolio");
            return;
          }
          await createPortfolio({ name: portfolioName });
          setPortfolioName("");
          await load();
        }}
        list={
          portfolios.length === 0 ? (
            <EmptyList text="Nenhuma carteira cadastrada." />
          ) : (
            <ul data-testid="portfolio-list">
              {portfolios.map((portfolio) => (
                <ItemRow
                  key={portfolio.id}
                  label={portfolio.name}
                  name={portfolio.name}
                  onEdit={() => {
                    setPortfolioName(portfolio.name);
                    startEdit({ kind: "portfolio", id: portfolio.id });
                  }}
                  onDelete={async () => {
                    await deletePortfolio(portfolio.id);
                    await finish("portfolio");
                  }}
                />
              ))}
            </ul>
          )
        }
      >
        <div className="col-span-2">
          <label className={LABEL_CLASS} htmlFor="portfolio-name">
            Nome da carteira
          </label>
          <input
            id="portfolio-name"
            className={INPUT_CLASS}
            value={portfolioName}
            onChange={(e) => setPortfolioName(e.target.value)}
          />
        </div>
      </Section>

      <Section
        title="Contas"
        formLabel="Nova conta"
        canSubmit={accName.trim() !== "" && accInstitution !== ""}
        editingName={accounts.find((item) => item.id === editingId("account"))?.name ?? null}
        onCancelEdit={cancelEdit}
        onSubmit={async () => {
          const payload = {
            name: accName,
            institution_id: accInstitution,
            currency_code: accCurrency,
            account_type: accType,
            // Carteira só existe no livro de investimentos.
            ...(accType === "BROKERAGE" && accPortfolio !== "" ? { portfolio_id: accPortfolio } : {}),
          };
          const id = editingId("account");
          if (id !== null) {
            await updateAccount(id, payload);
            await finish("account");
          } else {
            await createAccount(payload);
            setAccName("");
            await load();
          }
        }}
        list={
          accounts.length === 0 ? (
            <EmptyList text="Nenhuma conta cadastrada." />
          ) : (
            <ul data-testid="account-list">
              {accounts.map((account) => (
                <ItemRow
                  key={account.id}
                  label={`${account.name} — ${account.institution_name} (${account.currency_code}) · ${ACCOUNT_TYPE_LABELS[account.account_type]}`}
                  name={account.name}
                  onEdit={() => {
                    setAccName(account.name);
                    setAccInstitution(account.institution_id);
                    setAccCurrency(account.currency_code);
                    setAccPortfolio(account.portfolio_id ?? "");
                    setAccType(account.account_type);
                    startEdit({ kind: "account", id: account.id });
                  }}
                  onDelete={async () => {
                    await deleteAccount(account.id);
                    await finish("account");
                  }}
                />
              ))}
            </ul>
          )
        }
      >
        <div className="col-span-2">
          <label className={LABEL_CLASS} htmlFor="acc-name">
            Nome da conta
          </label>
          <input id="acc-name" className={INPUT_CLASS} value={accName} onChange={(e) => setAccName(e.target.value)} />
        </div>
        <div>
          <label className={LABEL_CLASS} htmlFor="acc-institution">
            Instituição
          </label>
          <select
            id="acc-institution"
            className={INPUT_CLASS}
            value={accInstitution}
            onChange={(e) => setAccInstitution(e.target.value)}
          >
            <option value="">Selecione…</option>
            {institutions.map((institution) => (
              <option key={institution.id} value={institution.id}>
                {institution.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={LABEL_CLASS} htmlFor="acc-currency">
            Moeda da conta
          </label>
          <select
            id="acc-currency"
            className={INPUT_CLASS}
            value={accCurrency}
            onChange={(e) => setAccCurrency(e.target.value)}
          >
            {currencyOptions}
          </select>
        </div>
        <div>
          <label className={LABEL_CLASS} htmlFor="acc-type">
            Tipo da conta
          </label>
          <select
            id="acc-type"
            className={INPUT_CLASS}
            value={accType}
            onChange={(e) => setAccType(e.target.value as AccountType)}
          >
            {ACCOUNT_TYPES.map((type) => (
              <option key={type} value={type}>
                {ACCOUNT_TYPE_LABELS[type]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={LABEL_CLASS} htmlFor="acc-portfolio">
            Carteira (opcional)
          </label>
          <select
            id="acc-portfolio"
            className={INPUT_CLASS}
            value={accType === "BROKERAGE" ? accPortfolio : ""}
            disabled={accType !== "BROKERAGE"}
            onChange={(e) => setAccPortfolio(e.target.value)}
          >
            <option value="">Sem carteira</option>
            {portfolios.map((portfolio) => (
              <option key={portfolio.id} value={portfolio.id}>
                {portfolio.name}
              </option>
            ))}
          </select>
        </div>
      </Section>

      <Section
        title="Ativos"
        formLabel="Novo ativo"
        canSubmit={
          assetTicker.trim() !== "" &&
          assetName.trim() !== "" &&
          assetClass !== "" &&
          assetCountry.trim().length === 2 &&
          !(isFixedIncome(assetClass) && parseRatePercent(assetRate) === "invalid")
        }
        editingName={assets.find((item) => item.id === editingId("asset"))?.ticker ?? null}
        onCancelEdit={cancelEdit}
        onSubmit={async () => {
          const payload = {
            ticker: assetTicker,
            name: assetName,
            asset_class_code: assetClass,
            country: assetCountry,
            currency_code: assetCurrency,
            // Só renda fixa vence; trocar para outra classe apaga os dois.
            maturity_date: isFixedIncome(assetClass) && assetMaturity !== "" ? assetMaturity : null,
            annual_rate: isFixedIncome(assetClass) ? (parseRatePercent(assetRate) as string | null) : null,
          };
          const id = editingId("asset");
          if (id !== null) {
            await updateAsset(id, payload);
            await finish("asset");
          } else {
            await createAsset(payload);
            setAssetTicker("");
            setAssetName("");
            setAssetMaturity("");
            setAssetRate("");
            await load();
          }
        }}
        list={
          assets.length === 0 ? (
            <EmptyList text="Nenhum ativo cadastrado." />
          ) : (
            <ul data-testid="asset-list">
              {assets.map((asset) => (
                <ItemRow
                  key={asset.id}
                  label={`${asset.ticker} — ${asset.name} (${asset.country}, ${asset.currency_code})${
                    asset.maturity_date ? ` · vence em ${formatIsoDate(asset.maturity_date)}` : ""
                  }`}
                  name={asset.ticker}
                  onEdit={() => {
                    setAssetTicker(asset.ticker);
                    setAssetName(asset.name);
                    setAssetClass(asset.asset_class_code);
                    setAssetCountry(asset.country);
                    setAssetCurrency(asset.currency_code);
                    setAssetMaturity(asset.maturity_date ?? "");
                    setAssetRate(rateToPercentText(asset.annual_rate));
                    startEdit({ kind: "asset", id: asset.id });
                  }}
                  onDelete={async () => {
                    await deleteAsset(asset.id);
                    await finish("asset");
                  }}
                />
              ))}
            </ul>
          )
        }
      >
        <div>
          <label className={LABEL_CLASS} htmlFor="asset-ticker">
            Ticker
          </label>
          <input
            id="asset-ticker"
            className={INPUT_CLASS}
            value={assetTicker}
            onChange={(e) => setAssetTicker(e.target.value)}
          />
        </div>
        <div>
          <label className={LABEL_CLASS} htmlFor="asset-name">
            Nome do ativo
          </label>
          <input
            id="asset-name"
            className={INPUT_CLASS}
            value={assetName}
            onChange={(e) => setAssetName(e.target.value)}
          />
        </div>
        <div>
          <label className={LABEL_CLASS} htmlFor="asset-class">
            Classe
          </label>
          <select
            id="asset-class"
            className={INPUT_CLASS}
            value={assetClass}
            onChange={(e) => setAssetClass(e.target.value)}
          >
            <option value="">Selecione…</option>
            {assetClasses.map((item) => (
              <option key={item.code} value={item.code}>
                {item.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={LABEL_CLASS} htmlFor="asset-country">
            País do ativo (2 letras)
          </label>
          <input
            id="asset-country"
            maxLength={2}
            className={INPUT_CLASS}
            value={assetCountry}
            onChange={(e) => setAssetCountry(e.target.value)}
          />
        </div>
        <div>
          <label className={LABEL_CLASS} htmlFor="asset-currency">
            Moeda do ativo
          </label>
          <select
            id="asset-currency"
            className={INPUT_CLASS}
            value={assetCurrency}
            onChange={(e) => setAssetCurrency(e.target.value)}
          >
            {currencyOptions}
          </select>
          <p className="mt-1 text-xs text-neutral-500">Toda operação com este ativo terá de estar nesta moeda.</p>
        </div>
        {isFixedIncome(assetClass) && (
          <>
            <div>
              <label className={LABEL_CLASS} htmlFor="asset-maturity">
                Vencimento (opcional)
              </label>
              <input
                id="asset-maturity"
                type="date"
                className={INPUT_CLASS}
                value={assetMaturity}
                onChange={(e) => setAssetMaturity(e.target.value)}
              />
              <p className="mt-1 text-xs text-neutral-500">Aparece na agenda da Visão geral.</p>
            </div>
            <div>
              <label className={LABEL_CLASS} htmlFor="asset-rate">
                Taxa ao ano, em % (opcional)
              </label>
              <input
                id="asset-rate"
                inputMode="decimal"
                placeholder="3,85"
                className={INPUT_CLASS}
                value={assetRate}
                aria-invalid={parseRatePercent(assetRate) === "invalid"}
                onChange={(e) => setAssetRate(e.target.value)}
              />
              {parseRatePercent(assetRate) === "invalid" && (
                <p className="mt-1 text-xs text-red-400" role="alert">
                  Use um número entre 0 e 100, como 3,85.
                </p>
              )}
            </div>
          </>
        )}
      </Section>
    </div>
  );
}
