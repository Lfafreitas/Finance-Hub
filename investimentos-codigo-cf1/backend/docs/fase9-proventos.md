# Fase 9 — Proventos

## Arquivos criados/alterados

```
app/schemas/dividends.py            (novo) DividendsSummary e schemas de quebra
app/services/dividends_service.py   (novo) agregação pura + orquestração com banco
app/api/routers/dividends.py        (novo) GET /dividends/summary
app/main.py                         (alterado) registra o router
pyproject.toml                      (alterado) + ignore DTZ011 do ruff (date.today(), consistente com datas naive do domínio)
tests/services/test_dividends_service.py   (novo) 14 testes puros
tests/api/test_dividends_api.py            (novo) 6 testes de API
```

Nenhum model, migration, trigger, `PositionCalculator` ou Financial Engine foi tocado. Frontend não foi alterado (fora do escopo, conforme sua decisão).

## Decisões implementadas

- **D-F1**: quebra por instituição via `Transaction → Account → Institution`, reaproveitando `get_institutions_by_id` (já existente desde a Fase 7) — sem endpoint de instituições novo.
- **D-F2**: endpoint dedicado `GET /dividends/summary?portfolio_id=`, fora do `DashboardSummary`.
- **D-F3 formalizado**: dois campos por moeda — `average_monthly` (total do período / meses corridos entre a 1ª e a última ocorrência) e `average_monthly_last_12_months` (total dos últimos 12 meses / 12, janela fixa). Testado o caso de um único mês (average_monthly = total daquele mês) e o de múltiplos meses.
- **D-F4**: `predicted: null` + `predicted_unavailable_reason` sempre presente, mesma filosofia da Fase 7/8.
- **D-F5**: filtro `portfolio_id` idêntico ao do `/dashboard/summary`.
- **`by_type` adicionado**: `DIVIDEND`/`JCP`/`INCOME` quebrados separadamente, por moeda.
- **Regra de moeda (nova)**: toda agregação (`by_month`, `by_year`, `by_asset`, `by_institution`, `by_type`, totais) é feita **por par (dimensão, moeda)** — nunca soma BRL com USD. `consolidated_total_received` só existe quando há exatamente uma moeda em todo o escopo; caso contrário, `null` + motivo nomeando as moedas envolvidas. Testado com um caso de duas moedas.

## "Últimos 12 meses" — definição explícita

Defini como os 365 dias corridos terminando na data de referência (inclusive), não aritmética de mês calendário — documentado no código para não deixar implícito. `reference_date` tem default `date.today()` mas pode ser passado explicitamente (usado nos testes, para não depender da data real do sistema).

## Observação não-bloqueante (não corrigida, conforme suas instruções)

`_accounts_in_scope` (resolução de escopo por `portfolio_id`, com validação de posse) já existe, idêntica, em `app/services/dashboard_service.py`. Duplicei a mesma lógica (pequena, ~8 linhas) em `dividends_service.py` em vez de extrair para um local compartilhado, para não tocar em código da Fase 7 sem necessidade nesta fase. Registro como possível extração futura (ex.: `app/services/scope_resolver.py`), não implementada agora.

## Testes executados

**Puros** (`tests/services/test_dividends_service.py`, sem Postgres, 14): totais básicos, consolidado com moeda única, moeda mista não consolidada, `by_month` nunca mistura moeda no mesmo valor, média mensal (1 mês e 3 meses), `average_monthly_last_12_months` sempre ÷12, janela de últimos 12 meses excluindo o que está fora, total no ano corrente, `by_type`/`by_asset`/`by_institution`/`by_year`, `predicted` sempre `None` com motivo, lista vazia.

**API** (`tests/api/test_dividends_api.py`, 6): totais + quebra por instituição real (join), isolamento de usuário, filtro por portfolio, portfolio inexistente (404), `REVERSED` excluído, moedas diferentes não consolidadas.

**Suíte completa de backend: 129 testes passando** (109 da Fase 8 + 20 novos, nenhum teste anterior alterado além do necessário — nenhum foi).

**Frontend**: 16 testes confirmados intactos (nenhum arquivo tocado).

## Lint/format

`ruff check .` e `black --check .` limpos.

## Achados durante a implementação

- `date.today()` disparou o lint `DTZ011` (recomenda timezone-aware) — como todo o domínio usa datas naive (`Transaction.transaction_date` é `Date`, sem timezone), usar timezone-aware aqui introduziria uma inconsistência sem benefício real; documentado e ignorado nas configurações do ruff, mesmo padrão do `B008` da Fase 6.
- Nenhuma inconsistência financeira/matemática nova encontrada — a implementação seguiu a especificação aprovada sem exigir nenhuma correção de meio de caminho.

## Confirmação

**Nenhuma fase posterior foi iniciada.** Nenhuma decisão das Fases 4–8 foi alterada. A revisão global de regressão mencionada por você fica para quando você decidir fazê-la — não a antecipei aqui.
