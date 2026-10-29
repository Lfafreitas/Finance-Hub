# CF-2 — Categorias, tags e regras de classificação

Tudo nesta unidade é **classificação**: nada altera o fato de um
lançamento (conta, data, valor, moeda, descrição, origem).

## Categorias

Árvore de até **dois níveis** (categoria e subcategoria), por usuário.
O limite é garantido no banco por trigger. Nome é único dentro do
mesmo nível (duas raízes não repetem nome; duas filhas do mesmo pai
também não).

Categoria só é excluída sem uso: sem subcategorias, sem lançamentos e
sem regras apontando para ela.

`POST /cashflow/categories/defaults` cria o que faltar da árvore
inicial — 15 categorias e 14 subcategorias derivadas do histórico real
(CF-0, seção 6). É idempotente e nunca mexe no que já existe. Nada é
criado sozinho.

Transferência não tem categoria (CHECK no banco).

## Tags

Marcador livre, ortogonal à categoria, com um `tag_group` opcional
para separar dimensões — no histórico real, as duas que apareceram
foram **beneficiário** (pessoa) e **canal** (compra online). Excluir
uma tag só a remove dos lançamentos e das regras.

## Como a descrição é lida

`parse_description` (puro, em `app/domain/cashflow_engine/description.py`)
transforma o texto do banco nos pedaços que as regras usam. Os formatos
foram verificados nos arquivos reais do Nubank.

| Texto do banco | `match_text` | Outros campos |
|---|---|---|
| `Dm*Spotify P46c9` | `spotify` | — |
| `Ebn *Spotify` | `spotify` | — |
| `Loja Grande - NuPay - Parcela 5/6` | `loja grande` | parcela 5/6, canal NuPay |
| `Amazonmktplc*Lojinha - Parcela 3/5` | `amazonmktplc lojinha` | parcela 3/5 |
| `99food *Loja X` | `99food loja x` | — |
| `Bus Tarifa*123456789` | `bus tarifa` | — |
| `Compra no débito - SUPER CENTRAL` | `compra no debito super central` | movimento |
| `Transferência enviada pelo Pix - Nome - CPF - Banco (cód) Agência…` | `transferencia enviada pelo pix nome` | movimento, documento, instituição |

Passos, todos determinísticos:

1. minúsculas, sem acento, espaços colapsados;
2. sufixo de parcela (`- Parcela n/t` ou `- n/t`) vira campo;
3. sufixo de canal (`- NuPay`) vira campo;
4. prefixo de **intermediador de pagamento** antes do `*` é removido
   (`mp`, `dm`, `pg`, `pag`, `ebn`, `zp`, `evo`, `ec`, `mlp`, `nuv`,
   `app`, `pagseguro`). Marketplace e aplicativo ficam, porque neles o
   prefixo é a parte útil;
5. código colado no fim é removido (só dígitos com 4+ caracteres, ou
   letras e dígitos misturados com 5+ caracteres e 2+ dígitos). O
   primeiro token nunca é removido;
6. em linha de extrato de conta, documento e instituição são separados
   do nome pela posição do documento.

Cada lançamento devolvido pela API traz o seu `match_text`, para ser
possível ver exatamente o que uma regra enxerga.

## Regras

Uma regra tem:

- **condição:** `pattern` comparado ao `match_text` por `CONTAINS`
  (padrão), `EQUALS` ou `STARTS_WITH`; opcionalmente o sentido (`IN`
  entrada, `OUT` saída) e uma conta;
- **efeito:** uma natureza (obrigatória; nunca `TRANSFER` nem
  `UNCLASSIFIED`), e opcionalmente categoria e tags.

**A primeira regra ativa que casa decide sozinha**, na ordem de
`priority` (menor primeiro) e, em empate, da mais antiga. Regras não se
combinam. Assim todo lançamento classificado por regra tem **uma**
regra que o explica, guardada em `classified_by_rule_id`.

Por que a natureza é obrigatória: uma regra que só desse categoria
deixaria o lançamento fora de gasto e de renda sem que isso ficasse
visível.

### Aplicação

`POST /cashflow/rules/preview` mostra o que mudaria; `POST
/cashflow/rules/apply` grava. As duas devolvem a mesma lista.

Quem é avaliado:

| Lançamento | Padrão | Com `reevaluate` |
|---|---|---|
| Não classificado (natureza `UNCLASSIFIED`, sem categoria, sem regra) | sim | sim |
| Classificado por regra | não | sim, do zero |
| Classificado à mão | **nunca** | **nunca** |
| Transferência ou estornado | **nunca** | **nunca** |

"Do zero" quer dizer que, se nenhuma regra casa mais, o lançamento
volta a não classificado e perde as tags que a regra tinha posto.

Qualquer classificação manual (`PUT .../nature` ou `PUT
.../classification`) zera `classified_by_rule_id`: a partir dali é
decisão sua e nenhuma regra mexe. Excluir uma regra tem o mesmo efeito
sobre o que ela classificou — a classificação fica, só deixa de
apontar para a regra.

## Quebra por categoria

`GET /cashflow/summary/categories?start&end`, por moeda. Só `EXPENSE`
e `INCOME` entram. Cada linha traz o que é da própria categoria
(`own_*`) e o total com as subcategorias (`total_*`); há uma linha
"sem categoria".

A soma dos `own_expenses` é conferida contra o `expenses` do resumo do
mesmo período antes de responder; se não fechar, nenhum número é
devolvido.

## API

| Rota | O que faz |
|---|---|
| `GET/POST /cashflow/categories`, `PUT/DELETE /cashflow/categories/{id}` | categorias |
| `POST /cashflow/categories/defaults` | árvore inicial |
| `GET/POST /cashflow/tags`, `PUT/DELETE /cashflow/tags/{id}` | tags |
| `PUT /cashflow/entries/{id}/classification` | natureza, categoria e tags, à mão |
| `GET/POST /cashflow/rules`, `PUT/DELETE /cashflow/rules/{id}` | regras |
| `POST /cashflow/rules/preview`, `POST /cashflow/rules/apply` | aplicar regras |
| `GET /cashflow/summary/categories` | quebra por categoria |

## Fora desta unidade

- Reconhecer transferência entre contas próprias pelo CPF do titular e
  casar pagamento de fatura com a fatura (CF-3). Uma regra de texto não
  distingue "recebi de terceiro" de "recebi de mim mesmo em outro
  banco" — as duas linhas têm o mesmo formato.
- Persistir os campos lidos da descrição (documento, instituição,
  parcela): hoje são recalculados a cada leitura (CF-3).
- Telas (CF-5).
