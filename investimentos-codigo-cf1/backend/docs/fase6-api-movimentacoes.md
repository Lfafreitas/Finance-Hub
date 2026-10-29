# Fase 6 — API de Movimentações

## Camadas criadas

```
app/schemas/transaction.py        TransactionCreate, TransactionRead, TransferCreate, TransferRead, PositionRead
app/services/exceptions.py        exceções de domínio (routers só traduzem, nunca reimplementam a regra)
app/services/transaction_service.py   toda a regra de negócio: posse de conta, D-A3 (SELL), transferência atômica, correção/estorno
app/api/deps.py                   get_current_user_id (D-A1) + re-export de get_db
app/api/routers/transactions.py   endpoints — só chamam o service e traduzem exceção -> HTTP
app/repositories/transactions.py  + list_transactions (histórico completo, distinto de get_active_transactions)
app/db/session.py                 + get_db() (commit no sucesso, rollback na exceção — garante atomicidade da transferência)
app/core/config.py                + single_user_email
app/main.py                       registra o router
pyproject.toml                    + ignore B008 do ruff (Depends() em default é o padrão do FastAPI, não bug)
```

## Decisões implementadas

- **D-A1 (usuário sem autenticação real)**: `get_current_user_id` resolve o usuário a partir de `settings.single_user_email`, nunca de um parâmetro do cliente. Toda checagem de posse de conta usa esse `user_id` resolvido — trocar para autenticação real no futuro significa mudar só essa função, nenhum router/service.
- **D-A2 (transferência atômica)**: `POST /transfers` cria as duas pernas na mesma sessão; os triggers `DEFERRED` da Fase 5 são forçados com `SET CONSTRAINTS ALL IMMEDIATE` dentro do próprio `create_transfer`, para que qualquer violação vire um erro de domínio traduzido em HTTP antes da resposta — não dependemos do commit final do request para descobrir um problema.
- **D-A3 (SELL validado antes de persistir)**: `_check_sell_against_position` chama `get_active_transactions` + `PositionCalculator` antes do INSERT; rejeita com `InsufficientPositionError` (→ 400) se a quantidade exceder a posição atual.
- **D-A4 (correção atômica)**: `correct_transaction` marca a original `REVERSED` e cria a nova transação com `reverses_transaction_id` na mesma sessão.
- **Sem transferência parcialmente persistida**: garantido por `get_db` só commitar se o request inteiro terminar sem exceção, mais o `SET CONSTRAINTS ALL IMMEDIATE` acima.
- **Mesma conta rejeitada**, **moedas diferentes fora do escopo** (`CrossCurrencyTransferError`), **origem/destino do mesmo usuário** — todos no `create_transfer`.
- **Financial Engine inalterado** — o service só chama `PositionCalculator`/repositório, nunca modifica a lógica pura.
- **Regra de negócio só no service** — os routers (`app/api/routers/transactions.py`) só fazem `try/except` mapeando exceção → status HTTP via um dicionário único.

## Endpoints disponíveis

| Método | Rota | Descrição |
|---|---|---|
| POST | `/transactions` | Cria transação manual (não aceita `TRANSFER_OUT`/`IN` — rejeitado pelo schema) |
| POST | `/transfers` | Cria as duas pernas de uma transferência atomicamente |
| POST | `/transactions/{id}/correct` | Estorna a original + cria a corrigida |
| GET | `/accounts/{account_id}/transactions` | Histórico completo (ACTIVE + REVERSED), filtro opcional `asset_id` |
| GET | `/accounts/{account_id}/positions/{asset_id}` | Posição calculada (ou `null` se não há histórico) |
| GET | `/health` | Já existente (Fase 3) |

## Testes novos (18)

- `tests/api/test_transactions_api.py` (13): depósito simples, `TRANSFER_OUT` rejeitado neste endpoint (422), conta de outro usuário (404), conta inexistente (404), SELL acima da posição (400) e dentro da posição (201), transferência atômica com vínculo bidirecional confirmado na resposta, mesma conta (400), conta de outro usuário na transferência (404), correção completa (original preservada + nova ligada), corrigir já-revertida (409), consulta de posição existente e inexistente (`null`).
- `tests/services/test_transaction_service.py` (5): conta inexistente no service, transferência entre moedas diferentes, mesma conta no service, correção tentando mudar de conta, correção de perna de transferência (ambas rejeitadas).

## Suíte completa

**85 testes passando** (67 da Fase 5 intactos + 18 novos). `ruff check .` e `black --check .` limpos. Nenhuma migration foi necessária (Fase 6 é só camada de aplicação, sem mudança de schema).

## Problemas encontrados durante a implementação

- Dois testes meus tinham asserção errada sobre a string exata devolvida pelo Postgres para colunas `NUMERIC` (`"100.00"` vira `"100.0000"` na coluna de 4 casas, `"100"` vira `"100.00000000"` na de 8) — corrigido nos próprios testes, não é um bug de aplicação, é o comportamento correto de `NUMERIC` de precisão fixa.
- Ruff acusou `B008` (chamada de função em default de argumento) nos usos de `Depends(...)` — é o padrão idiomático do FastAPI, não um bug; adicionado `ignore = ["B008"]` à configuração do ruff, com o motivo documentado no `pyproject.toml`.

## Confirmação

**Fase 7 não foi iniciada.** Nenhum código de Dashboard, agregação de patrimônio ou qualquer funcionalidade além do escopo aprovado da Fase 6 foi tocado.
