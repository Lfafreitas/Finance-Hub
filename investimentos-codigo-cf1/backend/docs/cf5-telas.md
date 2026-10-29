# CF-5 — Telas do controle financeiro

Até aqui o livro de caixa só existia na API. Esta unidade põe tudo o que
já estava pronto (CF-1, CF-2, CF-3) em telas, e acrescenta à API só o
que as telas precisavam para funcionar.

## Navegação

Dois níveis, ainda por estado local (sem rotas):

- **Investimentos** — Dashboard, Lançamentos, Importar, Cotações,
  Reconciliação. Nada mudou dentro delas.
- **Controle financeiro** — Resumo, Lançamentos, Importar extrato,
  Categorias, Regras.
- **Cadastros** — usado pelos dois livros.

Cada área lembra a tela em que estava. Nada do livro de caixa é buscado
antes de a área ser aberta.

## Telas

### Resumo

Um mês por vez, uma seção por moeda (moedas nunca são somadas):

- saldos de hoje por conta, e os três totais por papel — disponível,
  reserva e cartão. Não existe "total geral";
- o movimento do mês nos dois lados da identidade do período ("de onde
  veio" e "para onde foi"), com os números do backend;
- gastos por categoria, maiores primeiro, subcategorias sob a mãe;
- aviso com a quantidade de lançamentos do mês ainda não classificados,
  que abre a lista já filtrada neles.

### Lançamentos

- filtros: conta, período, natureza, categoria (ou "sem categoria"),
  texto na descrição, estornados. Só valem depois de **Filtrar**;
- 50 por página, com o total;
- cada linha mostra de onde veio a classificação: `regra: <nome>`,
  `manual`, ou nada quando ainda não foi classificada;
- **Classificar**: natureza, categoria e tags de uma vez. Opcionalmente
  cria uma regra com o mesmo destino (texto normalizado do lançamento,
  só no mesmo sentido — entrada ou saída);
- **Transferência**: liga ao lançamento da outra ponta, ou marca como
  aporte/resgate em conta de investimentos;
- **Desfazer transferência** e **Estornar**, os dois com confirmação;
- **Novo lançamento**: lançamento manual ou transferência entre contas.

### Importar extrato

Prévia → confirmação, como na importação de investimentos. Mostra a
regra que classificaria cada linha, trava as linhas com erro e as já
importadas, e no fim diz se o saldo do sistema bate com o do banco.

O **saldo inicial** só é oferecido quando o arquivo informa saldo e a
conta ainda não tem nenhum lançamento; vem marcado, pode ser desmarcado,
e se desliga sozinho se alguma linha válida for tirada da seleção.

### Categorias e Regras

Cadastro de categorias (dois níveis), tags e regras. Aplicar as regras
ao que já existe exige ver a prévia antes; mudar uma regra ou a opção
de reavaliar descarta a prévia que estava na tela.

## O que mudou na API

- `GET /cashflow/entries` ganhou os filtros `nature`, `category_id`,
  `uncategorized` e `search`.
  - `category_id` de uma categoria-mãe inclui as subcategorias — o mesmo
    critério do total por categoria.
  - `category_id` e `uncategorized` juntos são recusados (400).
  - `search` procura o texto dentro da descrição, sem diferenciar
    maiúsculas; `%` e `_` são texto, não curingas. Não ignora acentos.
- `GET /cashflow/entries/count`: o total com os mesmos filtros, sem
  paginação. Lista e contagem usam a mesma função de filtro, então
  respondem sempre sobre o mesmo conjunto.
- Cada mudança de `POST /cashflow/rules/preview|apply` passou a trazer
  `currency_code` e `entry_date` do lançamento.

Nenhuma migração nesta unidade.

## Regras que as telas respeitam

- **A tela não faz conta com dinheiro.** Todo valor exibido veio
  calculado do backend; a tela só formata. As duas exceções são de
  apresentação: a largura da barra de categoria e a troca de sinal como
  texto (saída digitada positiva é enviada com `-` na frente).
- **Valor digitado** aceita vírgula ou ponto decimal (`1.234,56` ou
  `1234.56`), sempre positivo, até 4 casas. O sentido escolhido decide o
  sinal.
- **Depois de qualquer alteração a lista é buscada de novo.** A tela
  não adivinha o resultado.
- **Ação que não tem volta simples pede confirmação** no próprio lugar
  (estornar, desfazer transferência, excluir).
- **A prévia de importação volta intacta** para o backend; a tela só
  escolhe linhas.
- **Se a classificação é gravada mas a regra falha**, a mensagem diz
  exatamente isso — o lançamento já está classificado.

## Correção em tela antiga

Depois de importar, o campo de arquivo ficava com o arquivo anterior e
escolher o mesmo arquivo de novo não fazia nada. Agora o campo volta
vazio — na importação de investimentos e na de extrato.

## Fora desta unidade

- Indicadores (CF-4): taxa de poupança, aportes/renda, parcelas/renda.
- Gráficos de evolução mês a mês.
- Editar o texto, a data ou o valor de um lançamento: continua sendo
  estornar e lançar de novo.
- Dividir um lançamento em várias categorias.
- Busca que ignore acentos.
