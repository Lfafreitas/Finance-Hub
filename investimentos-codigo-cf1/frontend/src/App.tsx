import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

import type { ReactNode } from "react";

import type { CashflowEntryFilters } from "./api/cashflowTypes";
import { currentMonth, monthRange } from "./lib/cashflow";
import { CashCategories } from "./pages/cash/CashCategories";
import { CashEntries } from "./pages/cash/CashEntries";
import { CashImport } from "./pages/cash/CashImport";
import { CashReview } from "./pages/cash/CashReview";
import { CashRules } from "./pages/cash/CashRules";
import { CashSummary } from "./pages/cash/CashSummary";
import { Analyses } from "./pages/Analyses";
import { AlertBanner } from "./components/alerts/AlertBanner";
import { AppIntro } from "./components/AppIntro";
import { BackendStatus } from "./components/BackendStatus";
import { PrivacyToggle } from "./components/PrivacyToggle";
import type { SidebarGroup } from "./components/desktop/Sidebar";
import type { SidebarIconName } from "./components/desktop/Sidebar";
import { Sidebar, SidebarIcon } from "./components/desktop/Sidebar";
import { isPrivate, setPrivate, subscribePrivacy } from "./lib/privacy";
import { PAGE_TITLE_CLASS } from "./lib/ui";
import { navigate } from "./lib/motion";
import type { NavDirection } from "./lib/motion";
import { getAlerts } from "./api/insights";
import { CompactBar } from "./components/mobile/CompactBar";
import { ChartIcon, HomeIcon, MoreIcon, NewsIcon, WalletIcon } from "./components/mobile/icons";
import type { MoreGroup } from "./components/mobile/MoreMenu";
import { MoreMenu } from "./components/mobile/MoreMenu";
import { TabBar } from "./components/mobile/TabBar";
import { usePullToRefresh } from "./components/mobile/usePullToRefresh";
import { Dashboard, type DashboardTarget } from "./pages/Dashboard";
import { Import } from "./pages/Import";
import { Insights } from "./pages/Insights";
import { Prices } from "./pages/Prices";
import { Reconciliation } from "./pages/Reconciliation";
import { Notes } from "./pages/Notes";
import { Registry } from "./pages/Registry";
import { SecurityPanel } from "./components/security/SecurityPanel";
import { Transactions } from "./pages/Transactions";

// Navegação por estado local (decisão D da Fase 11): sem URL própria e
// sem `react-router-dom`. Dois níveis: a área (um livro, ou os
// cadastros que os dois usam) e a tela dentro dela.
type Area = "investments" | "cash" | "notes" | "registry" | "security";
type InvestmentPage = "dashboard" | "analyses" | "insights" | "transactions" | "import" | "prices" | "reconciliation";
type CashPage = "summary" | "review" | "entries" | "import" | "categories" | "rules";

const AREAS: { id: Area; label: string }[] = [
  { id: "investments", label: "Investimentos" },
  { id: "cash", label: "Controle financeiro" },
  { id: "notes", label: "Anotações" },
  { id: "registry", label: "Cadastros" },
  { id: "security", label: "Segurança" },
];

const INVESTMENT_PAGES: { id: InvestmentPage; label: string }[] = [
  { id: "dashboard", label: "Visão geral" },
  { id: "analyses", label: "Análises" },
  { id: "insights", label: "Jornal" },
  { id: "transactions", label: "Lançamentos" },
  { id: "import", label: "Importar" },
  { id: "prices", label: "Cotações" },
  { id: "reconciliation", label: "Reconciliação" },
];

const INVESTMENT_ICONS: Record<InvestmentPage, SidebarIconName> = {
  dashboard: "overview",
  analyses: "analyses",
  insights: "news",
  transactions: "list",
  import: "import",
  prices: "prices",
  reconciliation: "reconcile",
};

const CASH_ICONS: Record<CashPage, SidebarIconName> = {
  summary: "wallet",
  review: "classify",
  entries: "list",
  import: "import",
  categories: "folder",
  rules: "rules",
};

const CASH_PAGES: { id: CashPage; label: string }[] = [
  { id: "summary", label: "Resumo" },
  { id: "review", label: "Classificar" },
  { id: "entries", label: "Lançamentos" },
  { id: "import", label: "Importar extrato" },
  { id: "categories", label: "Categorias" },
  { id: "rules", label: "Regras" },
];

