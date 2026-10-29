# Fatura-PDF — fatura do cartão em PDF (conferida) e em OFX

Migração `b4e8f2a6c1d9`: só acrescenta `NUBANK_CARD_OFX` e
`NUBANK_CARD_PDF` ao tipo `cashflow_import_profile`. Dependência nova
do backend: `pdfminer.six` (na pasta backend, `pip install -e .`).

## Perfis novos

| Perfil | Arquivo | Conta | Chave de duplicidade |
| --- | --- | --- | --- |
| `NUBANK_CARD_PDF` | PDF da fatura fechada | cartão de crédito | conteúdo + ordem (a mesma do CSV) |
| `NUBANK_CARD_OFX` | OFX da fatura (`<CCSTMTRS>`) | cartão de crédito | conteúdo + ordem (a mesma do CSV) |

Os dois são detectados sozinhos (`%PDF-` no começo; `<CCSTMTRS>` no
OFX). Origem gravada: `IMPORT_PDF` e `IMPORT_OFX`.

## Conferência antes de gravar (PDF)

A fatura traz o próprio resumo. Antes de a prévia existir, o app soma o
que leu e compara:

1. **compras**: tudo que não é pagamento — compras, parcelas, Pix no
   crédito parcelado (na seção "Pagamentos e Financiamentos"), estornos,
   "Crédito de Confiança", descontos de antecipação — tem de dar
   exatamente `Total de compras de todos os cartões` + `Outros lançamentos`;
2. **pagamentos**: as linhas `Pagamento em DD MMM` têm de dar exatamente
   `Pagamento recebido`.

Um centavo de diferença recusa o arquivo inteiro (400, com os dois
valores na mensagem). Nada é gravado. A prévia mostra as duas
conferências, o vencimento e o total a pagar.

Testado nas 23 faturas reais (dez/2024 a out/2026): todas conferem.

## Leitura

- Datas sem ano ("30 DEZ"): o ano sai da data de emissão; data que
  cairia mais de 10 dias depois dela é do ano anterior.
- `•••• 1234` (final do cartão) sai da descrição.
- `Pagamento em 31 MAR` vira `Pagamento recebido` — o texto do CSV/OFX e
  o que o casamento com o "Pagamento de fatura" da conta procura.
- `Estorno de X` fica com esse nome; a chave de duplicidade usa `X`, que
  é como o CSV escreve o estorno. Importar CSV e PDF do mesmo mês, em
  qualquer ordem, não duplica.
- `Saldo restante da fatura anterior` não é gasto novo: fica de fora.
- Linha com valor zero fica de fora.
- Linha datada sem valor legível recusa o arquivo.
- "Total a pagar" só é lido dentro do quadro RESUMO (a primeira página
  tem o mesmo rótulo nas simulações de parcelamento).

## OFX do cartão

O `FITID` se repete no arquivo real (o IOF de compra internacional usa
o da compra), então não serve de chave. O valor já vem no sinal do
livro. O `LEDGERBAL` é o saldo da fatura, não o do livro: não é usado
para saldo inicial.

## Limites conhecidos

- O Pix no crédito parcelado aparece no PDF como `Nome - Parcela 2/5` e
  no CSV como `Pix no Crédito - Nome - 2/5`, com um centavo de
  diferença: importar CSV e PDF do mesmo mês duplica essa linha.
- Faturas com parcelamento com juros: o "Total a pagar" do Nubank fica
  um centavo abaixo da soma das linhas. A conferência usa as linhas
  (que batem com "Total de compras"); o saldo do cartão no app pode
  ficar alguns centavos diferente do banco.
- Duas compras idênticas (mesmo texto, valor e dia) no dia do
  fechamento, uma em cada fatura, seriam vistas como a mesma.
- Fatura de outro banco, ou PDF com layout diferente: recusado (a
  conferência não fecha ou o cabeçalho não é reconhecido).
