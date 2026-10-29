# Fácil de usar — iniciador, pasta Entrada e widget com notícias

Sem migração. Rotas novas: `GET /cashflow/inbox` e `POST /cashflow/inbox/process`.

## Iniciador (`launcher/dashboard.py`)

Atalhos na pasta "Dashboard Financeiro" (criados por `dashboard.py atalhos`):

| Atalho | O que faz |
| --- | --- |
| Iniciar Dashboard | instala/atualiza dependências quando `pyproject.toml` ou `package-lock.json` mudam, confere o Postgres, aplica as migrações, (re)liga o backend, liga o frontend, carrega a pasta Entrada e abre o navegador |
| Parar Dashboard | desliga backend e frontend |
| Carregar pasta Entrada | carrega os arquivos da pasta (com o dashboard ligado) |
| Abrir widget | abre o widget da carteira (liga o backend se preciso) |

- O backend é sempre reiniciado no "Iniciar": é assim que um código novo
  entra no ar. O frontend (Vite) se atualiza sozinho e é reaproveitado.
- Só processos DESTE projeto são desligados: o backend é reconhecido pelo
  `/health` (nome do app) e o frontend pelo título da página. Outro
  programa nas portas 8000/5173 nunca é derrubado; o iniciador avisa.
- Logs em `investimentos-codigo-cf1/.dashboard/` (fora do git).

## Pasta Entrada

Salve o extrato da conta (OFX/CSV) ou a fatura do cartão (PDF/OFX/CSV) do
Nubank em `Dashboard Financeiro/Entrada` (configurável: `INBOX_DIR`).

- Cada arquivo passa pelo mesmo caminho da tela "Importar extrato": prévia
  (com a conferência da fatura em PDF) e commit tudo-ou-nada, com as mesmas
  chaves de duplicidade. Carregar duas vezes não duplica.
- Conta de destino pelo formato: extrato → a conta corrente do Nubank;
  fatura → o cartão do Nubank. Sem exatamente uma conta candidata, o
  arquivo fica na pasta (`NO_ACCOUNT`).
- Entra o que é válido e novo; linha com erro é só contada. Saldo inicial
  nunca é criado aqui.
- Recusado (`REFUSED`: formato desconhecido, fatura que não confere) fica
  na pasta com o motivo.
- Aceitos (`IMPORTED`, `NOTHING_NEW`) vão para `importados/AAAA-MM-DD/`
  **depois do commit**, com uma linha em `importados/registro.txt`. Nome
  repetido ganha "(2)". Falha ao mover não desfaz nada.
- Tela: Controle financeiro → Importar extrato → "Carregar a pasta Entrada".

## Widget

- Seção "Notícias": as 4 primeiras notícias da análise do dia (a mesma da
  tela Notícias e análises, que a tarefa agendada grava em
  `claude-analises/relatorios`). Clique abre a notícia; só links http(s).
- "análise de DD/MM" fica amarelo quando a análise é de antes de ontem.
- Botão direito → "Notícias" liga/desliga a seção.
