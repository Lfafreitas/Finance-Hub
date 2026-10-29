"""Exceções de domínio da camada de serviço.

Regra da Fase 6: regra de negócio mora no service, não no router. Os
routers só sabem mapear cada uma dessas exceções para um status HTTP —
não reimplementam nem reinterpretam a condição que gerou o erro.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base de todas as exceções de domínio da camada de serviço."""


class AccountNotFoundError(DomainError):
    """A conta não existe ou não pertence ao usuário resolvido pela
    dependency de autenticação (nunca a um `user_id` vindo do cliente).
    """


class PortfolioNotFoundError(DomainError):
    """O portfolio não existe ou não pertence ao usuário resolvido."""


class TransactionNotFoundError(DomainError):
    pass


class InvalidScanScopeError(DomainError):
    """O scan de reconciliação foi chamado com mais de um escopo ao
    mesmo tempo (`account_id` e `portfolio_id`). Escopo é: uma conta,
    um portfolio, ou nenhum dos dois (todas as contas do usuário) —
    nunca os dois juntos.
    """


class ReconciliationLogNotFoundError(DomainError):
    """O `ReconciliationLog` não existe ou não pertence ao usuário
    resolvido pela dependency de autenticação.
    """


class ReconciliationAlreadyResolvedError(DomainError):
    """Só um `ReconciliationLog PENDING` pode ser resolvido. Cobre
    IGNORED, KEPT_BOTH, MERGED e STALE — nenhum deles aceita uma nova
    resolução.
    """


class InvalidMergeSurvivorError(DomainError):
    """Em um MERGE, `surviving_transaction_id` precisa ser exatamente
    uma das duas Transactions do par — nunca uma terceira Transaction.
    """


class SameAccountTransferError(DomainError):
    """Conta de origem e destino da transferência são a mesma."""


class CrossCurrencyTransferError(DomainError):
    """Transferência entre contas de moedas diferentes — fora do
    escopo desta fase (decisão explícita, não uma limitação técnica
    escondida).
    """


class InsufficientPositionError(DomainError):
    """Tentativa de SELL com quantidade maior que a posição atual
    calculada pelo Financial Engine (D-A3).
    """


class UnsupportedTransactionTypeError(DomainError):
    """Tipo de transação que não deveria vir por este endpoint (ex.:
    TRANSFER_OUT/IN via POST /transactions, que devem ir por
    POST /transfers).
    """


class InvalidTransactionDataError(DomainError):
    """Os campos da transação são incoerentes com o tipo dela (ex.: BUY
    sem ativo/quantidade, quantidade ou valor negativo, DEPOSIT ligado
    a um ativo). Rejeitada ANTES de gravar: como Transaction é
    imutável, um dado assim ficaria para sempre no histórico e
    quebraria todo cálculo de posição do par (conta, ativo).
    """


class CurrencyMismatchError(DomainError):
    """A moeda da transação difere da moeda do ativo a que ela se
    refere (`Transaction.currency_code != Asset.currency_code`). Não há
    conversão nem inferência: a operação é recusada. Sem essa regra o
    par (conta, ativo) ficaria com Transactions em moedas diferentes —
    a posição inconsistente que o dashboard exclui dos totais.
    """


class TransactionAlreadyReversedError(DomainError):
    """Tentativa de corrigir uma transação que já está REVERSED."""


class UnsupportedCorrectionError(DomainError):
    """Correção que muda conta/ativo, ou que tenta corrigir uma perna
    de transferência — fora do escopo desta fase.
    """


class UnsupportedReversalError(DomainError):
    """Reversão de uma Transaction que não pode ser revertida
    isoladamente (ex.: perna de transferência — reverter uma perna
    sem a outra deixaria o par inconsistente).
    """


class ReversalInvalidatesHistoryError(DomainError):
    """Remover a Transaction alvo deixaria o histórico financeiro
    inválido segundo o Financial Engine (ex.: reverter um BUY do qual
    um SELL posterior depende). A mensagem carrega o motivo devolvido
    pelo próprio engine — as regras não são duplicadas na camada de
    serviço.
    """


