# Visual novo, agenda, referência, alocação-alvo e proventos

## Visual — "tinta de extrato"

- Fundo grafite com leve tom azul-esverdeado; um acento azul-gelo só para
  o que está selecionado e o foco do teclado. Verde/vermelho/âmbar só
  para sinal, sempre com texto ou sinal junto.
- Fonte IBM Plex Sans **instalada junto com o app** (pacote
  `@fontsource/ibm-plex-sans`): nada é buscado na internet ao abrir.
  Ao atualizar, o "Iniciar Dashboard" roda `npm install` sozinho.
- A escala `neutral-*` do Tailwind foi redefinida em `src/index.css`, então
  todas as telas mudaram juntas. Paleta dos gráficos revalidada contra o
  fundo novo (#141b1f): luminosidade, croma, daltonismo e contraste passam.
- Visão geral na ordem da leitura rápida: patrimônio → o que pede atenção →
  leitura do Claude → evolução → referência → agenda → alocação →
  indicadores → detalhe.

## Agenda (`GET /performance/agenda`)

- Cadastro do ativo de renda fixa (CDB, LCI, LCA, Tesouro, debênture, bond)
  ganhou **vencimento** e **taxa ao ano**. Edição de tela antiga, sem esses
  campos, mantém o que estava; trocar a classe para não-renda-fixa apaga.
- Vencimentos em ordem de data, com dias que faltam. Vencido ainda na
  carteira aparece com aviso para conferir.
- "≈ no vencimento": juros compostos da taxa, desde a primeira compra, sobre
  o custo, base 365. É estimativa: sem imposto, IOF ou convenção do emissor.
- Proventos recebidos nos últimos 12 meses, mês a mês, por moeda (usa o
  resumo de proventos que já existia).

## Comparação com a referência (`GET /performance/benchmarks`)

- Pergunta: "se cada aporte tivesse ido para a referência, no mesmo dia e
  valor, quanto eu teria hoje?". Dólar → SPY; reais → CDI.
- Aporte = compra (quantidade × preço + taxas); venda tira (quantidade ×
  preço − taxas). Proventos não entram: SPY também é só preço.
- Dia sem pregão usa o último nível anterior; aporte antes da primeira
  cotação da referência → a comparação não aparece e a tela diz o que falta.
- CDI: série 12 do Banco Central (% ao dia), baixada junto com "Atualizar
  cotações" quando há investimento em reais. Só o período sai do
  computador. A taxa do dia D rende de D para o dia útil seguinte. Falha do
  Banco Central não desfaz as cotações (`cdi_status` diz o que houve).

## Alocação-alvo (`GET /performance/allocation`, `PUT /performance/allocation/{moeda}`)

- O usuário define o peso-alvo por classe em cada moeda (soma 100%; lista
  vazia apaga). Classe com posição e sem alvo, quando há alvos, conta como
  alvo zero.
- A tela mostra o peso atual, o alvo (traço branco) e a distância em p.p. e
  em valor. Até 2 p.p. conta como "no alvo". É régua dele, não recomendação.

## Resultado com proventos

- Por ativo: (resultado + proventos recebidos) / custo. Da carteira: o mesmo,
  só quando todas as posições têm cotação.

## Retrato para o Claude (`carteira.json`)

Ganhou `agenda`, `benchmarks` (sem a série diária) e `allocation`. O prompt
da análise diária usa esses campos.
