<p align="center">
  <img src="docs/hero.svg" alt="Finance Hub: seu dinheiro explicado, num lugar só" width="100%">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/PostgreSQL-SQLAlchemy%202%20%2B%20Alembic-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black" alt="React 19">
  <img src="https://img.shields.io/badge/TypeScript-6-3178C6?logo=typescript&logoColor=white" alt="TypeScript">
  <img src="https://img.shields.io/badge/Tailwind-4-06B6D4?logo=tailwindcss&logoColor=white" alt="Tailwind">
  <img src="https://img.shields.io/badge/testes-2.111%20passando-2EA043" alt="2.111 testes passando">
</p>

<p align="center">
  <b>Português</b> · <a href="README.en.md">English</a>
</p>

<p align="center">
  <img src="docs/gifs/tour.gif" alt="Tour pelo dashboard: visão geral, evolução, alocação, análises, jornal e controle financeiro" width="100%">
</p>

> [!NOTE]
> Todos os valores, contas e ativos das imagens e animações são **fictícios**. Eles vêm do script
> [`seed_demo.py`](investimentos-codigo-cf1/backend/scripts/seed_demo.py), que monta uma carteira de
> demonstração num banco vazio.

---

## ⚡ Em 30 segundos

O **Finance Hub** é uma aplicação web que roda no seu computador e junta, num lugar só, a carteira de
investimentos (no Brasil e no exterior), a conta do banco e a fatura do cartão.

- 💵 **Reais e dólares lado a lado.** Cada moeda tem o seu resultado, e nada é somado com uma
  conversão escondida.
- 🧾 **Importa extrato e fatura**, inclusive a fatura em PDF, conferida centavo por centavo antes de
  gravar.
- 📈 **Compara a carteira com o CDI e o S&P 500**, usando os mesmos aportes nas mesmas datas.
- 📰 **Todo dia útil, um jornal da carteira** escrito por uma rotina agendada do Claude, com as
  notícias que afetam os seus ativos.
- 🔒 **Os dados ficam na sua máquina.** O celular acessa por uma rede privada e só abre com Face ID.

## 🤔 Perguntas que ele responde

