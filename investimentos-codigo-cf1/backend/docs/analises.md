# Análises-1 e Análises-2 — análises da carteira e o Claude no dashboard

## Análises-1: cotações automáticas e análises

### Cotações automáticas

- `POST /prices/refresh` busca, na fonte pública de gráficos do Yahoo
  Finance, um ano de fechamentos diários de cada ativo com transação
  ativa nas suas contas, e grava como cotação de fonte `YAHOO`.
- **Só o código do ativo sai do computador** (`SPY`, `PETR4.SA`...).
- O preço do pregão em andamento substitui a barra do dia: com a tela
  aberta, o número acompanha o mercado com o atraso da fonte (cerca de
  15 minutos). Não é o tempo real de uma corretora.
- Classes com fonte: ações e ETFs (BR e EUA), FII, REIT, BDR e cripto.
  Renda fixa e fundos voltam como `UNSUPPORTED`: a cotação continua
  manual.
- Nada é gravado quando a fonte responde outra moeda, preço não
  positivo, data futura ou formato inesperado. Falha em um ativo não
  impede os outros.
- **Cotação manual vence a automática na mesma data.** Em datas
  diferentes, vale a mais recente.
- Migração `d2e7a1b9c4f3`: `price_source` ganha `YAHOO`.

### `GET /analytics/portfolio`

Parte do mesmo resumo do dashboard. Por moeda (nunca somadas):

- **Concentração**: pesos por ativo, classe e conta. Base: valor de
  mercado quando toda posição aberta tem cotação; senão, custo (e a
  resposta diz). Sinais: um ativo acima de 40%; os 3 maiores acima de
  75% (com mais de 3 ativos); tudo numa classe só.
- **Cenários** até `until` (padrão 31/12): modelo lognormal da carteira.
  - Volatilidade de cada ativo pelo histórico real quando há 60 retornos
    diários ou mais; senão, padrão da classe. A resposta diz qual.
  - Correlação medida nas datas comuns; senão, padrão por grupo.
  - Retorno esperado é premissa de longo prazo (USD: ações 7%, imóveis
    6%; BRL: ações 10%, imóveis 9%), não previsão.
  - Pessimista/otimista = percentis 10 e 90; realista = mediana; e a
    chance de terminar abaixo de hoje.
  - Renda fixa e posições sem cotação ficam fora, listadas com o motivo.
- **Ritmo de aporte**: aporte é o mesmo do dashboard (depósitos,
  retiradas e transferências de fora). Por mês no ano, e projeção até
  dezembro em três ritmos: média do ano (desde o primeiro mês com
  aporte), últimos 3 meses e o mês atual.
- **Alertas**: posição sem cotação e cotação com mais de 7 dias.

### Tela Análises

Investimentos → Análises. Ao abrir, se a cotação automática tiver mais
de 15 minutos, busca de novo; com a tela aberta, busca a cada 15
minutos. Botão "Atualizar cotações agora".

## Análises-2: o Claude no dashboard

O backend roda só no seu computador e não fica exposto na internet, então
a tarefa agendada do Claude não chama a API. A troca é por uma pasta,
`Dashboard Financeiro/claude-analises` (configurável por `INSIGHTS_DIR`):

| Arquivo | Quem escreve | Conteúdo |
|---|---|---|
| `carteira.json` | o backend | retrato da carteira: ativos, quantidades, custos, valores, pesos, cenários, ritmo de aporte |
| `relatorios/AAAA-MM-DD.json` | o Claude | a análise do dia |

- O retrato é regravado ao abrir "Notícias e análises" e depois de cada
  busca de cotações. Não leva nome, documento nem número de conta.
- `GET /insights` devolve a análise mais recente, o histórico e os
  arquivos recusados. `GET /insights/{data}` abre um dia.

### Formato do relatório (versão 1)

```json
{
  "schema_version": 1,
  "generated_at": "2026-10-09T08:00:00-03:00",
  "headline": "frase única",
  "summary": ["parágrafo", "..."],
  "holdings": [
    {"ticker": "QQQ", "signal": "ATENCAO", "reading": "texto",
     "metrics": [{"label": "P/L", "value": "29,4", "context": "mediana 23,2"}],
     "sources": [{"title": "Fonte", "url": "https://..."}]}
  ],
  "news": [
    {"ticker": "SPY", "topic": "Mercado", "title": "...", "source": "...",
     "url": "https://...", "published_at": "2026-10-08", "summary": "..."}
  ],
  "research": [
    {"house": "BlackRock Investment Institute", "title": "...", "url": "https://...",
     "published_at": "2026-10-06", "summary": "...", "relevance": "..."}
  ],
  "watch": [{"topic": "Reunião do Fed", "why": "...", "date": "2026-10-28"}],
  "disclaimer": "..."
}
```

Regras que o backend confere (arquivo fora delas é recusado e aparece
na tela com o motivo):

- campo desconhecido recusa o arquivo; `schema_version` só 1;
- `signal`: `POSITIVO`, `NEUTRO` ou `ATENCAO` — nunca ordem de compra
  ou venda;
- links só `http://` ou `https://`;
- limites: resumo de 1 a 8 parágrafos de até 2000 caracteres; até 40
  ativos, 40 notícias, 20 relatórios, 15 itens a acompanhar; arquivo de
  até 512 KB;
- nome do arquivo `AAAA-MM-DD.json` com data válida.

A tela mostra tudo como texto (nada é interpretado como HTML) e abre
links em outra aba sem acesso à página.

## Fora destas unidades

- Renda fixa com taxa e vencimento (os CDs em dólar do Inter): hoje fica
  fora dos cenários.
- Leitor dos PDFs do Inter (notas de corretagem e extrato mensal).
- Índices de referência (CDI, IPCA, S&P 500) para comparar rentabilidade.
- Premissas de retorno editáveis na tela.