/** Moldura comum das telas de trabalho (o Dashboard tem a sua própria). */
function PageFrame({ title, wide = false, children }: { title?: string; wide?: boolean; children: ReactNode }) {
  return (
    <div className="px-4 pb-16 pt-1 md:px-6 md:pt-8">
      <div className={`mx-auto ${wide ? "max-w-7xl" : "max-w-6xl"}`}>
        {title && <h1 className={PAGE_TITLE_CLASS}>{title}</h1>}
        {children}
      </div>
    </div>
  );
}

type MobileTab = "home" | "analyses" | "news" | "cash" | "more";
const TAB_PAGES: Partial<Record<MobileTab, InvestmentPage>> = {
  home: "dashboard",
  analyses: "analyses",
  news: "insights",
};

function mobileTitleOf(area: Area, investmentPage: InvestmentPage, cashPage: CashPage): string {
  if (area === "registry") return "Cadastros";
  if (area === "notes") return "Anotações";
  if (area === "security") return "Segurança";
  if (area === "cash") return CASH_PAGES.find((p) => p.id === cashPage)?.label ?? "Caixa";
  if (investmentPage === "dashboard") return "Visão geral";
  if (investmentPage === "insights") return "Jornal";
  return INVESTMENT_PAGES.find((p) => p.id === investmentPage)?.label ?? "";
}

/** Alertas não lidos (para o número na aba Jornal). */
function useUnreadAlerts(): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    const load = () => {
      getAlerts(7)
        .then((index) => setCount(index?.unread_count ?? 0))
        .catch(() => setCount(0));
    };
    load();
    window.addEventListener("alerts-changed", load);
    return () => window.removeEventListener("alerts-changed", load);
  }, []);
  return count;
}