| Pergunta | Onde a resposta aparece |
|---|---|
| Quanto eu tenho de verdade, e quanto é investimento, reserva ou dinheiro parado? | [Visão geral](#1-visão-geral-do-patrimônio) |
| Valeu mais a pena do que deixar no CDI? | [Evolução e referência](#2-evolução-e-comparação-com-a-referência) |
| Minha carteira está longe do que eu planejei? | [Alocação contra alvo](#3-agenda-proventos-e-alocação-contra-alvo) |
| Para onde foi o meu salário este mês? | [Controle financeiro](#8-controle-financeiro) |
| Quantos meses a minha reserva aguenta? | [Caixa, reserva e poupança](#4-caixa-reserva-e-poupança) |
| E se o mercado cair até dezembro? | [Cenários](#6-análises-cenários-e-ritmo-de-aporte) |
| Que notícia de hoje mexe com o que eu tenho? | [Jornal da carteira](#7-jornal-da-carteira) |

---

## 🧭 Sumário

- [Em números](#-em-números)
- [Funcionalidades](#-funcionalidades)
- [Arquitetura](#-arquitetura)
- [Decisões de engenharia](#-decisões-de-engenharia)
- [Motores de cálculo](#-motores-de-cálculo)
- [Importação de extratos e faturas](#-importação-de-extratos-e-faturas)
- [Integração com o Claude](#-integração-com-o-claude)
- [Segurança e privacidade](#-segurança-e-privacidade)
- [API](#-api)
- [Estrutura do repositório](#-estrutura-do-repositório)
- [Como rodar](#-como-rodar)
- [Testes e qualidade](#-testes-e-qualidade)
- [Perguntas frequentes](#-perguntas-frequentes)
- [Limitações conhecidas](#-limitações-conhecidas)

---

## 📊 Em números

| | |
|---|---|
| Código de aplicação | **~38 mil linhas** (backend 19,1 mil · frontend 17,1 mil · iniciador e widget 1,9 mil) |
| Código de teste | **~31 mil linhas** (backend 20,6 mil · frontend 10,2 mil) |
| Testes automatizados | **2.111 passando** (backend 1.375 · frontend 645 · iniciador 69 · widget 22) |
| Endpoints REST | **113** |
| Banco de dados | **22 tabelas** · **18 migrações** Alembic, com triggers de integridade |
| Formatos importados | CSV, XLSX e OFX de corretora · CSV e OFX de conta · CSV, OFX e **PDF** de fatura |

### O problema

Quem investe no Brasil e no exterior acaba com a vida financeira espalhada: a corretora americana
mostra dólar, a brasileira mostra real, o banco mostra o extrato e o cartão mostra a fatura. Nenhum
deles responde às perguntas que importam. Os agregadores prontos resolvem parte disso, mas pedem a
senha do banco e costumam somar reais com dólares numa conversão que esconde o câmbio.

### A solução

Uma aplicação web **local**, com um único usuário, que reúne dois livros contábeis:

| Livro | O que registra | O que entrega |
|---|---|---|
| 📈 **Investimentos** | compras, vendas, proventos, transferências e eventos societários, por corretora e moeda | posição e preço médio, rentabilidade (XIRR, TWR, CAGR), comparação com CDI e S&P 500, cenários, concentração, alocação contra alvo e vencimentos |
| 💳 **Controle financeiro** | extrato da conta e fatura do cartão importados do banco | renda × gastos, gastos por categoria, taxa de poupança, quantos meses a reserva cobre e transferências casadas automaticamente |

Por cima dos dois livros, uma rotina agendada do **Claude** lê um retrato da carteira e escreve, todo
dia útil, um **Jornal da carteira**, além de alertas de hora em hora quando sai algo sério.

### O que diferencia o projeto

- **Moedas nunca se somam.** Reais e dólares aparecem lado a lado, cada um com o seu resultado.
- **Os fatos financeiros são imutáveis.** Erro se corrige com estorno e lançamento novo, e o banco
  de dados garante isso com triggers.
- **Importar nunca grava às cegas.** Todo arquivo passa por uma prévia assinada com HMAC, e o commit
  grava exatamente o que foi mostrado, tudo ou nada.
- **Os dados ficam na sua máquina.** O backend só escuta em `127.0.0.1`. Saem do computador apenas
  os códigos dos ativos, para buscar cotações, e a série pública do CDI.
- **Acesso pelo celular com Face ID**, por uma rede privada do Tailscale, com passkeys (WebAuthn) e
  sem nenhuma porta aberta para a internet.

---

## ✨ Funcionalidades

<table>
  <tr>
    <td width="33%" valign="top"><b>📈 Investimentos</b><br><br>
      Patrimônio por moeda<br>
      Evolução e comparação com CDI e S&P 500<br>
      Vencimentos, proventos e alocação-alvo<br>
      Indicadores, risco e cenários<br>
      Cotações automáticas e manuais<br>
      Reconciliação entre fontes
    </td>
    <td width="33%" valign="top"><b>💳 Controle financeiro</b><br><br>
      Renda × gastos, mês a mês<br>
      Gastos por categoria e subcategoria<br>
      Reserva e taxa de poupança<br>
      Importação de extrato e fatura (CSV, OFX, PDF)<br>
      Regras de classificação<br>
      Transferências casadas sozinhas
    </td>
    <td width="33%" valign="top"><b>🧰 Em volta</b><br><br>
      Jornal diário e alertas do Claude<br>
      Leitura para dislexia e anotações<br>
      Modo privacidade<br>
      App no celular com Face ID<br>
      Widget de área de trabalho<br>
      Iniciador com um clique<br>
      Pasta Entrada para importar sozinho
    </td>
  </tr>
</table>

### 📈 Investimentos

#### 1. Visão geral do patrimônio

![Visão geral do patrimônio por moeda](docs/screenshots/visao-geral.png)

Patrimônio de todas as contas separado por moeda e dividido em renda variável, renda fixa, reserva e
disponível em conta. Logo abaixo vem a leitura do Claude sobre a carteira: o que está bem, o que pede
atenção, os riscos e o que pode melhorar. É uma leitura dos números, nunca uma recomendação de compra.

#### 2. Evolução e comparação com a referência

![Evolução do patrimônio e comparação com o CDI](docs/screenshots/evolucao-e-referencia.png)

- **Evolução do patrimônio**, com a linha do patrimônio total e a do valor aplicado, em 1M, 3M, 6M,
  1A ou tudo.
- **Comparação com a referência:** o que o **CDI** renderia (em reais) e o que o **SPY** renderia (em
  dólar) **com os mesmos aportes, nas mesmas datas**. A pergunta deixa de ser "quanto rendeu?" e passa
  a ser "valeu mais a pena do que a alternativa?".
- **Gráficos interativos:** ao passar o mouse (ou o dedo, ou as setas do teclado) sobre a linha, o
  número grande do topo mostra o valor daquele dia e a variação até ele, no jeito do app Ações do
  iPhone. Nas barras, o item sob o mouse acende e os outros apagam.

#### 3. Agenda, proventos e alocação contra alvo

![Vencimentos da renda fixa e alocação por classe com alvo](docs/screenshots/agenda-e-alocacao.png)

- Vencimentos da renda fixa, com a estimativa do valor no vencimento por juros compostos.
- Proventos recebidos.
- **Alocação-alvo por classe e moeda:** você define a régua e o painel mostra a distância de cada
  classe até o alvo, em pontos percentuais e em dinheiro.

#### 4. Caixa, reserva e poupança

![Reserva em meses de gasto e taxa de poupança](docs/screenshots/caixa-e-reserva.png)

O controle financeiro alimenta o painel de investimentos: renda e gastos mês a mês, quantos meses de
gasto médio a reserva cobre (com as referências usuais de 3 e 6 meses), a taxa de poupança e quanto
foi investido de fato. O cartão Caixa, com renda e gastos mês a mês, fica ao lado da leitura do Claude
na visão geral.

#### 5. Indicadores da carteira

![Indicadores por ativo](docs/screenshots/indicadores.png)

Calculados por moeda:

- **Da carteira:** maior posição, quanto somam as 3 maiores e diversificação (número efetivo de
  ativos, `1/HHI`).
- **Desempenho:** quantos ativos estão no positivo, o melhor e o pior, e a composição atual simulada
  nos últimos 12 meses.
- **Por ativo:** peso, resultado, contribuição em pontos percentuais e retornos de pregão, 1 mês, no
  ano e 12 meses.
- **Risco:** volatilidade anualizada, pior queda e faixa de 52 semanas.

#### 6. Análises: cenários e ritmo de aporte

![Cenários pessimista, realista e otimista](docs/screenshots/analises-cenarios.png)

- **Cenários até uma data:** modelo lognormal da carteira, com volatilidade e correlação medidas no
  histórico real de cada ativo quando há dados suficientes (60 ou mais retornos diários). Mostra os
  percentis 10, 50 e 90 e a chance de terminar abaixo do valor de hoje.
- **Ritmo de aporte:** quanto entrou por mês e a projeção até dezembro em três ritmos: média do ano,
  últimos 3 meses e mês atual.

#### 7. Jornal da carteira

![Jornal da carteira escrito pelo Claude](docs/screenshots/jornal-da-carteira.png)

A edição do dia, escrita pela rotina agendada do Claude:

- faixa de números do mercado, manchete com lide e "O que acompanhar";
- ideias **para estudar**, cada uma com tese, riscos e fontes;
- as empresas por trás dos ETFs que você tem (look-through);
- um botão "Perguntar ao Claude" que abre uma conversa já com o contexto da carteira;
- **leitura ajustável**, pensada também para quem tem dislexia: fontes Atkinson Hyperlegible, Lexend
  e OpenDyslexic, tamanho do texto, espaçamento entre letras e linhas, largura da coluna e fundo
  "papel", com menos contraste;
- **selecionar um trecho** abre uma barra com Destacar, Anotar, Copiar e Perguntar ao Claude;
- **Outras leituras:** você cadastra os sites e jornais que lê, e a rotina diária traz o que saiu de
  novo em cada um, resumido e ligado à carteira.

<table>
  <tr>
    <td width="50%"><img src="docs/screenshots/leitura-ajustes.png" alt="Ajustes de leitura: fonte OpenDyslexic e fundo papel" width="100%"></td>
    <td width="50%"><img src="docs/screenshots/leitura-selecao.png" alt="Trecho selecionado com Destacar, Anotar, Copiar e Perguntar" width="100%"></td>
  </tr>
</table>

### 💳 Controle financeiro

#### 8. Controle financeiro

![Resumo do controle financeiro](docs/screenshots/controle-financeiro-resumo.png)

- Entradas, saídas, sobra, quanto foi investido e saldo da reserva no mês.
- Entradas × saídas dos últimos 6 meses.
- "Para onde foi o dinheiro": gastos por categoria e subcategoria.
- Investir e transferir entre contas próprias **não contam como gasto**. Pagamento de fatura também
  não: ele é casado automaticamente com o pagamento recebido no cartão.

#### 9. Importação de fatura em PDF, com conferência

<p align="center">
  <img src="docs/gifs/importacao.gif" alt="Importando uma fatura em PDF: prévia, conferência com o resumo e importação" width="100%">
</p>

A fatura fechada do cartão em PDF é lida, e o sistema confere a soma das compras e dos pagamentos com
o resumo da própria fatura **antes de gravar qualquer coisa**. Um centavo de diferença recusa o
arquivo inteiro. A prévia mostra a regra que classificaria cada linha e a situação dela (nova,
duplicada ou com erro). Só depois do clique em "Importar" algo é gravado, e tudo de uma vez.

#### 10. Regras de classificação

![Regras de classificação](docs/screenshots/regras-de-classificacao.png)

"Quando a descrição contém X, classificar como gasto na categoria Y." As regras são testadas em ordem
de prioridade, sobre a descrição já limpa (sem acentos, número de parcela ou intermediário de
pagamento). Dá para ver o que mudaria antes de aplicar as regras aos lançamentos antigos.

### 🧰 Em volta

#### 11. Modo privacidade

<p align="center">
  <img src="docs/gifs/privacidade.gif" alt="Um clique esconde todos os valores em dinheiro" width="100%">
</p>

Um clique esconde todos os valores em dinheiro e mantém os percentuais visíveis. Serve para abrir o
dashboard em público ou compartilhar a tela.

#### 12. No celular

<table>
  <tr>
    <td width="36%" align="center"><img src="docs/gifs/celular.gif" alt="Navegação no celular: início, análises, jornal e caixa" width="100%"></td>
    <td valign="middle">
      O layout móvel tem navegação por abas (Início, Análises, Jornal, Caixa e Mais) e pode ser
      instalado como app (PWA) na tela de início do iPhone.<br><br>
      O acesso passa pela rede privada do Tailscale e exige Face ID. Nenhuma porta fica aberta para a
      internet.
    </td>
  </tr>
</table>

<details>
<summary><b>Mais telas: celular, cotações e segurança</b></summary>

<br>

**Três telas no celular**

![Dashboard no celular](docs/screenshots/celular.png)

**Cotações:** a última cotação de cada ativo, com busca automática no Yahoo Finance e registro manual.
Na mesma data, a cotação manual vence a automática.

![Cotações](docs/screenshots/cotacoes.png)

**Segurança:** cadastro de aparelhos por código de pareamento, lista de passkeys e bloqueio de todos
os aparelhos de uma vez.

![Segurança do acesso pelo celular](docs/screenshots/seguranca-celular.png)

**Modo privacidade ligado**

![Valores escondidos](docs/screenshots/modo-privacidade.png)

</details>

#### 13. Anotações

![Anotações com nota fixada, trecho destacado do Jornal e marca do Claude](docs/screenshots/anotacoes.png)

Um caderno para teses, dúvidas e lembretes sobre a carteira (ou qualquer assunto), com busca, notas
fixadas e os trechos destacados no Jornal. As notas ficam no computador. Só as que você marcar com
"Usar na conversa com o Claude" entram no resumo levado ao Claude e na leitura da rotina diária.

#### No computador

Uma barra lateral no jeito dos apps do Mac mostra todas as telas agrupadas por área, com um clique
para qualquer uma. Os grupos recolhem e o app lembra como ficaram. Em telas médias, como a de um
tablet, ela vira uma coluna só de ícones.

#### Além do navegador

- 🚀 **Iniciador** ([`launcher/dashboard.py`](investimentos-codigo-cf1/launcher/dashboard.py)): um
  comando, ou um atalho no Windows, que instala as dependências quando elas mudaram, confere o
  Postgres, aplica as migrações, liga o backend e o frontend, carrega a pasta Entrada e abre o
  navegador. Usa só a biblioteca padrão do Python e se adapta ao terminal: tem saída rica, uma segura
  para o console antigo do Windows e uma de texto puro.
- 🪟 **Widget de área de trabalho** ([`widget/`](investimentos-codigo-cf1/widget/), Tkinter): mostra o
  patrimônio por moeda, o resultado, a variação do pregão, um gráfico de 30 dias e as notícias do dia.
  Pode abrir junto com o Windows ou com o Linux.
- 📂 **Pasta Entrada:** basta salvar o extrato ou a fatura numa pasta para eles serem importados pelo
  mesmo caminho da tela, sem duplicar. Os arquivos aceitos vão para `importados/AAAA-MM-DD/`.

---

## 🧱 Arquitetura

```mermaid
flowchart LR
    subgraph PC["Computador do usuário"]
        direction LR
        subgraph FE["Frontend · React 19 + Vite"]
            UI["Telas<br/>(Investimentos · Caixa · Cadastros · Segurança)"]
            PX["Proxy /api<br/>+ cabeçalho do host do cliente"]
        end
        subgraph BE["Backend · FastAPI (127.0.0.1:8000)"]
            R["Routers<br/>(113 endpoints)"]
            S["Services<br/>(orquestração, transações)"]
            D["Domain<br/>(motores puros: financial_engine,<br/>cashflow_engine, analytics, reconciliation)"]
            RP["Repositories"]
        end
        DB[("PostgreSQL<br/>triggers de integridade")]
        W["Widget Tkinter"]
        L["Iniciador CLI"]
        F[/"claude-analises/<br/>carteira.json · relatorios/ · alertas/"/]
        IN[/"Entrada/<br/>extratos e faturas"/]
    end
    Y["Yahoo Finance<br/>(só o ticker sai)"]
    BCB["Banco Central SGS<br/>(CDI diário)"]
    C["Tarefa agendada<br/>do Claude"]
    TS["Tailscale<br/>(rede privada)"]
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

### Camadas do backend

| Camada | Pasta | Responsabilidade |
|---|---|---|
| **Routers** | `app/api/routers/` | HTTP: validação de entrada (Pydantic), códigos de status e mapeamento de exceções de domínio para 400/404/409/422 |
| **Services** | `app/services/` | Orquestração: carregam fatos, chamam os motores, controlam a transação de banco (SAVEPOINT, locks de linha) e acessam arquivos e serviços externos |
| **Domain** | `app/domain/` | **Lógica pura, sem banco, HTTP ou I/O.** Recebe fatos imutáveis e devolve resultados. Aqui vivem todas as fórmulas, e por isso é a camada mais testada |
| **Repositories** | `app/repositories/` | O único ponto que consulta as tabelas de fatos para cálculo. Filtra o que foi estornado e converte linhas em dataclasses imutáveis |
| **Models** | `app/models/` | SQLAlchemy 2 (tipagem `Mapped[...]`), todo valor monetário em `Numeric`, nunca em `float` |
| **Migrations** | `alembic/versions/` | 18 migrações, com triggers, enums e seeds de moedas e classes de ativo |

### Stack

| Área | Tecnologias |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic Settings, SQLAlchemy 2, Alembic, psycopg 3 |
| Cálculo | `Decimal` em todo o domínio financeiro, `pyxirr` para XIRR e modelo lognormal próprio para cenários |
| Importação | `ofxparse`, `openpyxl` e `pdfminer.six` (leitura posicional da fatura em PDF) |
| Autenticação remota | `webauthn` (passkeys) e `@simplewebauthn/browser` |
| Frontend | React 19, TypeScript 6, Vite 8, Tailwind CSS 4, Recharts 3, IBM Plex Sans/Serif |
| Testes | pytest (com Postgres real), Vitest, Testing Library e jsdom |
| Qualidade | Ruff, Black e Oxlint |
| Desktop | Tkinter (widget) e CLI com a biblioteca padrão (iniciador) |
| Rede | Tailscale Serve (HTTPS dentro da rede privada) |

### Modelo de dados (simplificado)

```mermaid
erDiagram
    USER ||--o{ ACCOUNT : possui
    INSTITUTION ||--o{ ACCOUNT : atende
    PORTFOLIO |o--o{ ACCOUNT : agrupa
    ACCOUNT ||--o{ TRANSACTION : "livro de investimentos (BROKERAGE)"
    ACCOUNT ||--o{ CASHFLOW_ENTRY : "livro de caixa (CHECKING, SAVINGS, CREDIT_CARD)"
    ASSET |o--o{ TRANSACTION : referencia
    ASSET_CLASS ||--o{ ASSET : classifica
    ASSET ||--o{ ASSET_PRICE : cotacoes
    TRANSACTION |o--o| TRANSACTION : "estorno / perna da transferência"
    CASHFLOW_ENTRY }o--o| CATEGORY : classificada
    CASHFLOW_IMPORT_BATCH ||--o{ CASHFLOW_ENTRY : importou
    TRANSACTION ||--o{ RECONCILIATION_LOG : "par suspeito"
    USER ||--o{ PASSKEY : "aparelhos"
    USER ||--o{ ALLOCATION_TARGET : alvos
```

O tipo da conta decide o livro, e **os livros não se misturam**: uma conta de corretora não recebe
lançamento de caixa, e vice-versa. A regra é garantida por trigger no banco, não só pelo código.

---

## 🧠 Decisões de engenharia

| Decisão | Por quê |
|---|---|
| **Posição e saldo são calculados, nunca guardados** | A fonte da verdade são os eventos (`Transaction`, `CashflowEntry`). Posição, preço médio e saldo são recalculados do zero, então não existe estado derivado que fique dessincronizado. |
| **Fatos imutáveis e estorno como único caminho de correção** | Triggers recusam `UPDATE` em campos de fato e qualquer `DELETE`. Corrigir um lançamento é estornar (`ACTIVE → REVERSED`) e lançar de novo. A trilha de auditoria fica completa por construção. |
| **O motor não enxerga o que foi estornado** | `TransactionFact` **não tem campo `status`**. O filtro de estornos existe em um único repositório, então o motor não tem como incluir por engano algo estornado. |
| **Moedas nunca se somam** | Todos os resumos, KPIs e gráficos são agrupados por moeda. O XIRR só é calculado quando todos os fluxos estão na mesma moeda. |
| **`Decimal` em todo o domínio financeiro, `Numeric` no banco** | Não há erro de ponto flutuante em dinheiro. Os valores voltam da API como string posicional, nunca em notação científica. |
| **Prévia assinada com HMAC antes do commit** | O commit da importação só aceita o payload que o servidor assinou na prévia. Não dá para gravar algo diferente do que foi mostrado. O segredo padrão é recusado fora de desenvolvimento. |
| **Importação tudo ou nada** | Cada commit roda num SAVEPOINT próprio. Se uma linha selecionada for recusada, nada é gravado. |
| **Duplicidade por chave de conteúdo** | Importar duas vezes, ou CSV e PDF do mesmo mês em qualquer ordem, não duplica nada. O `FITID` do OFX não serve de chave porque se repete no arquivo real. |
| **Transferências com integridade no banco** | As duas pernas (`TRANSFER_OUT` e `TRANSFER_IN`) são ligadas por FK auto-referente, e um trigger *deferred* para o commit valida o par. |
| **Reconciliação nunca altera nada sozinha** | O scan só registra pares suspeitos (mesmo evento vindo de fontes diferentes). Quem decide é o usuário: ignorar, manter os dois ou mesclar. |
| **Sem roteador no frontend** | A navegação é por estado local em dois níveis (área e página). A aplicação é pequena o bastante para não precisar de `react-router`. |
| **Documentação por fase** | Cada unidade de trabalho tem um documento em [`backend/docs/`](investimentos-codigo-cf1/backend/docs/) com as decisões tomadas e o motivo. |

---

## 🧮 Motores de cálculo

Todos ficam em [`app/domain/`](investimentos-codigo-cf1/backend/app/domain/) e são funções puras, sem
banco nem rede.

| Motor | O que calcula |
|---|---|
| `financial_engine/position.py` | Posição, **custo médio ponderado**, ganho realizado e custo realizado separado do remanescente. A mesma fórmula vale para ativos do Brasil e do exterior. |
| `financial_engine/performance.py` | **XIRR** (fluxos datados), **CAGR** (só quando há exatamente duas datas) e **TWR** (retorno ponderado pelo tempo, com subperíodos entre fluxos externos). |
| `financial_engine/valuation.py` | Valor de mercado com a cotação mais recente, sem nunca misturar moedas. |
| `analytics/benchmark.py` | Simulação "**e se fosse CDI?**": aplica os mesmos aportes, nas mesmas datas, na série diária do CDI do Banco Central. |
| `analytics/scenarios.py` | Modelo **lognormal** da carteira, com volatilidade e correlação históricas (ou padrões por classe, quando falta histórico), percentis 10, 50 e 90 e probabilidade de perda. |
| `analytics/kpis.py`, `concentration.py` | Diversificação (`1/HHI`), concentração, contribuição por ativo, volatilidade anualizada, pior queda e faixa de 52 semanas. |
| `analytics/lookthrough.py` | Exposição às empresas **por trás dos ETFs**: peso do fundo multiplicado pelo peso da empresa no fundo, somado entre fundos. |
| `analytics/allocation.py`, `agenda.py`, `financial_health.py` | Distância até a alocação-alvo, vencimentos da renda fixa, meses de reserva e taxa de poupança. |
| `cashflow_engine/` | Saldo por conta, resumo mensal, quebra por categoria, **limpeza de descrição** (parcela, canal, códigos de transação), motor de regras e casamento de transferências e pagamentos de fatura. |
| `reconciliation/matcher.py` | Pares que parecem o mesmo evento, comparados campo a campo, com tolerância relativa no valor. |

---

## 📥 Importação de extratos e faturas

| Origem | Formato | Detecção | Observações |
|---|---|---|---|
| Corretora | CSV, XLSX, OFX | por extensão e conteúdo | Ativo, moeda e país são validados linha a linha. Um ticker que existe em dois países é recusado, nunca resolvido em silêncio. |
| Conta corrente (Nubank) | CSV, OFX | cabeçalho | O OFX traz o saldo. Na primeira importação, o sistema cria o saldo inicial que faz a conta bater com o banco. |
| Cartão (Nubank) | CSV, OFX, **PDF** | `%PDF-` / `<CCSTMTRS>` | O PDF é conferido contra o resumo da fatura e as datas sem ano são resolvidas pela data de emissão. Estornos, Pix no crédito parcelado e descontos de antecipação são tratados à parte. |

```mermaid
flowchart LR
    A["📄 Arquivo"] --> B["Parser puro"] --> C["Prévia<br/>erros · duplicados · regra"] --> D["Assinatura HMAC"] --> E["Commit atômico"] --> F["Regras aplicadas"] --> G["Transferências casadas"]
```

O arquivo em si não é guardado. Ficam só o nome e a impressão digital dele.

---

## 🤖 Integração com o Claude

O dashboard **não chama nenhuma IA**. A integração acontece por arquivos, numa pasta de troca:

```
claude-analises/
├── carteira.json          ← o backend grava: posições, pesos, KPIs, cenários, agenda, benchmarks, alocação
├── relatorios/
│   └── AAAA-MM-DD.json    ← a tarefa diária do Claude grava o "Jornal" (formato v4, validado pelo backend)
└── alertas/
    └── AAAA-MM-DD.json    ← a tarefa de hora em hora grava só quando há notícia de severidade ALTA/CRÍTICA
```

- Os prompts das tarefas agendadas estão versionados em
  [`backend/docs/agente-prompts/`](investimentos-codigo-cf1/backend/docs/agente-prompts/). Um teste
  garante que o prompt pede a versão mais nova do formato.
- O backend **valida** cada relatório. Arquivo fora do formato aparece como "recusado", com o motivo.
  Uma fração acima de 500% também recusa o arquivo, para pegar um "39" escrito no lugar de "0,39".
- O botão "Perguntar ao Claude" monta um link para `claude.ai/new` com o contexto da carteira
  (`GET /insights/chat-context`), limitado em tamanho. A conversa usa a assinatura do próprio usuário.

---

## 🔒 Segurança e privacidade

A API não tem login próprio, porque o sistema tem um único usuário. A fronteira de segurança é a
**rede**, e ela é fechada em camadas:

| Camada | Proteção |
|---|---|
| Rede | O backend escuta **só em `127.0.0.1`** e nunca é publicado. O celular chega ao frontend pela rede privada do Tailscale, e o Vite repassa `/api` para o backend local. |
| DNS rebinding | Há uma allowlist de `Host` no backend (`localhost`, `127.0.0.1`) e no Vite (`localhost`, `*.ts.net`). |
| CORS | Só a origem do próprio frontend pode ler as respostas. |
| Local × remoto | O proxy **sobrescreve** um cabeçalho com o host que o navegador usou. Qualquer sinal de encaminhamento torna a requisição remota, e a regra nega por padrão. |
| Acesso remoto | **Passkeys (WebAuthn)** com Face ID. O cadastro do aparelho usa um código de pareamento de 10 minutos, com uso único e bloqueio após 5 tentativas. A sessão fica em cookie `HttpOnly; Secure; SameSite=Strict`, e dá para revogar todos os aparelhos de uma vez. |
| Cabeçalhos | `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer` e `Permissions-Policy` restritiva. |
| Uploads | Teto de tamanho configurável (10 MB por padrão), e nenhum arquivo é persistido. |
| Dados externos | Só os tickers saem do computador (Yahoo Finance), além da série pública do CDI (Banco Central). |
| Repositório | Extratos, faturas, `.env`, bancos locais e a pasta de análises ficam fora do git (`.gitignore`). |

---

## 🔌 API

São 113 endpoints REST, documentados automaticamente pelo FastAPI em `http://127.0.0.1:8000/docs`
com o backend ligado.

| Grupo | Exemplos |
|---|---|
| Cadastros | `/institutions`, `/accounts`, `/portfolios`, `/assets`, `/currencies`, `/asset-classes` |
| Investimentos | `/transactions`, `/transactions/{id}/reverse`, `/transactions/{id}/correct`, `/transfers` |
| Importação | `/imports/preview`, `/imports/commit` |
| Painel | `/dashboard/summary`, `/overview`, `/dividends/summary`, `/performance/history`, `/performance/agenda`, `/performance/allocation` |
| Desempenho | `/performance/kpis`, `/performance/benchmarks`, `/performance/financial-health`, `/analytics/portfolio`, `/performance/widget` |
| Cotações | `/prices/latest`, `/prices/refresh`, `/assets/{id}/prices` |
| Caixa | `/cashflow/entries`, `/cashflow/summary`, `/cashflow/summary/categories`, `/cashflow/balances` |
| Classificação | `/cashflow/categories`, `/cashflow/tags`, `/cashflow/rules`, `/cashflow/rules/preview`, `/cashflow/rules/apply` |
| Importação de caixa | `/cashflow/imports/preview`, `/cashflow/imports/commit`, `/cashflow/inbox/process` |
| Reconciliação | `/reconciliation/scan`, `/reconciliation/pending`, `/reconciliation/{id}/comparison`, `/reconciliation/{id}/resolve` |
| Claude | `/insights`, `/insights/{data}`, `/insights/alerts`, `/insights/snapshot`, `/insights/lookthrough`, `/insights/chat-context` |
| Anotações | `/notes`, `/notes/{id}`, `/reading-sources`, `/reading-sources/{id}` |
| Acesso remoto | `/auth/status`, `/auth/pairing`, `/auth/register/*`, `/auth/login/*`, `/auth/passkeys`, `/auth/sessions/revoke-all` |

---

## 📁 Estrutura do repositório

```
.
├── Iniciar Dashboard.bat · Parar Dashboard.bat · Abrir widget.bat · ...   ← atalhos para Windows
├── docs/
│   ├── hero.svg · hero.en.svg              ← banner animado deste README
│   ├── gifs/                               ← animações (dados fictícios)
│   └── screenshots/                        ← imagens (dados fictícios)
└── investimentos-codigo-cf1/
    ├── backend/
    │   ├── app/
    │   │   ├── api/routers/                ← camada HTTP
    │   │   ├── services/                   ← orquestração, importadores e dados de mercado
    │   │   ├── domain/                     ← motores puros de cálculo
    │   │   ├── repositories/
    │   │   ├── models/ · schemas/
    │   │   └── core/                       ← configuração e detecção local/remoto
    │   ├── alembic/versions/               ← 18 migrações (triggers, enums, seeds)
    │   ├── tests/                          ← domain · services · api (Postgres real)
    │   ├── scripts/seed_demo.py            ← carteira de demonstração
    │   └── docs/                           ← decisões de cada fase e prompts do agente
    ├── frontend/
    │   └── src/
    │       ├── pages/ · pages/cash/        ← telas de investimentos e do caixa
    │       ├── components/                 ← overview, charts, cash, insights, mobile, security...
    │       ├── api/                        ← cliente tipado da API
    │       └── lib/                        ← formatação, privacidade e lógica de tela testável
    ├── launcher/                           ← iniciador CLI (só biblioteca padrão)
    └── widget/                             ← widget de área de trabalho (Tkinter)
```

---

## 🚀 Como rodar

### Pré-requisitos

- Python **3.12+**
- Node.js **20.19+ ou 22.12+** (exigência do Vite 8; desenvolvido no 24)
- PostgreSQL rodando em `localhost:5432` (desenvolvido e testado no 16)

### 1. Banco de dados

```sql
CREATE DATABASE investimentos_dev;
```

A URL padrão é `postgresql+psycopg://postgres:postgres@localhost:5432/investimentos_dev`. Para mudar,
copie [`backend/.env.example`](investimentos-codigo-cf1/backend/.env.example) para `backend/.env` e
ajuste `DATABASE_URL`.

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

### 4. (Opcional) Carteira de demonstração

Com o backend ligado num banco **vazio**:

```bash
cd investimentos-codigo-cf1/backend
python scripts/seed_demo.py
```

### Atalho no Windows

Depois de criar o banco, dê dois cliques em **`Iniciar Dashboard.bat`**. O iniciador cria o ambiente,
instala as dependências, aplica as migrações, liga tudo e abre o navegador. Para desligar, use
**`Parar Dashboard.bat`**.

```bash
python investimentos-codigo-cf1/launcher/dashboard.py iniciar [--widget] [--sem-navegador]
python investimentos-codigo-cf1/launcher/dashboard.py parar | carregar | celular | atalhos
```

---

## ✅ Testes e qualidade

| Parte | Testes | Comando |
|---|---|---|
| Backend | **1.375** | `cd investimentos-codigo-cf1/backend && pytest` |
| Frontend | **645** | `cd investimentos-codigo-cf1/frontend && npm test` |
| Iniciador | **69** | `cd investimentos-codigo-cf1/launcher && pytest` |
| Widget | **22** | `cd investimentos-codigo-cf1/widget && pytest` |

Lint e checagem de tipos do frontend: `npm run lint && npm run build`.

- Os testes do backend rodam contra **PostgreSQL real**, não SQLite, para exercitar os triggers, os
  enums e as constraints *deferred* que garantem a integridade. O banco de teste é criado e limpo
  pelos próprios testes.
- Os motores de domínio têm testes unitários puros. Services e API têm testes de integração com
  cenários de ponta a ponta: importar, classificar, casar transferências e conferir que a identidade
  contábil fecha.
- O leitor de fatura em PDF foi validado com 23 faturas reais, que não estão neste repositório. Os
  testes usam uma fatura sintética, gerada byte a byte em
  [`tests/fatura_pdf_helpers.py`](investimentos-codigo-cf1/backend/tests/fatura_pdf_helpers.py).

---

## 💬 Perguntas frequentes

<details>
<summary><b>Ele me diz o que comprar?</b></summary>
<br>
Não. Todas as análises, inclusive as do Claude, são leituras dos números da sua carteira. Os cenários
são um modelo estatístico, e as "ideias para estudar" são pontos de partida para pesquisa, com tese,
riscos e fontes. A interface deixa isso explícito.
</details>

<details>
<summary><b>Preciso dar a senha do banco para alguém?</b></summary>
<br>
Não. Você baixa o extrato ou a fatura no app do banco e importa o arquivo. Nada se conecta à sua conta.
</details>

<details>
<summary><b>Funciona sem internet?</b></summary>
<br>
Quase tudo. Cotações automáticas (Yahoo Finance) e a série do CDI (Banco Central) precisam de rede, e
só os códigos dos ativos saem do computador. Sem rede, a cotação manual continua funcionando.
</details>

<details>
<summary><b>Por que não uma planilha?</b></summary>
<br>
Porque planilha soma real com dólar sem reclamar, deixa apagar um lançamento sem rastro e não sabe
se a fatura que você colou bate com o resumo do banco. Aqui, essas regras ficam no banco de dados e
nos testes, não na boa vontade de quem digita.
</details>

---

## 🚧 Limitações conhecidas

- **Um único usuário, por desenho.** A aplicação foi feita para rodar no computador do dono, não
  como serviço multiusuário.
- **O controle financeiro lê o formato do Nubank** (conta e cartão). Outros bancos precisam de um
  parser novo em `services/cashflow_imports/`.
- **As cotações automáticas têm o atraso da fonte pública** (cerca de 15 minutos). Renda fixa e fundos
  têm cotação manual.
- **O acesso pelo celular depende do computador ligado** e do Tailscale nos dois aparelhos.
- **Os cenários são um modelo estatístico com premissas de longo prazo**, não uma previsão.

---

<p align="center">
  Feito por <b>Luis Fernando Freitas</b>, analista de dados<br>
  <a href="https://www.linkedin.com/in/luis-fernando-freitas-a3503b284/">LinkedIn</a> ·
  <a href="https://github.com/Lfafreitas">GitHub</a>
</p>
