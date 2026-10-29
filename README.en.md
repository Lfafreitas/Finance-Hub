<p align="center">
  <img src="docs/hero.en.svg" alt="Finance Hub: your money, explained, in one place" width="100%">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/PostgreSQL-SQLAlchemy%202%20%2B%20Alembic-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black" alt="React 19">
  <img src="https://img.shields.io/badge/TypeScript-6-3178C6?logo=typescript&logoColor=white" alt="TypeScript">
  <img src="https://img.shields.io/badge/Tailwind-4-06B6D4?logo=tailwindcss&logoColor=white" alt="Tailwind">
  <img src="https://img.shields.io/badge/tests-2%2C111%20passing-2EA043" alt="2,111 tests passing">
</p>

<p align="center">
  <a href="README.md">Português</a> · <b>English</b>
</p>

<p align="center">
  <img src="docs/gifs/tour.gif" alt="Dashboard tour: overview, history, allocation, analytics, briefing and spending control" width="100%">
</p>

> [!NOTE]
> All values, accounts and assets in the images and animations are **fictitious**. They come from the
> [`seed_demo.py`](investimentos-codigo-cf1/backend/scripts/seed_demo.py) script, which loads a demo
> portfolio into an empty database. The app's interface is in Brazilian Portuguese.

---

## ⚡ In 30 seconds

**Finance Hub** is a web app that runs on your own computer and brings together, in one place, an
investment portfolio (in Brazil and abroad), the bank account and the credit card statement.

- 💵 **Reais and dollars side by side.** Each currency has its own result, and nothing is added up
  through a hidden exchange-rate conversion.
- 🧾 **Imports bank and card statements**, including the PDF credit card statement, which is checked
  to the cent before anything is saved.