function App() {
  // Modo privacidade: ao trocar, o App redesenha e todo valor em dinheiro
  // (formatado em lib/formatCurrency) passa a sair escondido.
  const hidden = useSyncExternalStore(subscribePrivacy, isPrivate);
  const [area, setArea] = useState<Area>("investments");
  // Cada área lembra a tela em que estava.
  const [investmentPage, setInvestmentPage] = useState<InvestmentPage>("dashboard");
  const [cashPage, setCashPage] = useState<CashPage>("summary");
  // Celular: a aba "Mais" aberta (lista) e a chave para "puxar para atualizar".
  const [moreOpen, setMoreOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);
  const pull = usePullToRefresh(refresh);
  const unreadAlerts = useUnreadAlerts();
  // Filtros com que a lista de lançamentos de caixa abre. A `key` muda
  // junto, para a tela ser remontada com eles.
  const [entryFilters, setEntryFilters] = useState<{
    key: number;
    filters: CashflowEntryFilters;
  }>({
    key: 0,
    filters: {},
  });

  // Conta com que a tela de lançamentos de investimento abre (vinda do Dashboard).
  const [transactionsAccount, setTransactionsAccount] = useState<{
    key: number;
    id: string;
  }>({ key: 0, id: "" });

  function openFromDashboard(target: DashboardTarget) {
    if (target.page === "review") {
      setArea("cash");
      setCashPage("review");
    } else if (target.page === "prices") {
      setInvestmentPage("prices");
    } else if (target.page === "insights") {
      setInvestmentPage("insights");
    } else if (target.page === "registry") {
      setArea("registry");
    } else {
      setTransactionsAccount((current) => ({
        key: current.key + 1,
        id: target.accountId,
      }));
      setInvestmentPage("transactions");
    }
  }

  function openUnclassifiedOfMonth(month: string) {
    const range = monthRange(month) ?? monthRange(currentMonth());
    setEntryFilters((current) => ({
      key: current.key + 1,
      filters: { ...(range ?? {}), nature: "UNCLASSIFIED" },
    }));
    setCashPage("entries");
  }

  // --- Celular: abas embaixo -------------------------------------------------
  const activeTab: MobileTab = moreOpen
    ? "more"
    : area === "cash"
      ? "cash"
      : area === "investments" && investmentPage === "dashboard"
        ? "home"
        : area === "investments" && investmentPage === "analyses"
          ? "analyses"
          : area === "investments" && investmentPage === "insights"
            ? "news"
            : "more";

  function selectTab(tab: string, direction: NavDirection = "fade") {
    navigate(() => {
      window.scrollTo({ top: 0 });
      setMoreOpen(tab === "more");
      if (tab === "cash") setArea("cash");
      const page = TAB_PAGES[tab as MobileTab];
      if (page) {
        setArea("investments");
        setInvestmentPage(page);
      }
    }, direction);
  }

  function openFromMore(next: () => void) {
    navigate(() => {
      window.scrollTo({ top: 0 });
      next();
      setMoreOpen(false);
    }, "push");
  }

  const mobileTitle = moreOpen ? "Mais" : mobileTitleOf(area, investmentPage, cashPage);
  const moreGroups: MoreGroup[] = [
    {
      title: "Investimentos",
      items: (["transactions", "import", "prices", "reconciliation"] as const).map((id) => ({
        id,
        label: INVESTMENT_PAGES.find((p) => p.id === id)!.label,
        onSelect: () =>
          openFromMore(() => {
            setArea("investments");
            setInvestmentPage(id);
          }),
      })),
    },
    {
      title: "Geral",
      items: [
        { id: "notes", label: "Anotações", onSelect: () => openFromMore(() => setArea("notes")) },
        { id: "registry", label: "Cadastros", onSelect: () => openFromMore(() => setArea("registry")) },
        { id: "security", label: "Segurança", onSelect: () => openFromMore(() => setArea("security")) },
        {
          id: "privacy",
          label: hidden ? "Mostrar valores" : "Esconder valores",
          detail: hidden ? "escondidos" : "à mostra",
          onSelect: () => setPrivate(!isPrivate()),
        },
      ],
    },
  ];

  // --- Computador: barra lateral com todas as telas ---------------------------
  const openPage = (nextArea: Area, page?: string) =>
    navigate(() => {
      window.scrollTo({ top: 0 });
      setArea(nextArea);
      if (nextArea === "investments" && page) setInvestmentPage(page as InvestmentPage);
      if (nextArea === "cash" && page) setCashPage(page as CashPage);
    });
  const sidebarGroups: SidebarGroup[] = [
    {
      id: "investments",
      title: "Investimentos",
      items: INVESTMENT_PAGES.map((p) => ({
        id: p.id,
        label: p.label,
        icon: <SidebarIcon name={INVESTMENT_ICONS[p.id]} />,
        active: area === "investments" && investmentPage === p.id,
        badge: p.id === "insights" ? unreadAlerts : undefined,
        onSelect: () => openPage("investments", p.id),
      })),
    },
    {
      id: "cash",
      title: "Controle financeiro",
      items: CASH_PAGES.map((p) => ({
        id: p.id,
        label: p.label,
        icon: <SidebarIcon name={CASH_ICONS[p.id]} />,
        active: area === "cash" && cashPage === p.id,
        onSelect: () => openPage("cash", p.id),
      })),
    },
    {
      id: "general",
      title: "Geral",
      items: (["notes", "registry", "security"] as const).map((id) => ({
        id,
        label: AREAS.find((a) => a.id === id)!.label,
        icon: <SidebarIcon name={id} />,
        active: area === id,
        onSelect: () => openPage(id),
      })),
    },
  ];

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 md:flex">
      <AppIntro />
      <Sidebar groups={sidebarGroups} hidden={hidden} />
      <div className="min-w-0 flex-1">
        <BackendStatus />
        <AlertBanner
          onOpen={() => {
            setArea("investments");
            setInvestmentPage("insights");
          }}
        />
        {/* Celular: barra compacta (título ao rolar, "‹ Mais" nas telas que vêm de lá). */}
        <CompactBar
          title={mobileTitle}
          back={
            !moreOpen && activeTab === "more" ? { label: "Mais", onBack: () => selectTab("more", "pop") } : undefined
          }
          trailing={<PrivacyToggle hidden={hidden} />}
        />
        {pull > 0 && (
          <div className="flex justify-center md:hidden" style={{ height: pull * 48 }} aria-hidden="true">
            <span
              className="mt-2 h-6 w-6 rounded-full border-2 border-neutral-600 border-t-sky-400"
              style={{ transform: `rotate(${pull * 270}deg)`, opacity: pull }}
            />
          </div>
        )}
        {area === "cash" && !moreOpen && (
          <nav className="overflow-x-auto px-4 pb-1 pt-1 md:hidden" aria-label="Telas do caixa">
            <div className="flex w-max gap-2">
              {CASH_PAGES.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-current={cashPage === item.id ? "page" : undefined}
                  onClick={() => navigate(() => setCashPage(item.id))}
                  className={`h-9 whitespace-nowrap rounded-full px-4 text-[15px] ${
                    cashPage === item.id
                      ? "bg-neutral-100 font-medium text-neutral-950"
                      : "bg-neutral-900 text-neutral-300"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </nav>
        )}

        <div key={refreshKey} className="pb-[calc(84px+env(safe-area-inset-bottom))] md:pb-0">
          {moreOpen && (
            <div className="md:hidden">
              <MoreMenu groups={moreGroups} />
            </div>
          )}
          <div className={moreOpen ? "hidden md:block" : undefined}>
            {area === "investments" && (
              <>
                {investmentPage === "dashboard" && <Dashboard onOpen={openFromDashboard} />}
                {investmentPage === "analyses" && (
                  <PageFrame title="Análises da carteira">
                    <Analyses />
                  </PageFrame>
                )}
                {investmentPage === "insights" && (
                  <PageFrame>
                    <Insights />
                  </PageFrame>
                )}
                {investmentPage === "transactions" && (
                  <PageFrame title="Lançamentos">
                    <Transactions key={transactionsAccount.key} initialAccountId={transactionsAccount.id} />
                  </PageFrame>
                )}
                {investmentPage === "import" && (
                  <PageFrame title="Importar">
                    <Import />
                  </PageFrame>
                )}
                {investmentPage === "prices" && (
                  <PageFrame title="Cotações">
                    <Prices />
                  </PageFrame>
                )}
                {investmentPage === "reconciliation" && (
                  <PageFrame title="Reconciliação">
                    <Reconciliation />
                  </PageFrame>
                )}
              </>
            )}

            {area === "cash" && (
              <>
                {cashPage === "summary" && (
                  <PageFrame title="Resumo do controle financeiro">
                    <CashSummary
                      onOpenUnclassified={openUnclassifiedOfMonth}
                      onOpenReview={() => setCashPage("review")}
                    />
                  </PageFrame>
                )}
                {cashPage === "review" && (
                  <PageFrame title="Classificar o que falta">
                    <CashReview />
                  </PageFrame>
                )}
                {cashPage === "entries" && (
                  <PageFrame title="Lançamentos de caixa" wide>
                    <CashEntries key={entryFilters.key} initialFilters={entryFilters.filters} />
                  </PageFrame>
                )}
                {cashPage === "import" && (
                  <PageFrame title="Importar extrato ou fatura" wide>
                    <CashImport />
                  </PageFrame>
                )}
                {cashPage === "categories" && (
                  <PageFrame title="Categorias e tags">
                    <CashCategories />
                  </PageFrame>
                )}
                {cashPage === "rules" && (
                  <PageFrame title="Regras de classificação" wide>
                    <CashRules />
                  </PageFrame>
                )}
              </>
            )}

            {area === "notes" && (
              <PageFrame title="Anotações">
                <Notes />
              </PageFrame>
            )}

            {area === "registry" && (
              <PageFrame title="Cadastros">
                <Registry />
              </PageFrame>
            )}

            {area === "security" && (
              <PageFrame title="Segurança do acesso pelo celular">
                <SecurityPanel />
              </PageFrame>
            )}
          </div>
        </div>
      </div>
      <TabBar
        tabs={[
          { id: "home", label: "Início", icon: HomeIcon },
          { id: "analyses", label: "Análises", icon: ChartIcon },
          { id: "news", label: "Jornal", icon: NewsIcon, badge: unreadAlerts },
          { id: "cash", label: "Caixa", icon: WalletIcon },
          { id: "more", label: "Mais", icon: MoreIcon },
        ]}
        active={activeTab}
        onSelect={selectTab}
      />
    </div>
  );
}

export default App;
