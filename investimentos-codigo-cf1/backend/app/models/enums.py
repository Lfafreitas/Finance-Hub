import enum


class InstitutionType(str, enum.Enum):
    """Domínio pequeno e estável (banco/corretora/outro). Diferente de
    AssetClass (tabela de referência), aqui um enum nativo é adequado
    porque não esperamos crescimento frequente desta lista.
    """

    BANK = "BANK"
    BROKER = "BROKER"
    OTHER = "OTHER"


class TransactionStatus(str, enum.Enum):
    """Estado de uma Transaction para fins de estorno/correção.

    Transição permitida: ACTIVE -> REVERSED, e só essa (reforçado pelo
    trigger de imutabilidade). Não existe REVERSED -> ACTIVE: uma
    reversão é definitiva; se a transação era, na verdade, correta,
    a correção certa é registrar uma nova transação, não reativar a
    antiga. Apenas transações ACTIVE entram no cálculo de posição do
    futuro Financial Engine.
    """

    ACTIVE = "ACTIVE"
    REVERSED = "REVERSED"


class TransactionType(str, enum.Enum):
    """Tipo do evento financeiro original.

    Enum nativo (não tabela de referência) por decisão consciente:
    cada novo tipo aqui exige lógica nova no futuro Financial Engine
    (ex.: STOCK_SPLIT precisa recalcular quantidade/preço médio de um
    jeito específico). Diferente de AssetClass, que é taxonomia
    descritiva, TransactionType é um contrato entre o dado e o código
    que o processa — por isso faz sentido ficar hardcoded e versionado
    junto com o código, não editável via dado.
    """

    BUY = "BUY"
    SELL = "SELL"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    DIVIDEND = "DIVIDEND"
    JCP = "JCP"
    INCOME = "INCOME"
    FEE = "FEE"
    TRANSFER_OUT = "TRANSFER_OUT"
    TRANSFER_IN = "TRANSFER_IN"
    FX_CONVERSION = "FX_CONVERSION"
    BONUS_SHARES = "BONUS_SHARES"
    STOCK_SPLIT = "STOCK_SPLIT"
    REVERSE_SPLIT = "REVERSE_SPLIT"


class TransactionSource(str, enum.Enum):
    """De onde o dado original veio — usado pelo futuro Reconciliation
    Engine para comparar fontes (ex.: API vs CSV).
    """

    MANUAL = "MANUAL"
    IMPORT_CSV = "IMPORT_CSV"
    IMPORT_XLSX = "IMPORT_XLSX"
    IMPORT_OFX = "IMPORT_OFX"
    IMPORT_PDF = "IMPORT_PDF"
    API_PLUGGY = "API_PLUGGY"


class ReconciliationStatus(str, enum.Enum):
    """Estado de um `ReconciliationLog` (Fase 10b).

    - PENDING: conflito detectado, aguardando decisão humana.
    - IGNORED: o usuário decidiu ignorar; o par não é reapresentado.
    - KEPT_BOTH: o usuário decidiu manter as duas; o par não é
      reapresentado.
    - MERGED: uma Transaction sobrevive (`surviving_transaction_id`) e a
      outra foi revertida (`reversed_transaction_id`).
    - STALE: a reconciliação deixou de ser aplicável porque uma das
      Transactions do par já foi revertida/invalidada por outra via.

    Só PENDING é "aberto"; os demais são estados finais (a regra de
    transição — ex.: não resolver duas vezes — é do service).
    """

    PENDING = "PENDING"
    IGNORED = "IGNORED"
    KEPT_BOTH = "KEPT_BOTH"
    MERGED = "MERGED"
    STALE = "STALE"


class PriceSource(str, enum.Enum):
    """De onde veio uma cotação (`AssetPrice`).

    - MANUAL: o usuário informou o preço. Na mesma data, vale sobre
      qualquer fonte automática.
    - YAHOO: cotação automática (Análises-1), gravada pela atualização
      de cotações. Só o código do ativo é enviado à fonte.
    """

    MANUAL = "MANUAL"
    YAHOO = "YAHOO"