class CorrectionInvalidatesHistoryError(DomainError):
    """Aplicar a correção deixaria o histórico financeiro do par
    (conta, ativo) inválido segundo o Financial Engine (ex.: reduzir um
    BUY do qual um SELL posterior depende, ou corrigir um SELL para
    mais do que a posição). Espelho de `ReversalInvalidatesHistoryError`
    para `correct_transaction`; a mensagem carrega o motivo devolvido
    pelo próprio engine.
    """


class DomainConflictError(DomainError):
    """Violação de integridade do banco (trigger de imutabilidade, de
    vínculo de transferência, FK, unique) traduzida para uma mensagem
    de domínio — usada quando o próprio Postgres rejeita a operação
    por uma regra que já está reforçada em nível de schema.
    """


class ImportParsingError(DomainError):
    """Arquivo de importação malformado ou em formato inesperado."""


class InvalidImportSignatureError(DomainError):
    """A assinatura HMAC do payload de commit não corresponde ao
    conteúdo — o payload foi alterado em relação à preview, ou é de
    uma versão diferente da lógica de parsing/normalização.
    """


class ImportRowRejectedError(DomainError):
    """Uma linha do lote de importação violou uma regra de negócio
    (ex.: SELL acima da posição) durante o commit. Usada para abortar
    o lote inteiro (tudo-ou-nada) com o motivo exato da linha que
    falhou.
    """


class DuplicateRegistryEntryError(DomainError):
    """Cadastro que já existe (ativo com o mesmo ticker+país, conta com
    o mesmo nome na instituição, carteira com o mesmo nome).
    """


class InvalidRegistryReferenceError(DomainError):
    """Cadastro que aponta para uma referência inexistente (moeda,
    classe de ativo ou instituição não cadastrada).
    """


class AssetNotFoundError(DomainError):
    """O ativo não existe no cadastro."""


class InvalidPriceError(DomainError):
    """Cotação inválida: preço não positivo ou data no futuro."""


class NotAnInvestmentAccountError(DomainError):
    """CF-1: a conta é do livro de caixa (`account_type` diferente de
    BROKERAGE) e não recebe `Transaction` de investimento.
    """


class InvalidCashflowEntryError(DomainError):
    """CF-1: o lançamento de caixa viola uma regra do livro (valor
    zero, data futura, conta BROKERAGE, natureza não permitida na
    operação, descrição vazia).
    """


class CashflowEntryNotFoundError(DomainError):
    """O lançamento não existe ou a conta dele não é do usuário."""


class CashflowEntryAlreadyReversedError(DomainError):
    pass


class CashflowEntryNotRestorableError(DomainError):
    """Edição-2: o lançamento não está excluído, ou foi substituído por
    uma edição e não pode voltar.
    """


class InvalidCashflowPeriodError(DomainError):
    pass


class RegistryEntryNotFoundError(DomainError):
    """Instituição ou ativo inexistente em uma edição ou exclusão."""


class RegistryInUseError(DomainError):
    """O cadastro já é usado por lançamentos (ou por outros cadastros)
    e a mudança pedida quebraria o que foi gravado: excluir, trocar a
    moeda, ou trocar a conta de livro.
    """


class CashflowCategoryNotFoundError(DomainError):
    pass


class CashflowTagNotFoundError(DomainError):
    pass


class CashflowRuleNotFoundError(DomainError):
    pass


class InvalidCashflowClassificationError(DomainError):
    """CF-2: classificação incoerente — categoria em transferência,
    subcategoria de subcategoria, regra sem efeito, regra que
    classificaria como transferência.
    """


class CashflowClassificationInUseError(DomainError):
    """Categoria com subcategorias, lançamentos ou regras não é excluída."""


class InvalidCashflowTransferLinkError(DomainError):
    """CF-3: os lançamentos não podem ser ligados como transferência
    (valores que não se anulam, moedas diferentes, mesma conta, datas
    distantes, lançamento estornado ou já em transferência).
    """


class InvalidAllocationTargetError(DomainError):
    """Alvos de alocação que não somam 100%, com classe repetida ou
    classe/moeda que não existe."""
