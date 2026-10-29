# Edição-2 — excluir, restaurar e editar lançamentos

Pedido depois do primeiro uso real: faltavam os botões de excluir e de
editar lançamento. Decisão do usuário: **excluir com histórico** — o
lançamento sai da lista e dos saldos, mas nada é apagado do banco.

## Livro de caixa

| Ação | Rota | Regra |
|---|---|---|
| Excluir | `POST /cashflow/entries/{id}/reverse` (já existia) | ACTIVE → REVERSED. Transferência: as pontas vão juntas. |
| Restaurar | `POST /cashflow/entries/{id}/restore` | REVERSED → ACTIVE. Transferência: as pontas voltam juntas. Recusado (409) se o lançamento foi substituído por uma edição. |
| Editar | `POST /cashflow/entries/{id}/correct` | Só lançamento **manual** e que não seja transferência. O original fica excluído e um novo é gravado com `corrects_entry_id` apontando para ele. Natureza, categoria, tags e notas são copiadas (notas podem ser trocadas). |

Por que importado não é editado: data e valor vêm do extrato. Editar
faria o saldo deixar de bater com o banco, e reimportar não recriaria a
linha (a chave do banco continua ocupada). Para importado vale
Classificar ou Excluir.

Por que a versão antiga de uma edição não volta: contaria o mesmo fato
duas vezes. Para voltar aos valores antigos, edite a versão nova.

Migration `a7d3c9e5f1b2`:

- o trigger de imutabilidade passa a aceitar REVERSED → ACTIVE;
- coluna `corrects_entry_id` (fato, imutável; índice único: um
  lançamento é substituído uma vez só).

Nenhum dado existente é alterado.

## Telas

- **Controle financeiro → Lançamentos:** Editar (manual), Classificar,
  Transferência e Excluir em cada linha ativa; Restaurar nas excluídas.
  Filtro "Mostrar excluídos".
- **Investimentos → Lançamentos:** os botões Corrigir/Estornar passam a
  se chamar Editar/Excluir. A regra é a mesma de antes (o histórico do
  ativo precisa continuar válido). Restaurar ficou só no caixa: no livro
  de investimentos a exclusão participa da reconciliação, e voltar um
  lançamento exige revalidar a posição — fica para uma unidade própria.

## Carga dos extratos do Nubank

`Dashboard Financeiro\carga-inicial\carregar_extratos.py` importa os
.ofx de `..\extratos-nubank` pelo mesmo fluxo da tela, confere o saldo
de cada mês com o extrato e liga as aplicações/resgates RDB à Caixinha.
Ajustes que ele cria (todos com a marca `carga-extratos:` nas notas):

- saldo inicial da conta antes do primeiro extrato;
- rendimento da conta informado no extrato (`RENDIMENTO LIQUIDO`);
- acerto da Caixinha: rendimento acumulado + o que já estava guardado
  antes de jan/2025, para o saldo bater com o app do Nubank.

Qualquer outra diferença de saldo é só mostrada, nunca ajustada.
