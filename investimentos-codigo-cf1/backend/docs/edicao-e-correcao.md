# Edição e correção nas telas

Unidade pedida depois do primeiro uso real: cadastro errado não tinha
conserto, e correção/estorno de lançamento só existiam na API.

## Cadastros (`PUT` e `DELETE`)

`PUT` recebe o cadastro inteiro, com o mesmo corpo da criação.

| Cadastro | Muda sempre | Só muda sem uso | Exclusão |
|---|---|---|---|
| Instituição | nome, tipo, país | — | só sem contas |
| Carteira | nome | — | só sem contas vinculadas |
| Conta | nome, instituição, carteira, tipo dentro do livro de caixa | moeda; troca entre investimentos e caixa | só sem uso |
| Ativo | ticker, nome, classe, país | moeda | só sem uso |

"Uso" de uma conta: ter `Transaction`, ter `CashflowEntry`, ou ser
contraparte de uma transferência do livro de caixa. "Uso" de um ativo:
ter `Transaction` ou cotação.

Por que a moeda trava: os lançamentos foram gravados na moeda do ativo
e da conta (regra da Moeda-3). Por que o livro trava: uma corretora que
é contraparte de um aporte, se virasse conta de caixa, transformaria o
aporte em transferência interna com perna órfã. Essa última regra
também está no banco (migration `f1d8b3a6c2e9`).

Recusa por uso responde `409` com o motivo em texto; a tela mostra o
texto como veio.

## Lançamentos

- `POST /transactions/{id}/correct` (já existia): estorna o original e
  grava um novo com os valores corrigidos. Conta e ativo não mudam.
- `POST /transactions/{id}/reverse` (rota nova, regra já existente):
  marca como `REVERSED`, sem criar nada.

Os dois recusam perna de transferência e qualquer mudança que deixaria
o histórico inválido (ex.: estornar a compra que sustenta uma venda).
Nada é apagado: o lançamento antigo continua no histórico, riscado.

## Telas

- **Cadastros:** cada item tem Editar e Excluir. Editar carrega o item
  no formulário do bloco, que passa a salvar em vez de criar. Excluir
  pede confirmação na própria linha.
- **Lançamentos:** cada lançamento ativo tem Corrigir e Estornar.
  Corrigir abre o formulário preenchido, com o ativo travado. Estornar
  pede confirmação. Pernas de transferência e lançamentos revertidos
  não têm ação; conversão de câmbio só estorna.

## Fora desta unidade

Editar ou estornar transferência entre contas de investimento;
edição de cotação já informada (informar de novo a mesma data
substitui); telas do livro de caixa (CF-5).
