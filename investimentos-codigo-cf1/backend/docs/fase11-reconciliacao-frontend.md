# Fase 11 — Frontend de reconciliação (+ revisão geral)

Estado ao fim da fase. O código é a fonte da verdade; este arquivo só
registra o que existe e por quê.

## API nova

| Endpoint | O que faz |
|---|---|
| `GET /transactions/{id}` | Transaction isolada, com `source`. 404 genérico para inexistente/alheia. |
| `GET /reconciliation/{id}/comparison` | Comparação campo a campo do par, recalculada por `compare_transactions` + `classify` (nunca `match()`). Funciona em qualquer status do log. `match_reason` é o texto guardado no log. Valores já em string posicional (nunca notação científica). |
| `POST /reconciliation/scan` | Casca sobre `scan_for_reconciliation`. Corpo opcional: `{}`, `{account_id}` ou `{portfolio_id}`. Resposta: `{created_count, created}`. |

## Frontend

- `App.tsx`: navegação por estado local entre Dashboard e Reconciliação (sem `react-router-dom`).
- `pages/Reconciliation.tsx`: lista de pendências, detalhe do par, scan manual. A lista nunca é
  atualizada de forma otimista: depois de resolver ou escanear, busca de novo no backend.
- `components/ReconciliationDetail.tsx`: duas Transactions (origem de cada lado) + tabela campo a campo.
  Igualdade e diferenças vêm prontas do backend — o frontend só exibe.
- `components/ReconciliationActions.tsx`: IGNORE / KEEP_BOTH / MERGE. MERGE só habilita com a
  sobrevivente escolhida; toda decisão passa por confirmação; erros 400/404/409/422 têm mensagem própria.
- `components/ReconciliationScanPanel.tsx`: scan com os três escopos.
- `api/client.ts`: `request` aceita método e corpo; erros viram `ApiError` (`status`, `detail`).

## Correções feitas nesta fase fora do escopo original

1. `correct_transaction` valida o histórico resultante com o `PositionCalculator`, usa lock de linha e
   SAVEPOINT (`CorrectionInvalidatesHistoryError`, HTTP 400).
2. `scan_for_reconciliation` cria cada log via `_create_reconciliation_log_safe` (SAVEPOINT): um par
   registrado por outro processo durante o scan não derruba o scan.
3. `Transaction.linked_transaction_id` declara a FK como deferrable no model — `alembic check` limpo.
4. Validação de coerência dos campos por tipo em todo ponto de entrada (`InvalidTransactionDataError`,
   HTTP 400): BUY/SELL exigem ativo, quantidade > 0 e preço; valores/taxas nunca negativos; eventos
   societários exigem quantidade com o sinal da convenção; DEPOSIT/WITHDRAWAL/FX_CONVERSION sem ativo.
5. `PositionCalculator`: a venda que zera a posição remove exatamente todo o custo remanescente
   (antes sobrava um resíduo de arredondamento como `1E-26`, às vezes negativo, que chegava a virar
   uma fatia de 100% na alocação de uma carteira já zerada).
6. Importação: `error` da linha entra no conteúdo assinado pelo HMAC; upload limitado
   (`IMPORT_MAX_UPLOAD_BYTES`); XLSX aceita células de data nativas do Excel.
7. Borda: `TrustedHostMiddleware` (`ALLOWED_HOSTS`) e CORS restrito (`CORS_ALLOWED_ORIGINS`); a
   aplicação não sobe fora de development/test com o segredo HMAC padrão.

## Pendências que dependem de decisão

- (Resolvido) Dashboard somava moedas diferentes: Moeda-1 (backend) e Moeda-2 (frontend).
- (Resolvido na Moeda-3) moeda da transação diferente da moeda do ativo. A moeda da conta continua livre para movimentos sem ativo.
- Nenhum fluxo marca um `ReconciliationLog` como `STALE` quando uma Transaction do par é revertida
  por outro caminho.
- `check_batch_after_import` segue sem timeout/limite de lote.
- `gross_amount` não é conferido contra `quantity * unit_price` (o engine usa o produto; o campo
  bruto só é usado em proventos, taxas avulsas, aportes e na reconciliação).