- 📈 **Benchmarks the portfolio against the CDI (Brazil's interbank rate) and the S&P 500**, using the
  same deposits on the same dates.
- 📰 **Every business day, a portfolio briefing** written by a scheduled Claude task, with the news
  that affects your holdings.
- 🔒 **Your data stays on your machine.** The phone connects through a private network and opens only
  with Face ID.

## 🤔 Questions it answers

| Question | Where the answer shows up |
|---|---|
| How much do I really have, and how much is invested, emergency fund or idle cash? | [Overview](#1-net-worth-overview) |
| Did I do better than just leaving it in the CDI? | [History and benchmark](#2-history-and-benchmark-comparison) |
| How far is my portfolio from the plan? | [Allocation vs. target](#3-calendar-income-and-allocation-vs-target) |
| Where did this month's salary go? | [Spending control](#8-spending-control) |
| How many months does my emergency fund cover? | [Cash, reserve and savings](#4-cash-reserve-and-savings) |
| What if the market drops before December? | [Scenarios](#6-analytics-scenarios-and-contribution-pace) |
| Which of today's news affects what I own? | [Portfolio briefing](#7-portfolio-briefing) |

---

## 🧭 Contents

- [By the numbers](#-by-the-numbers)
- [Features](#-features)
- [Architecture](#-architecture)
- [Engineering decisions](#-engineering-decisions)
- [Calculation engines](#-calculation-engines)
- [Statement imports](#-statement-imports)
- [Claude integration](#-claude-integration)
- [Security and privacy](#-security-and-privacy)
- [API](#-api)
- [Repository layout](#-repository-layout)
- [Running it](#-running-it)
- [Tests and quality](#-tests-and-quality)
- [FAQ](#-faq)
- [Known limitations](#-known-limitations)

---

## 📊 By the numbers

| | |
|---|---|
| Application code | **~38k lines** (backend 19.1k · frontend 17.1k · launcher and widget 1.9k) |
| Test code | **~31k lines** (backend 20.6k · frontend 10.2k) |
| Automated tests | **2,111 passing** (backend 1,375 · frontend 645 · launcher 69 · widget 22) |
| REST endpoints | **113** |
| Database | **22 tables** · **18 Alembic migrations**, with integrity triggers |
| Import formats | broker CSV, XLSX and OFX · bank CSV and OFX · card CSV, OFX and **PDF** |

### The problem

If you invest in Brazil and abroad, your financial life ends up scattered: the US broker shows
dollars, the Brazilian broker shows reais, the bank shows the statement and the card shows the bill.
None of them answers the questions that matter. Off-the-shelf aggregators solve part of it, but they
ask for your bank password and usually add reais and dollars together through a conversion that hides
the exchange rate.

### The solution

A **local**, single-user web app that keeps two ledgers:

| Ledger | What it records | What it delivers |
|---|---|---|
| 📈 **Investments** | buys, sells, income, transfers and corporate actions, per broker and currency | position and average cost, returns (XIRR, TWR, CAGR), CDI and S&P 500 benchmarks, scenarios, concentration, allocation vs. target and maturities |
| 💳 **Spending control** | bank and card statements imported from the bank | income × spending, spending by category, savings rate, emergency-fund coverage and automatically matched transfers |

On top of both ledgers, a scheduled **Claude** task reads a snapshot of the portfolio and writes a
**portfolio briefing** every business day, plus hourly alerts when something serious comes up.

### What sets it apart

- **Currencies never add up.** Reais and dollars sit side by side, each with its own result.
- **Financial facts are immutable.** Mistakes are fixed with a reversal plus a new entry, and the
  database enforces it with triggers.
- **Imports never write blindly.** Every file goes through an HMAC-signed preview, and the commit
  saves exactly what was shown, all or nothing.
- **Your data stays on your machine.** The backend only listens on `127.0.0.1`. The only things that
  leave the computer are ticker symbols, to fetch quotes, and the public CDI series.
- **Phone access with Face ID**, over a private Tailscale network, with passkeys (WebAuthn) and no
  port open to the internet.

---

## ✨ Features

<table>
  <tr>
    <td width="33%" valign="top"><b>📈 Investments</b><br><br>
      Net worth per currency<br>
      History and CDI / S&P 500 benchmark<br>
      Maturities, income and target allocation<br>
      Indicators, risk and scenarios<br>
      Automatic and manual quotes<br>
      Cross-source reconciliation
    </td>
    <td width="33%" valign="top"><b>💳 Spending control</b><br><br>
      Income × spending, month by month<br>
      Spending by category and subcategory<br>
      Emergency fund and savings rate<br>
      Statement imports (CSV, OFX, PDF)<br>
      Classification rules<br>
      Transfers matched automatically
    </td>
    <td width="33%" valign="top"><b>🧰 Around it</b><br><br>
      Daily briefing and alerts from Claude<br>
      Dyslexia-friendly reading and notes<br>
      Privacy mode<br>
      Phone app with Face ID<br>
      Desktop widget<br>
      One-click launcher<br>
      Drop-in "Entrada" import folder
    </td>
  </tr>
</table>

### 📈 Investments

#### 1. Net worth overview

![Net worth per currency](docs/screenshots/visao-geral.png)

Net worth across all accounts, split by currency and broken down into equities, fixed income,
emergency fund and cash. Below it is Claude's reading of the portfolio: what is fine, what needs
attention, the risks and what could improve. It is a reading of the numbers, never a buy
recommendation.

#### 2. History and benchmark comparison

![Net worth history and CDI comparison](docs/screenshots/evolucao-e-referencia.png)

- **Net worth history**, with total net worth and amount invested, over 1M, 3M, 6M, 1Y or all time.
- **Benchmark comparison:** what the **CDI** would have returned (in reais) and what **SPY** would
  have returned (in dollars) **with the same deposits on the same dates**. The question stops being
  "how much did I make?" and becomes "was it worth more than the alternative?".
- **Interactive charts:** hovering over the line (or dragging a finger, or using the arrow keys)
  makes the big number at the top show that day's value and the change up to it, like the iPhone
  Stocks app. On bar charts, the item under the pointer lights up and the others dim.

#### 3. Calendar, income and allocation vs. target

![Fixed-income maturities and allocation by class vs. target](docs/screenshots/agenda-e-alocacao.png)

- Fixed-income maturities, with the estimated value at maturity using compound interest.
- Income received.
- **Target allocation by asset class and currency:** you set the target and the panel shows how far
  each class is from it, in percentage points and in money.

#### 4. Cash, reserve and savings

![Emergency fund in months of spending and savings rate](docs/screenshots/caixa-e-reserva.png)

Spending control feeds the investment dashboard: monthly income and spending, how many months of
average spending the emergency fund covers (with the usual 3- and 6-month markers), the savings rate
and how much was actually invested. The Cash card, with monthly income and spending, sits next to
Claude's reading on the overview.

#### 5. Portfolio indicators

![Per-asset indicators](docs/screenshots/indicadores.png)

Computed per currency:

- **Portfolio:** largest position, combined weight of the top 3 and diversification (effective
  number of assets, `1/HHI`).
- **Performance:** how many assets are positive, the best and the worst, and the current mix
  simulated over the last 12 months.
- **Per asset:** weight, result, contribution in percentage points, and returns for the session,
  1 month, year to date and 12 months.
- **Risk:** annualized volatility, maximum drawdown and 52-week range.

#### 6. Analytics: scenarios and contribution pace

![Pessimistic, realistic and optimistic scenarios](docs/screenshots/analises-cenarios.png)

- **Scenarios up to a date:** a lognormal portfolio model, with volatility and correlation measured
  on each asset's real history when there is enough data (60 or more daily returns). It shows the
  10th, 50th and 90th percentiles and the probability of ending below today's value.
- **Contribution pace:** how much came in each month and the projection to December at three paces:
  year average, last 3 months and current month.

#### 7. Portfolio briefing

![Portfolio briefing written by Claude](docs/screenshots/jornal-da-carteira.png)

The day's edition, written by the scheduled Claude task:

- a market ticker strip, a headline with a lead paragraph and "What to watch";
- ideas **to research**, each with thesis, risks and sources;
- the companies behind the ETFs you hold (look-through);
- an "Ask Claude" button that opens a conversation with the portfolio context already loaded;
- **adjustable reading**, designed with dyslexia in mind too: Atkinson Hyperlegible, Lexend and
  OpenDyslexic fonts, text size, letter and line spacing, column width and a low-contrast "paper"
  background;
- **selecting a passage** opens a bar with Highlight, Note, Copy and Ask Claude;
- **Other reading:** you register the sites and papers you follow, and the daily task brings what is
  new in each one, summarized and tied to the portfolio.

<table>
  <tr>
    <td width="50%"><img src="docs/screenshots/leitura-ajustes.png" alt="Reading settings: OpenDyslexic font and paper background" width="100%"></td>
    <td width="50%"><img src="docs/screenshots/leitura-selecao.png" alt="Selected passage with Highlight, Note, Copy and Ask" width="100%"></td>
  </tr>
</table>

### 💳 Spending control

#### 8. Spending control

![Spending control summary](docs/screenshots/controle-financeiro-resumo.png)

- Income, spending, surplus, amount invested and emergency-fund balance for the month.
- Income × spending over the last 6 months.
- "Where the money went": spending by category and subcategory.
- Investing and moving money between your own accounts **do not count as spending**. Neither does
  paying the card bill: it is matched automatically with the payment received on the card.

#### 9. PDF statement import, with reconciliation

<p align="center">
  <img src="docs/gifs/importacao.gif" alt="Importing a PDF card statement: preview, check against the summary and import" width="100%">
</p>

The closed credit card statement in PDF is parsed, and the system checks the sum of purchases and
payments against the statement's own summary **before saving anything**. A one-cent difference
rejects the whole file. The preview shows the rule that would classify each line and its status (new,
duplicate or error). Nothing is saved until you click "Import", and then everything is saved at once.

#### 10. Classification rules

![Classification rules](docs/screenshots/regras-de-classificacao.png)

"When the description contains X, classify it as spending in category Y." Rules run in priority
order against the cleaned description (no accents, installment numbers or payment intermediaries).
You can preview what would change before applying the rules to past entries.

### 🧰 Around it

#### 11. Privacy mode

<p align="center">
  <img src="docs/gifs/privacidade.gif" alt="One click hides every money value" width="100%">
</p>

One click hides every money value and keeps percentages visible. Handy for opening the dashboard in
public or sharing your screen.

#### 12. On the phone

<table>
  <tr>
    <td width="36%" align="center"><img src="docs/gifs/celular.gif" alt="Phone navigation: home, analytics, briefing and cash" width="100%"></td>
    <td valign="middle">
      The mobile layout uses tab navigation (Home, Analytics, Briefing, Cash and More) and can be
      installed as an app (PWA) on the iPhone home screen.<br><br>
      Access goes through the private Tailscale network and requires Face ID. No port is open to the
      internet.
    </td>
  </tr>
</table>

<details>
<summary><b>More screens: phone, quotes and security</b></summary>

<br>

**Three phone screens**

![Dashboard on the phone](docs/screenshots/celular.png)

**Quotes:** the latest quote for each asset, with automatic lookup on Yahoo Finance and manual entry.
On the same date, a manual quote wins over the automatic one.

![Quotes](docs/screenshots/cotacoes.png)

**Security:** device enrollment with a pairing code, the list of passkeys and a button to lock out
every device at once.

![Phone access security](docs/screenshots/seguranca-celular.png)

**Privacy mode on**

![Hidden values](docs/screenshots/modo-privacidade.png)

</details>

#### 13. Notes

![Notes with a pinned note, a passage highlighted in the briefing and the Claude tag](docs/screenshots/anotacoes.png)

A notebook for theses, questions and reminders about the portfolio (or anything else), with search,
pinned notes and the passages highlighted in the briefing. Notes stay on your computer. Only the ones
you mark "Use in the conversation with Claude" go into the context sent to Claude and into the daily
task's reading.

#### On the computer

A Mac-style sidebar shows every screen grouped by area, one click away. Groups collapse and the app
remembers how you left them. On mid-size screens, like a tablet, it turns into an icon-only rail.

#### Beyond the browser

- 🚀 **Launcher** ([`launcher/dashboard.py`](investimentos-codigo-cf1/launcher/dashboard.py)): one
  command, or a Windows shortcut, that installs dependencies when they changed, checks Postgres,
  applies migrations, starts the backend and frontend, loads the "Entrada" folder and opens the
  browser. It uses only the Python standard library and adapts to the terminal: rich output, a safe
  mode for the legacy Windows console and plain text.
- 🪟 **Desktop widget** ([`widget/`](investimentos-codigo-cf1/widget/), Tkinter): shows net worth per
  currency, the result, the session change, a 30-day chart and the day's news. It can start with
  Windows or Linux.
- 📂 **"Entrada" folder:** save a statement or card bill into a folder and it is imported through the
  same path as the screen, without duplicates. Accepted files move to `importados/YYYY-MM-DD/`.

---

## 🧱 Architecture

```mermaid
flowchart LR
    subgraph PC["User's computer"]
        direction LR
        subgraph FE["Frontend · React 19 + Vite"]
            UI["Screens<br/>(Investments · Cash · Registry · Security)"]
            PX["/api proxy<br/>+ client host header"]
        end
        subgraph BE["Backend · FastAPI (127.0.0.1:8000)"]
            R["Routers<br/>(113 endpoints)"]
            S["Services<br/>(orchestration, transactions)"]
            D["Domain<br/>(pure engines: financial_engine,<br/>cashflow_engine, analytics, reconciliation)"]
            RP["Repositories"]
        end
        DB[("PostgreSQL<br/>integrity triggers")]
        W["Tkinter widget"]
        L["CLI launcher"]
        F[/"claude-analises/<br/>carteira.json · relatorios/ · alertas/"/]
        IN[/"Entrada/<br/>statements and bills"/]
    end
    Y["Yahoo Finance<br/>(only the ticker leaves)"]
    BCB["Central Bank SGS<br/>(daily CDI)"]
    C["Scheduled<br/>Claude task"]
    TS["Tailscale<br/>(private network)"]
    CEL["iPhone<br/>passkey / Face ID"]

    UI --> PX --> R --> S --> D
    S --> RP --> DB
    W --> R
    L --> R
    S <--> F
    S <--> IN
    S --> Y
    S --> BCB
    C <--> F
    CEL --> TS --> PX
```

### Backend layers

| Layer | Folder | Responsibility |
|---|---|---|
| **Routers** | `app/api/routers/` | HTTP: input validation (Pydantic), status codes and mapping domain exceptions to 400/404/409/422 |
| **Services** | `app/services/` | Orchestration: load facts, call the engines, control the database transaction (SAVEPOINT, row locks) and access files and external services |
| **Domain** | `app/domain/` | **Pure logic, no database, HTTP or I/O.** Takes immutable facts and returns results. Every formula lives here, which makes it the most tested layer |
| **Repositories** | `app/repositories/` | The only place that queries fact tables for calculations. Filters out reversed entries and turns rows into immutable dataclasses |
| **Models** | `app/models/` | SQLAlchemy 2 (`Mapped[...]` typing), every money value as `Numeric`, never `float` |
| **Migrations** | `alembic/versions/` | 18 migrations, with triggers, enums and seed data for currencies and asset classes |

### Stack

| Area | Technologies |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic Settings, SQLAlchemy 2, Alembic, psycopg 3 |
| Calculations | `Decimal` across the financial domain, `pyxirr` for XIRR and a custom lognormal scenario model |
| Imports | `ofxparse`, `openpyxl` and `pdfminer.six` (positional reading of the PDF statement) |
| Remote auth | `webauthn` (passkeys) and `@simplewebauthn/browser` |
| Frontend | React 19, TypeScript 6, Vite 8, Tailwind CSS 4, Recharts 3, IBM Plex Sans/Serif |
| Tests | pytest (against real Postgres), Vitest, Testing Library and jsdom |
| Quality | Ruff, Black and Oxlint |
| Desktop | Tkinter (widget) and a standard-library CLI (launcher) |
| Network | Tailscale Serve (HTTPS inside the private network) |

### Data model (simplified)

```mermaid
erDiagram
    USER ||--o{ ACCOUNT : owns
    INSTITUTION ||--o{ ACCOUNT : serves
    PORTFOLIO |o--o{ ACCOUNT : groups
    ACCOUNT ||--o{ TRANSACTION : "investment ledger (BROKERAGE)"
    ACCOUNT ||--o{ CASHFLOW_ENTRY : "cash ledger (CHECKING, SAVINGS, CREDIT_CARD)"
    ASSET |o--o{ TRANSACTION : references
    ASSET_CLASS ||--o{ ASSET : classifies
    ASSET ||--o{ ASSET_PRICE : quotes
    TRANSACTION |o--o| TRANSACTION : "reversal / transfer leg"
    CASHFLOW_ENTRY }o--o| CATEGORY : classified
    CASHFLOW_IMPORT_BATCH ||--o{ CASHFLOW_ENTRY : imported
    TRANSACTION ||--o{ RECONCILIATION_LOG : "suspected pair"
    USER ||--o{ PASSKEY : devices
    USER ||--o{ ALLOCATION_TARGET : targets
```

The account type decides the ledger, and **ledgers never mix**: a brokerage account does not take
cash entries, and vice versa. The rule is enforced by a database trigger, not just by code.

---

## 🧠 Engineering decisions

| Decision | Why |
|---|---|
| **Positions and balances are computed, never stored** | Events (`Transaction`, `CashflowEntry`) are the source of truth. Position, average cost and balance are recomputed from scratch, so there is no derived state to drift out of sync. |
| **Immutable facts, with reversal as the only way to correct** | Triggers reject `UPDATE` on fact columns and any `DELETE`. Fixing an entry means reversing it (`ACTIVE → REVERSED`) and recording it again. The audit trail is complete by construction. |
| **The engine cannot see reversed entries** | `TransactionFact` **has no `status` field**. The reversal filter lives in a single repository, so the engine cannot include a reversed entry by mistake. |
| **Currencies never add up** | Every summary, KPI and chart is grouped by currency. XIRR is only computed when all cash flows are in the same currency. |
| **`Decimal` across the financial domain, `Numeric` in the database** | No floating-point error with money. Values come back from the API as positional strings, never in scientific notation. |
| **HMAC-signed preview before commit** | The import commit only accepts the payload the server signed during preview. You cannot save something different from what was shown. The default secret is refused outside development. |
| **All-or-nothing imports** | Each commit runs in its own SAVEPOINT. If one selected line is rejected, nothing is saved. |
| **Duplicate detection by content key** | Importing twice, or the CSV and the PDF for the same month in any order, creates no duplicates. The OFX `FITID` is not used as a key because it repeats in real files. |
| **Transfers with database-level integrity** | Both legs (`TRANSFER_OUT` and `TRANSFER_IN`) are linked by a self-referencing FK, and a trigger *deferred* to commit validates the pair. |
| **Reconciliation never changes anything on its own** | The scan only records suspected pairs (the same event from different sources). The user decides: ignore, keep both or merge. |
| **No router on the frontend** | Navigation is local state on two levels (area and page). The app is small enough not to need `react-router`. |
| **Documentation per phase** | Each unit of work has a document in [`backend/docs/`](investimentos-codigo-cf1/backend/docs/) with the decisions taken and why. |

---

## 🧮 Calculation engines

They all live in [`app/domain/`](investimentos-codigo-cf1/backend/app/domain/) and are pure functions,
with no database or network.

| Engine | What it computes |
|---|---|
| `financial_engine/position.py` | Position, **weighted average cost**, realized gain and realized cost kept apart from the remaining cost. The same formula applies to Brazilian and foreign assets. |
| `financial_engine/performance.py` | **XIRR** (dated cash flows), **CAGR** (only with exactly two dates) and **TWR** (time-weighted return, with sub-periods between external flows). |
| `financial_engine/valuation.py` | Market value at the latest quote, never mixing currencies. |
| `analytics/benchmark.py` | "**What if it were the CDI?**" simulation: applies the same deposits, on the same dates, to the Central Bank's daily CDI series. |
| `analytics/scenarios.py` | **Lognormal** portfolio model, with historical volatility and correlation (or per-class defaults when history is short), 10th/50th/90th percentiles and probability of loss. |
| `analytics/kpis.py`, `concentration.py` | Diversification (`1/HHI`), concentration, per-asset contribution, annualized volatility, maximum drawdown and 52-week range. |
| `analytics/lookthrough.py` | Exposure to the companies **behind the ETFs**: fund weight times the company's weight in the fund, summed across funds. |
| `analytics/allocation.py`, `agenda.py`, `financial_health.py` | Distance to target allocation, fixed-income maturities, months of reserve and savings rate. |
| `cashflow_engine/` | Balance per account, monthly summary, category breakdown, **description cleanup** (installments, channel, transaction codes), rules engine and matching of transfers and card payments. |
| `reconciliation/matcher.py` | Pairs that look like the same event, compared field by field, with a relative tolerance on the amount. |

---

## 📥 Statement imports

| Source | Format | Detection | Notes |
|---|---|---|---|
| Broker | CSV, XLSX, OFX | extension and content | Asset, currency and country are validated line by line. A ticker that exists in two countries is rejected, never silently resolved. |
| Checking account (Nubank) | CSV, OFX | header | OFX carries the balance. On the first import, the system creates the opening balance that makes the account match the bank. |
| Credit card (Nubank) | CSV, OFX, **PDF** | `%PDF-` / `<CCSTMTRS>` | The PDF is checked against the statement summary, and dates without a year are resolved from the issue date. Refunds, installment Pix on credit and early-payment discounts are handled separately. |

```mermaid
flowchart LR
    A["📄 File"] --> B["Pure parser"] --> C["Preview<br/>errors · duplicates · rule"] --> D["HMAC signature"] --> E["Atomic commit"] --> F["Rules applied"] --> G["Transfers matched"]
```

The file itself is not stored. Only its name and fingerprint are kept.

---

## 🤖 Claude integration

The dashboard **does not call any AI**. The integration happens through files, in an exchange folder:

```
claude-analises/
├── carteira.json          ← written by the backend: positions, weights, KPIs, scenarios, calendar, benchmarks, allocation
├── relatorios/
│   └── YYYY-MM-DD.json    ← the daily Claude task writes the briefing (format v4, validated by the backend)
└── alertas/
    └── YYYY-MM-DD.json    ← the hourly task writes only when there is HIGH/CRITICAL news
```

- The scheduled task prompts are versioned in
  [`backend/docs/agente-prompts/`](investimentos-codigo-cf1/backend/docs/agente-prompts/). A test
  makes sure the prompt asks for the latest format version.
- The backend **validates** every report. A file that does not match the format shows up as
  "rejected", with the reason. A fraction above 500% also rejects the file, to catch a "39" written
  instead of "0.39".
- The "Ask Claude" button builds a `claude.ai/new` link with the portfolio context
  (`GET /insights/chat-context`), capped in size. The conversation runs on the user's own
  subscription.

---

## 🔒 Security and privacy

The API has no login of its own, because the system has a single user. The security boundary is the
**network**, and it is closed in layers:

| Layer | Protection |
|---|---|
| Network | The backend listens **only on `127.0.0.1`** and is never published. The phone reaches the frontend over the private Tailscale network, and Vite forwards `/api` to the local backend. |
| DNS rebinding | `Host` allowlist in the backend (`localhost`, `127.0.0.1`) and in Vite (`localhost`, `*.ts.net`). |
| CORS | Only the frontend's own origin can read responses. |
| Local × remote | The proxy **overwrites** a header with the host the browser used. Any sign of forwarding makes the request remote, and the rule denies by default. |
| Remote access | **Passkeys (WebAuthn)** with Face ID. Device enrollment uses a 10-minute, single-use pairing code that locks after 5 attempts. The session lives in an `HttpOnly; Secure; SameSite=Strict` cookie, and every device can be revoked at once. |
| Headers | `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer` and a restrictive `Permissions-Policy`. |
| Uploads | Configurable size cap (10 MB by default), and no file is stored. |
| External data | Only tickers leave the computer (Yahoo Finance), plus the public CDI series (Central Bank). |
| Repository | Statements, bills, `.env`, local databases and the analysis folder stay out of git (`.gitignore`). |

---

## 🔌 API

113 REST endpoints, documented automatically by FastAPI at `http://127.0.0.1:8000/docs` when the
backend is running.

| Group | Examples |
|---|---|
| Registry | `/institutions`, `/accounts`, `/portfolios`, `/assets`, `/currencies`, `/asset-classes` |
| Investments | `/transactions`, `/transactions/{id}/reverse`, `/transactions/{id}/correct`, `/transfers` |
| Import | `/imports/preview`, `/imports/commit` |
| Dashboard | `/dashboard/summary`, `/overview`, `/dividends/summary`, `/performance/history`, `/performance/agenda`, `/performance/allocation` |
| Performance | `/performance/kpis`, `/performance/benchmarks`, `/performance/financial-health`, `/analytics/portfolio`, `/performance/widget` |
| Quotes | `/prices/latest`, `/prices/refresh`, `/assets/{id}/prices` |
| Cash | `/cashflow/entries`, `/cashflow/summary`, `/cashflow/summary/categories`, `/cashflow/balances` |
| Classification | `/cashflow/categories`, `/cashflow/tags`, `/cashflow/rules`, `/cashflow/rules/preview`, `/cashflow/rules/apply` |
| Cash import | `/cashflow/imports/preview`, `/cashflow/imports/commit`, `/cashflow/inbox/process` |
| Reconciliation | `/reconciliation/scan`, `/reconciliation/pending`, `/reconciliation/{id}/comparison`, `/reconciliation/{id}/resolve` |
| Claude | `/insights`, `/insights/{date}`, `/insights/alerts`, `/insights/snapshot`, `/insights/lookthrough`, `/insights/chat-context` |
| Notes | `/notes`, `/notes/{id}`, `/reading-sources`, `/reading-sources/{id}` |
| Remote access | `/auth/status`, `/auth/pairing`, `/auth/register/*`, `/auth/login/*`, `/auth/passkeys`, `/auth/sessions/revoke-all` |

---

## 📁 Repository layout

```
.
├── Iniciar Dashboard.bat · Parar Dashboard.bat · Abrir widget.bat · ...   ← Windows shortcuts
├── docs/
│   ├── hero.svg · hero.en.svg              ← animated banner for this README
│   ├── gifs/                               ← animations (fictitious data)
│   └── screenshots/                        ← images (fictitious data)
└── investimentos-codigo-cf1/
    ├── backend/
    │   ├── app/
    │   │   ├── api/routers/                ← HTTP layer
    │   │   ├── services/                   ← orchestration, importers and market data
    │   │   ├── domain/                     ← pure calculation engines
    │   │   ├── repositories/
    │   │   ├── models/ · schemas/
    │   │   └── core/                       ← configuration and local/remote detection
    │   ├── alembic/versions/               ← 18 migrations (triggers, enums, seeds)
    │   ├── tests/                          ← domain · services · api (real Postgres)
    │   ├── scripts/seed_demo.py            ← demo portfolio
    │   └── docs/                           ← per-phase decisions and agent prompts
    ├── frontend/
    │   └── src/
    │       ├── pages/ · pages/cash/        ← investment and cash screens
    │       ├── components/                 ← overview, charts, cash, insights, mobile, security...
    │       ├── api/                        ← typed API client
    │       └── lib/                        ← formatting, privacy and testable screen logic
    ├── launcher/                           ← CLI launcher (standard library only)
    └── widget/                             ← desktop widget (Tkinter)
```

---

## 🚀 Running it

### Requirements

- Python **3.12+**
- Node.js **20.19+ or 22.12+** (required by Vite 8; developed on 24)
- PostgreSQL running on `localhost:5432` (developed and tested on 16)

### 1. Database

```sql
CREATE DATABASE investimentos_dev;
```

The default URL is `postgresql+psycopg://postgres:postgres@localhost:5432/investimentos_dev`. To
change it, copy [`backend/.env.example`](investimentos-codigo-cf1/backend/.env.example) to
`backend/.env` and set `DATABASE_URL`.

### 2. Backend

```bash
cd investimentos-codigo-cf1/backend
python -m venv .venv
# Windows: .venv\Scripts\activate    ·    Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 3. Frontend

```bash
cd investimentos-codigo-cf1/frontend
npm install
npm run dev          # http://localhost:5173
```

### 4. (Optional) Demo portfolio

With the backend running against an **empty** database:

```bash
cd investimentos-codigo-cf1/backend
python scripts/seed_demo.py
```

### Windows shortcut

After creating the database, double-click **`Iniciar Dashboard.bat`**. The launcher creates the
environment, installs dependencies, applies migrations, starts everything and opens the browser. To
stop, use **`Parar Dashboard.bat`**.

```bash
python investimentos-codigo-cf1/launcher/dashboard.py iniciar [--widget] [--sem-navegador]
python investimentos-codigo-cf1/launcher/dashboard.py parar | carregar | celular | atalhos
```

---

## ✅ Tests and quality

| Part | Tests | Command |
|---|---|---|
| Backend | **1,375** | `cd investimentos-codigo-cf1/backend && pytest` |
| Frontend | **645** | `cd investimentos-codigo-cf1/frontend && npm test` |
| Launcher | **69** | `cd investimentos-codigo-cf1/launcher && pytest` |
| Widget | **22** | `cd investimentos-codigo-cf1/widget && pytest` |

Frontend lint and type checking: `npm run lint && npm run build`.

- Backend tests run against **real PostgreSQL**, not SQLite, to exercise the triggers, enums and
  *deferred* constraints that guarantee integrity. The test database is created and cleaned up by
  the tests themselves.
- Domain engines have pure unit tests. Services and API have end-to-end integration tests: import,
  classify, match transfers and check that the accounting identity holds.
- The PDF statement reader was validated against 23 real statements, which are not in this
  repository. Tests use a synthetic statement generated byte by byte in
  [`tests/fatura_pdf_helpers.py`](investimentos-codigo-cf1/backend/tests/fatura_pdf_helpers.py).

---

## 💬 FAQ

<details>
<summary><b>Does it tell me what to buy?</b></summary>
<br>
No. Every analysis, including Claude's, is a reading of your portfolio's numbers. Scenarios are a
statistical model, and the "ideas to research" are starting points with thesis, risks and sources.
The interface says so explicitly.
</details>

<details>
<summary><b>Do I have to give anyone my bank password?</b></summary>
<br>
No. You download the statement or card bill from your bank's app and import the file. Nothing
connects to your account.
</details>

<details>
<summary><b>Does it work offline?</b></summary>
<br>
Almost everything does. Automatic quotes (Yahoo Finance) and the CDI series (Central Bank) need a
connection, and only ticker symbols leave the computer. Offline, manual quotes still work.
</details>

<details>
<summary><b>Why not a spreadsheet?</b></summary>
<br>
Because a spreadsheet will happily add reais to dollars, lets you delete an entry without a trace,
and has no idea whether the bill you pasted matches the bank's summary. Here, those rules live in
the database and in the tests, not in the goodwill of whoever is typing.
</details>

---

## 🚧 Known limitations

- **Single user, by design.** The app is meant to run on its owner's computer, not as a multi-user
  service.
- **Spending control reads Nubank's format** (account and card). Other banks need a new parser in
  `services/cashflow_imports/`.
- **Automatic quotes carry the public source's delay** (about 15 minutes). Fixed income and funds use
  manual quotes.
- **Phone access depends on the computer being on** and on Tailscale on both devices.
- **Scenarios are a statistical model with long-term assumptions**, not a forecast.

---

<p align="center">
  Built by <b>Luis Fernando Freitas</b>, data analyst<br>
  <a href="https://www.linkedin.com/in/luis-fernando-freitas-a3503b284/">LinkedIn</a> ·
  <a href="https://github.com/Lfafreitas">GitHub</a>
</p>