class AccountType(str, enum.Enum):
    """Papel da conta nos dois livros (CF-1).

    - BROKERAGE: conta do livro de INVESTIMENTOS. Só ela recebe
      `Transaction`; nunca recebe `CashflowEntry`.
    - CHECKING, CASH: caixa disponível.
    - SAVINGS: reserva guardada sem ativo nem cotação (ex.: caixinha,
      poupança). Fica no livro de caixa, com saldo próprio.
    - CREDIT_CARD: passivo. Compra é gasto na conta do cartão (saldo
      fica negativo); pagamento de fatura é transferência para ela.

    Um banco que também é corretora são DUAS contas.
    """

    CHECKING = "CHECKING"
    SAVINGS = "SAVINGS"
    CASH = "CASH"
    CREDIT_CARD = "CREDIT_CARD"
    BROKERAGE = "BROKERAGE"


class CashflowNature(str, enum.Enum):
    """Natureza de um `CashflowEntry` — é CLASSIFICAÇÃO, não fato: pode
    mudar depois sem alterar o lançamento.

    O sinal de `amount` é independente da natureza: EXPENSE com valor
    positivo é estorno (reduz o gasto, nunca vira renda); INCOME com
    valor negativo é devolução de renda.

    - THIRD_PARTY: dinheiro de/para terceiros que não é renda nem
      gasto (reembolso, divisão de conta, acerto com família). Linha
      própria, fora do denominador de qualquer taxa.
    - TRANSFER: movimento entre contas do próprio usuário. Exige
      `counterparty_account_id`.
    - ADJUSTMENT: saldo inicial e acertos de saldo.
    - UNCLASSIFIED: ainda não classificado.
    """

    INCOME = "INCOME"
    EXPENSE = "EXPENSE"
    THIRD_PARTY = "THIRD_PARTY"
    TRANSFER = "TRANSFER"
    ADJUSTMENT = "ADJUSTMENT"
    UNCLASSIFIED = "UNCLASSIFIED"


class CashflowEntryStatus(str, enum.Enum):
    """Só ACTIVE -> REVERSED (mesma regra de `TransactionStatus`)."""

    ACTIVE = "ACTIVE"
    REVERSED = "REVERSED"


class RuleMatchType(str, enum.Enum):
    """Como o `pattern` de uma regra é comparado com o texto
    normalizado do lançamento (`ParsedDescription.match_text`).
    """

    CONTAINS = "CONTAINS"
    EQUALS = "EQUALS"
    STARTS_WITH = "STARTS_WITH"


class RuleDirection(str, enum.Enum):
    """Sentido do lançamento a que a regra se aplica: IN = entrada
    (valor positivo), OUT = saída (valor negativo).
    """

    ANY = "ANY"
    IN = "IN"
    OUT = "OUT"


class CashflowImportProfile(str, enum.Enum):
    """Formato de arquivo que o livro de caixa sabe ler (CF-3). Cada
    perfil foi verificado em um arquivo real (CF-0, seções 13 e 14).

    - NUBANK_ACCOUNT_CSV / NUBANK_ACCOUNT_OFX: extrato da conta. Cada
      linha traz o identificador do banco, igual nos dois formatos.
    - NUBANK_CARD_CSV: fatura do cartão. Sem identificador; compra é
      positiva no arquivo (o importador inverte o sinal).
    - NUBANK_CARD_OFX: fatura do cartão em OFX. O FITID se repete (IOF
      de compra internacional), então a chave é a mesma do CSV.
    - NUBANK_CARD_PDF: fatura fechada em PDF, conferida com o resumo da
      própria fatura antes de importar (Fatura-PDF).
    """

    NUBANK_ACCOUNT_CSV = "NUBANK_ACCOUNT_CSV"
    NUBANK_ACCOUNT_OFX = "NUBANK_ACCOUNT_OFX"
    NUBANK_CARD_CSV = "NUBANK_CARD_CSV"
    NUBANK_CARD_OFX = "NUBANK_CARD_OFX"
    NUBANK_CARD_PDF = "NUBANK_CARD_PDF"
