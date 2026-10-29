# Fase 4 — Banco de Dados: Arquitetura de Persistência

## 1. Fonte da verdade vs. dados derivados

| Categoria | Entidades | Regra |
|---|---|---|
| **Fonte da verdade** (implementadas nesta fase) | `User`, `Institution`, `Account`, `Asset`, `Transaction` | Escritas diretamente pelo usuário/importação. `Transaction` é a mais importante: representa o evento financeiro original e nunca é sobrescrita — correções viram novas transações de ajuste. |
| **Referência** (implementadas nesta fase, dado não financeiro) | `Currency`, `AssetClass` | Taxonomias/cadastros de apoio. Extensíveis via INSERT (migration de seed), não exigem mudança de schema para crescer. |
| **Derivadas/calculadas** (NÃO implementadas nesta fase — preparadas conceitualmente) | `Position`, `Portfolio` | Sempre recalculáveis do zero a partir de `Transaction`. Nunca serão a origem de um dado, só o resultado. |
| **Futuras, fora do escopo desta fase** | `Dividend`, `Quote`, `Goal`, `Integration`, `SyncLog`, `Reconciliation` | Cada uma entra na sua fase correspondente do roadmap, com FKs para `Account`/`Transaction`/`Asset` conforme necessário. |

## 2. Relacionamentos (implementados)

```
User (1) ──< Account (N) >── Institution (1)
                │
                ├──> Currency (moeda da conta)
                │
Account (1) ──< Transaction (N) >── Asset (0..1, nullable)
                                        │
                                        ├──> AssetClass
                                        └──> Currency
Transaction ──> Currency (moeda da transação)
```

- `User 1—N Account`: um usuário tem várias contas.
- `Institution 1—N Account`: uma instituição atende várias contas (de usuários diferentes). Uma mesma instituição pode ter múltiplas contas do mesmo usuário (ex.: XP-Ações e XP-Renda Fixa) — por isso o unique é `(user_id, institution_id, name)`, não `(user_id, institution_id)`.
- `Account 1—N Transaction`: uma conta acumula seu histórico de eventos.
- `Asset 0..1—N Transaction`: `asset_id` é **nullable** — aportes/retiradas de dinheiro puro não referenciam ativo nenhum. Isso é o que garante que `Transaction` não depende de nenhuma outra entidade de negócio complexa para existir.
- `Asset N—1 AssetClass`, `Asset/Account/Transaction N—1 Currency`: cadastros de apoio.

**Preparação explícita para o futuro** (não implementada agora, para não criar FK para tabela inexistente): `Account` receberá uma coluna `portfolio_id` (nullable) quando `Portfolio` for criado, na fase de múltiplas carteiras.

## 3. Decisões de schema e justificativas

- **Dinheiro/preço/quantidade**: `Numeric` (Decimal) em todos os campos monetários — nunca `Float`, que não representa valores decimais exatamente. `quantity`/`unit_price`: `NUMERIC(20,8)` (suporta ações fracionárias no exterior). `fees`/`gross_amount`: `NUMERIC(18,4)` (4 casas para não perder precisão em valores intermediários; arredondamento para exibição é responsabilidade da camada de apresentação, não do banco).
- **Enum nativo vs. tabela de referência**: `TransactionType`/`TransactionSource`/`InstitutionType` são enums Python/Postgres porque são contratos com o código (cada tipo de transação exigirá lógica própria no futuro Financial Engine). `AssetClass`/`Currency` são tabelas porque são taxonomia extensível sem precisar de deploy.
- **UUID como PK** em todas as tabelas de negócio (não serial incremental) — evita vazar contagem/ordem de criação e facilita merge futuro de dados vindos de importação/API sem colisão de IDs.
- **Unicidade de `Asset`**: `(ticker, country)`. Decisão simples e documentada como ponto de revisão futura caso surja ambiguidade entre bolsas do mesmo país.
- **Índice único parcial** em `Transaction (account_id, external_reference) WHERE external_reference IS NOT NULL`: previne duplicidade de importação (mesma transação vinda da mesma fonte duas vezes) sem afetar lançamentos manuais, que nunca têm referência externa.
- **Imutabilidade de `Transaction`**: garantida por convenção de aplicação nesta fase (não há API de escrita ainda). Ainda **não** há um trigger de banco bloqueando UPDATE em `quantity/unit_price/gross_amount/transaction_date` — fica como decisão pendente (seção 5).

## 4. Migrations

- `a4a19c4b23b7`: cria as 7 tabelas (schema completo desta fase).
- `c4d73ae6e83b`: seed de `currencies` (BRL, USD) e `asset_classes` (16 classes cobrindo os ativos BR/exterior do escopo original).
- Ciclo `upgrade → downgrade → upgrade` testado e funcional (ver seção 6). Correção aplicada: o autogenerate do Alembic não remove tipos ENUM do Postgres ao dropar tabelas — isso foi corrigido manualmente no `downgrade()` da primeira migration.

## 5. Imutabilidade e estorno (aprovado e implementado)

- Trigger de banco `trg_transactions_immutability` (função `enforce_transaction_immutability`) bloqueia `UPDATE` em qualquer campo financeiro de uma `Transaction` já persistida: `account_id, asset_id, transaction_type, quantity, unit_price, fees, gross_amount, currency_code, transaction_date, source, external_reference, reverses_transaction_id, created_at`.
- Campos sempre editáveis: `notes`, `updated_at`.
- Campo de estado controlado: `status` (`ACTIVE`/`REVERSED`), só permite a transição `ACTIVE -> REVERSED`.
- Fluxo de correção: (1) marcar original como `REVERSED`; (2) inserir nova `Transaction` com `reverses_transaction_id` apontando para a original. Nada é apagado ou sobrescrito — rastreabilidade total.
- Exceções do trigger usam `SQLSTATE 23000` (integrity_constraint_violation) para chegarem à aplicação como `IntegrityError`, não um erro genérico.
- Testado: 6 campos financeiros diferentes bloqueados, `notes` editável, `ACTIVE→REVERSED` permitido, `REVERSED→ACTIVE` bloqueado, fluxo de correção completo, `reverses_transaction_id` imutável após criado. Ciclo `upgrade → downgrade → upgrade` das 3 migrations validado.

## 6. Dívida documentada — identificação de Asset

Mantida a constraint `(ticker, country)` para o MVP, conforme aprovado. Registrado como expansão futura: identificar ativos também por *exchange*/mercado e por código ISIN, caso apareça um caso real de colisão de ticker dentro do mesmo país.

## 7. Pontos que ainda precisam de decisão futura

1. `portfolio_id` em `Account`: será adicionado só quando `Portfolio` existir (fase de múltiplas carteiras) — confirmado, nada a fazer agora.
2. Identificação de `Asset` por exchange/ISIN: fica como dívida documentada acima, sem ação agora.
