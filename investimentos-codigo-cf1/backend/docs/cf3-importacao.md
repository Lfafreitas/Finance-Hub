# CF-3 — Importação do extrato e da fatura

Lê os arquivos do Nubank para o livro de caixa. A importação de
investimentos (`/imports`, `ofx_parser`) não foi tocada: são dois
fluxos separados, um por livro.

## Perfis

Cada perfil foi escrito contra um arquivo real (CF-0, seções 13 e 14).
Sem `profile` no pedido, o formato é detectado pelo conteúdo.

| Perfil | Arquivo | Conta | Chave de deduplicação |
|---|---|---|---|
| `NUBANK_ACCOUNT_CSV` | `Data,Valor,Identificador,Descrição` | corrente, reserva, dinheiro | identificador do banco |
| `NUBANK_ACCOUNT_OFX` | OFX 1.x, `<STMTTRN>` | corrente, reserva, dinheiro | o mesmo identificador (`FITID`) |
| `NUBANK_CARD_CSV` | `date,title,amount` | cartão de crédito | conteúdo + ordem de ocorrência |
| `NUBANK_CARD_OFX` | OFX `<CCSTMTRS>` | cartão de crédito | conteúdo + ordem (ver `fatura-pdf.md`) |
| `NUBANK_CARD_PDF` | PDF da fatura, conferido com o resumo | cartão de crédito | conteúdo + ordem (ver `fatura-pdf.md`) |

- Arquivo de cartão em conta que não é cartão (e o contrário) é
  recusado.
- Na fatura a compra vem positiva; o importador inverte o sinal.
- Uma linha ilegível não derruba o arquivo: sai com `error` e não pode
  ser importada.

## Deduplicação

- **Conta:** o banco dá um identificador a cada linha, igual no CSV e no
  OFX. Reimportar o mês, ou importar um formato depois do outro, não
  duplica.
- **Cartão:** não há identificador. A chave é o hash de (conta, data,
  título normalizado, valor) mais a posição entre as linhas idênticas do
  arquivo — duas compras iguais no mesmo dia são duas linhas.
- Lançamento estornado continua contando: reimportar não recria o que
  você estornou.

As duas chaves são índices únicos no banco, e os três campos de origem
(`external_id`, `import_fingerprint`, `import_batch_id`) são fato —
imutáveis pelo mesmo trigger do resto do lançamento.

## Prévia e commit

Mesmo desenho da importação de investimentos:

1. `POST /cashflow/imports/preview` lê o arquivo e devolve as linhas,
   com duplicatas e erros marcados e a regra que classificaria cada uma.
   **Não grava nada.** A resposta é assinada (HMAC).
2. `POST /cashflow/imports/commit` recebe a prévia intacta e as linhas
   escolhidas. Qualquer alteração de data, valor, descrição,
   identificador, erro ou marca de duplicata invalida a assinatura.
   **Tudo ou nada:** se uma linha falhar, o lote inteiro é desfeito.

Depois de gravar, na mesma operação:

1. pagamentos de fatura são casados (ver abaixo);
2. as regras são aplicadas **só aos lançamentos novos**.

O arquivo não é guardado. Fica um registro do lote com o nome, o hash
(`file_sha256`), o período e os números. O hash serve para avisar "este
arquivo já foi importado nesta conta".

## Saldo

O OFX informa o saldo final. O resultado do commit devolve o saldo do
sistema na mesma data e a diferença; zero quer dizer que a conta bate
com o banco.

`create_opening_adjustment` cria o lançamento de **saldo inicial** que
faz a conta bater, e só é aceito quando:

- o arquivo informa saldo (OFX);
- a conta ainda não tem nenhum lançamento;
- todas as linhas válidas do arquivo foram incluídas.

O CSV da conta e a fatura do cartão não informam saldo. Para o cartão,
o saldo só fica certo importando as faturas desde o início ou lançando
um ajuste à mão.

## Pagamento de fatura

O extrato da conta traz `Pagamento de fatura` (saída) e a fatura traz
`Pagamento recebido` (entrada). São as duas pontas de uma transferência
conta → cartão, e nos arquivos reais têm o mesmo valor e o mesmo dia.

O casamento automático exige: mesma instituição, mesma moeda, valores
que se anulam, no máximo 3 dias entre as datas, e **nenhuma
ambiguidade** — cada ponta com exatamente uma candidata. Dois
pagamentos iguais na mesma janela ficam para decisão manual.

Roda a cada commit e por `POST /cashflow/transfers/match` (por padrão
só mostra). Nunca toca em lançamento classificado à mão; sobrepõe o que
uma regra de texto tenha classificado, porque o casamento exato vale
mais que um padrão de texto.

## Ligar transferências à mão

`POST /cashflow/entries/{id}/transfer`, com um dos dois:

- `counterparty_entry_id`: o lançamento da outra ponta. Contas
  diferentes, mesma moeda, valores que se anulam, até 10 dias entre as
  datas.
- `investment_account_id`: uma conta de investimentos. Saída vira
  aporte, entrada vira resgate; fica uma perna só.

`DELETE /cashflow/entries/{id}/transfer` desfaz: as pernas voltam a não
classificado. Nos dois sentidos nenhum fato muda.

Não existe transferência para uma conta de caixa que não é importada
(outro banco sem extrato): sem a segunda perna o caixa não fecharia.
Esse dinheiro fica como você classificar — renda, gasto ou terceiros.

## Fora desta unidade

- Reconhecer conta própria automaticamente (decidido não guardar o CPF
  do titular).
- Faturas e extratos de outros bancos (XP, Inter, C6, Itaú): cada um é
  um perfil novo, a escrever quando houver um arquivo real.
- Telas (CF-5).
