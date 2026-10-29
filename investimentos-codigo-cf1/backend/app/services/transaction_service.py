from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.financial_engine.position import PositionCalculator
from app.models.account import Account
from app.models.asset import Asset
from app.models.enums import AccountType, TransactionSource, TransactionStatus, TransactionType
from app.models.transaction import Transaction
from app.repositories.transactions import get_active_transactions, list_transactions
from app.schemas.transaction import TransactionCreate, TransferCreate
from app.services.exceptions import (
    AccountNotFoundError,
    CorrectionInvalidatesHistoryError,
    CrossCurrencyTransferError,
    CurrencyMismatchError,
    DomainConflictError,
    InsufficientPositionError,
    InvalidTransactionDataError,
    NotAnInvestmentAccountError,
    ReversalInvalidatesHistoryError,
    SameAccountTransferError,
    TransactionAlreadyReversedError,
    TransactionNotFoundError,
    UnsupportedCorrectionError,
    UnsupportedReversalError,
)


def _get_owned_account(db: Session, account_id: UUID, user_id: UUID) -> Account:
    account = db.get(Account, account_id)
    if account is None or account.user_id != user_id:
        # Mesma mensagem para "não existe" e "não é sua": não damos
        # pista de que uma conta de outro usuário existe.
        raise AccountNotFoundError(f"conta {account_id} não encontrada")
    return account


def _get_investment_account(db: Session, account_id: UUID, user_id: UUID) -> Account:
    """CF-1: `Transaction` só existe em conta BROKERAGE. Conta do livro
    de caixa (corrente, reserva, dinheiro, cartão) recebe
    `CashflowEntry`, nunca `Transaction` — os dois livros não se
    misturam. Usada em toda ESCRITA; leitura continua em
    `_get_owned_account`.
    """
    account = _get_owned_account(db, account_id, user_id)
    if account.account_type is not AccountType.BROKERAGE:
        raise NotAnInvestmentAccountError(
            f"conta {account.name} é do controle financeiro: não recebe lançamento de investimento"
        )
    return account


_TRADE_TYPES = {TransactionType.BUY, TransactionType.SELL}
_QUANTITY_INCREASE_TYPES = {TransactionType.BONUS_SHARES, TransactionType.STOCK_SPLIT}
# Tipos que o `PositionCalculator` NÃO processa numa lista filtrada por
# ativo — são movimentos de caixa, nunca de posição de ativo.
_CASH_ONLY_TYPES = {
    TransactionType.DEPOSIT,
    TransactionType.WITHDRAWAL,
    TransactionType.FX_CONVERSION,
}


def _validate_transaction_data(
    *,
    transaction_type: TransactionType,
    asset_id: UUID | None,
    quantity: Decimal | None,
    unit_price: Decimal | None,
    fees: Decimal,
    gross_amount: Decimal,
) -> None:
    """Coerência dos campos com o tipo, checada em TODO ponto de
    entrada (manual, correção e importação) antes de gravar.

    Não é regra financeira nova: são exatamente as PRÉ-CONDIÇÕES de
    forma que o `PositionCalculator` já exige (BUY/SELL com ativo,
    quantidade e preço; eventos societários com quantidade; DEPOSIT/
    WITHDRAWAL/FX_CONVERSION fora de lista de ativo) mais a convenção
    de sinal do projeto (o SINAL de um evento vem do TIPO — SELL,
    WITHDRAWAL, REVERSE_SPLIT —, nunca de um valor negativo). Sem isso
    uma Transaction imutável malformada entraria no histórico e
    derrubaria (ou distorceria em silêncio) todo cálculo do par.
    """

    def _reject(message: str):
        raise InvalidTransactionDataError(f"{transaction_type.value}: {message}")

    if fees < 0:
        _reject("fees não pode ser negativo")
    if gross_amount < 0:
        _reject("gross_amount não pode ser negativo — o sinal do evento vem do tipo")
    if unit_price is not None and unit_price < 0:
        _reject("unit_price não pode ser negativo")

    if transaction_type in _TRADE_TYPES:
        if asset_id is None:
            _reject("exige asset_id")
        if quantity is None or unit_price is None:
            _reject("exige quantity e unit_price")
        if quantity <= 0:
            _reject("quantity deve ser maior que zero")
    elif transaction_type in _QUANTITY_INCREASE_TYPES:
        if asset_id is None:
            _reject("exige asset_id")
        if quantity is None or quantity <= 0:
            _reject("exige quantity maior que zero (variação de quantidade do evento)")
    elif transaction_type == TransactionType.REVERSE_SPLIT:
        if asset_id is None:
            _reject("exige asset_id")
        if quantity is None or quantity >= 0:
            _reject("exige quantity NEGATIVA (variação de quantidade do grupamento)")
    elif transaction_type in _CASH_ONLY_TYPES:
        if asset_id is not None:
            _reject("é movimento de caixa e não pode ter asset_id")
    elif quantity is not None and quantity < 0:
        _reject("quantity não pode ser negativa")


def _check_currency_matches_asset(db: Session, asset_id: UUID | None, currency_code: str) -> None:
    """`Transaction.currency_code == Asset.currency_code`, para TODA
    transação ligada a um ativo (compra, venda, proventos, taxa avulsa
    e eventos societários), em todo ponto de entrada.

    Sem ativo (DEPOSIT, WITHDRAWAL, transferências) não há o que
    comparar: a moeda informada no movimento é preservada.

    Um `asset_id` que não existe não é tratado aqui — a FK do banco já
    o rejeita na gravação, com o erro de sempre.
    """
    if asset_id is None:
        return
    asset = db.get(Asset, asset_id)
    if asset is None:
        return
    if currency_code != asset.currency_code:
        raise CurrencyMismatchError(
            f"moeda da transação ({currency_code}) difere da moeda do ativo "
            f"{asset.ticker} ({asset.currency_code}) — nenhuma conversão é feita"
        )


def _check_sell_against_position(
    db: Session,
    account_id: UUID,
    asset_id: UUID | None,
    transaction_type: TransactionType,
    quantity: Decimal | None,
) -> None:
    if transaction_type != TransactionType.SELL:
        return
    if quantity is None:
        return

    facts = get_active_transactions(db, account_id, asset_id)
    current_quantity = Decimal(0)
    if facts:
        current_quantity = PositionCalculator.calculate(facts).quantity

    if quantity > current_quantity:
        raise InsufficientPositionError(
            f"SELL de {quantity} excede a posição atual ({current_quantity})"
        )


def _insert_transaction(
    db: Session,
    *,
    account_id: UUID,
    asset_id: UUID | None,
    transaction_type: TransactionType,
    quantity: Decimal | None,
    unit_price: Decimal | None,
    fees: Decimal,
    gross_amount: Decimal,
    currency_code: str,
    transaction_date,
    source: TransactionSource,
    fx_rate_to_brl: Decimal | None = None,
    notes: str | None = None,
    external_reference: str | None = None,
) -> Transaction:
    """Único ponto que efetivamente monta e grava um `Transaction` novo
    (fora do fluxo de transferência/correção, que têm sua própria
    montagem). Compartilhado por `create_transaction` (MANUAL) e
    `create_imported_transaction` (Fase 10a, D-G2) — a MESMA validação
    de posse/D-A3 já rodou antes de chegar aqui, em ambos os casos.
    """
    transaction = Transaction(
        account_id=account_id,
        asset_id=asset_id,
        transaction_type=transaction_type,
        quantity=quantity,
        unit_price=unit_price,
        fees=fees,
        gross_amount=gross_amount,
        currency_code=currency_code,
        transaction_date=transaction_date,
        fx_rate_to_brl=fx_rate_to_brl,
        notes=notes,
        source=source,
        status=TransactionStatus.ACTIVE,
        external_reference=external_reference,
    )
    db.add(transaction)
    try:
        db.flush()
    except IntegrityError as exc:
        raise DomainConflictError(str(exc.orig)) from exc

    return transaction


def _validate_payload(payload: TransactionCreate) -> None:
    _validate_transaction_data(
        transaction_type=payload.transaction_type,
        asset_id=payload.asset_id,
        quantity=payload.quantity,
        unit_price=payload.unit_price,
        fees=payload.fees,
        gross_amount=payload.gross_amount,
    )


def create_transaction(db: Session, user_id: UUID, payload: TransactionCreate) -> Transaction:
    """Cria uma transação MANUAL (nunca TRANSFER_OUT/IN — ver
    TransactionCreate). Valida posse da conta e, para SELL, valida a
    posição atual (D-A3) antes de gravar.
    """
    _get_investment_account(db, payload.account_id, user_id)
    _validate_payload(payload)
    _check_currency_matches_asset(db, payload.asset_id, payload.currency_code)
    _check_sell_against_position(
        db, payload.account_id, payload.asset_id, payload.transaction_type, payload.quantity
    )

    return _insert_transaction(
        db,
        account_id=payload.account_id,
        asset_id=payload.asset_id,
        transaction_type=payload.transaction_type,
        quantity=payload.quantity,
        unit_price=payload.unit_price,
        fees=payload.fees,
        gross_amount=payload.gross_amount,
        currency_code=payload.currency_code,
        transaction_date=payload.transaction_date,
        source=TransactionSource.MANUAL,
        fx_rate_to_brl=payload.fx_rate_to_brl,
        notes=payload.notes,
    )


def create_imported_transaction(
    db: Session,
    user_id: UUID,
    *,
    account_id: UUID,
    asset_id: UUID | None,
    transaction_type: TransactionType,
    quantity: Decimal | None,
    unit_price: Decimal | None,
    fees: Decimal,
    gross_amount: Decimal,
    currency_code: str,
    transaction_date,
    source: TransactionSource,
    external_reference: str,
) -> Transaction:
    """Fase 10a (D-G2): função INTERNA (não exposta como
    `POST /transactions`, que continua só MANUAL) usada exclusivamente
    pelo fluxo de importação. Reaproveita exatamente a mesma validação
    de posse de conta e D-A3 de `create_transaction` — nenhuma regra
    nova, nenhum bypass.
    """
    _get_investment_account(db, account_id, user_id)
    _validate_transaction_data(
        transaction_type=transaction_type,
        asset_id=asset_id,
        quantity=quantity,
        unit_price=unit_price,
        fees=fees,
        gross_amount=gross_amount,
    )
    _check_currency_matches_asset(db, asset_id, currency_code)
    _check_sell_against_position(db, account_id, asset_id, transaction_type, quantity)

    return _insert_transaction(
        db,
        account_id=account_id,
        asset_id=asset_id,
        transaction_type=transaction_type,
        quantity=quantity,
        unit_price=unit_price,
        fees=fees,
        gross_amount=gross_amount,
        currency_code=currency_code,
        transaction_date=transaction_date,
        source=source,
        external_reference=external_reference,
    )


def create_transfer(
    db: Session, user_id: UUID, payload: TransferCreate
) -> tuple[Transaction, Transaction]:
    """Cria as duas pernas (TRANSFER_OUT + TRANSFER_IN) atomicamente.

    Atomicidade: as duas ficam na mesma sessão/transação de banco; se
    qualquer etapa falhar, nada é commitado (get_db só commita se o
    request inteiro terminar sem exceção). Além disso, forçamos a
    checagem dos constraints DEFERRED (FK + trigger de consistência do
    vínculo, ambos da Fase 5) já aqui dentro, via `SET CONSTRAINTS ALL
    IMMEDIATE`, para traduzir qualquer violação em erro de domínio
    antes de devolver a resposta — em vez de deixar a checagem só para
    o commit final, o que dificultaria dar um erro HTTP claro.
    """
    if payload.from_account_id == payload.to_account_id:
        raise SameAccountTransferError("conta de origem e destino não podem ser a mesma")
    if payload.gross_amount <= 0:
        raise InvalidTransactionDataError("TRANSFER: gross_amount deve ser maior que zero")
    if payload.fees < 0:
        raise InvalidTransactionDataError("TRANSFER: fees não pode ser negativo")

    from_account = _get_investment_account(db, payload.from_account_id, user_id)
    to_account = _get_investment_account(db, payload.to_account_id, user_id)

    if from_account.currency_code != to_account.currency_code:
        raise CrossCurrencyTransferError(
            "transferência entre contas de moedas diferentes está fora do escopo desta fase"
        )

    transfer_out = Transaction(
        account_id=from_account.id,
        asset_id=None,
        transaction_type=TransactionType.TRANSFER_OUT,
        fees=payload.fees,
        gross_amount=payload.gross_amount,
        currency_code=from_account.currency_code,
        transaction_date=payload.transaction_date,
        notes=payload.notes,
        source=TransactionSource.MANUAL,
        status=TransactionStatus.ACTIVE,
    )
    transfer_in = Transaction(
        account_id=to_account.id,
        asset_id=None,
        transaction_type=TransactionType.TRANSFER_IN,
        fees=Decimal(0),
        gross_amount=payload.gross_amount,
        currency_code=to_account.currency_code,
        transaction_date=payload.transaction_date,
        notes=payload.notes,
        source=TransactionSource.MANUAL,
        status=TransactionStatus.ACTIVE,
    )

    try:
        db.add(transfer_out)
        db.add(transfer_in)
        db.flush()  # gera os IDs das duas antes de vincular

        transfer_out.linked_transaction_id = transfer_in.id
        transfer_in.linked_transaction_id = transfer_out.id
        db.flush()

        # Força a checagem dos triggers DEFERRED agora, não só no commit.
        db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    except IntegrityError as exc:
        raise DomainConflictError(str(exc.orig)) from exc

    return transfer_out, transfer_in


def correct_transaction(
    db: Session, user_id: UUID, transaction_id: UUID, payload: TransactionCreate
) -> Transaction:
    """Estorna a original (status -> REVERSED) e cria uma nova
    transação com os valores corrigidos, ligada via
    `reverses_transaction_id` (D-A4). Nunca sobrescreve a original.

    Escopo desta fase: a correção deve manter a MESMA conta e o MESMO
    ativo da original (mover para outra conta é uma transferência, não
    uma correção) e não se aplica a pernas de transferência (corrigir
    as duas pontas simetricamente é mais complexo e fica fora desta
    fase).

    Validação de histórico (mesma garantia de `reverse_transaction`):
    depois de aplicar a correção, o histórico ACTIVE do par (conta,
    ativo) — já SEM a original e COM a corrigida, na ordem canônica
    `(transaction_date, created_at)` — precisa continuar válido para o
    Financial Engine. Quem decide é o `PositionCalculator` (nenhuma
    regra financeira é reimplementada aqui); o `ValueError` dele vira
    `CorrectionInvalidatesHistoryError`. Ex.: BUY 100 + SELL 80 —
    corrigir o BUY para 50 deixaria o SELL sem posição e é rejeitado;
    corrigir um SELL para mais do que a posição também.

    Tudo roda num SAVEPOINT: se a validação (ou o banco) rejeitar,
    NADA sobrevive — a original continua ACTIVE e a corrigida não
    existe —, independentemente do que o chamador faça com a sessão.
    """
    # Lock de linha (mesmo motivo de `reverse_transaction`): duas
    # correções concorrentes da MESMA Transaction não podem passar
    # ambas pela checagem de status e gerar duas corrigidas.
    original = db.get(Transaction, transaction_id, with_for_update=True)
    if original is None:
        raise TransactionNotFoundError(f"transação {transaction_id} não encontrada")

    _get_owned_account(db, original.account_id, user_id)

    if original.status != TransactionStatus.ACTIVE:
        raise TransactionAlreadyReversedError(
            f"transação {transaction_id} já está {original.status}"
        )
    if original.transaction_type in (TransactionType.TRANSFER_OUT, TransactionType.TRANSFER_IN):
        raise UnsupportedCorrectionError(
            "correção de pernas de transferência não é suportada nesta fase"
        )
    if payload.account_id != original.account_id or payload.asset_id != original.asset_id:
        raise UnsupportedCorrectionError(
            "correção deve manter a mesma conta e o mesmo ativo da transação original "
            "— para mover valores entre contas, use uma transferência"
        )
    _validate_payload(payload)
    _check_currency_matches_asset(db, payload.asset_id, payload.currency_code)

    try:
        with db.begin_nested():
            corrected = _apply_correction(db, original, payload)
    except IntegrityError as exc:
        raise DomainConflictError(str(exc.orig)) from exc

    return corrected


def _apply_correction(
    db: Session, original: Transaction, payload: TransactionCreate
) -> Transaction:
    """Núcleo de `correct_transaction`, sempre chamado dentro de um
    SAVEPOINT: estorna a original, grava a corrigida e valida o
    histórico resultante. Qualquer exceção desfaz as três coisas.
    """
    original.status = TransactionStatus.REVERSED
    db.flush()

    corrected = Transaction(
        account_id=payload.account_id,
        asset_id=payload.asset_id,
        transaction_type=payload.transaction_type,
        quantity=payload.quantity,
        unit_price=payload.unit_price,
        fees=payload.fees,
        gross_amount=payload.gross_amount,
        currency_code=payload.currency_code,
        transaction_date=payload.transaction_date,
        fx_rate_to_brl=payload.fx_rate_to_brl,
        notes=payload.notes,
        source=TransactionSource.MANUAL,
        status=TransactionStatus.ACTIVE,
        reverses_transaction_id=original.id,
    )
    db.add(corrected)
    db.flush()

    if corrected.asset_id is not None:
        # Lido do banco de propósito (não montado em memória): é a
        # MESMA ordenação e o MESMO filtro de ACTIVE que qualquer
        # cálculo de posição posterior vai usar.
        history = get_active_transactions(db, corrected.account_id, corrected.asset_id)
        try:
            PositionCalculator.calculate(history)
        except ValueError as exc:
            raise CorrectionInvalidatesHistoryError(
                f"corrigir a transação {original.id} tornaria o histórico inválido: {exc}"
            ) from exc

    return corrected


def reverse_transaction(db: Session, user_id: UUID, transaction_id: UUID) -> Transaction:
    """Reversão segura (Fase 10b, D-H2): marca uma Transaction ACTIVE
    como REVERSED, SEM criar nenhuma Transaction nova e sem alterar
    qualquer campo financeiro (o trigger de imutabilidade só permite
    ACTIVE -> REVERSED).

    Ordem das validações (nada é gravado antes de todas passarem):

    1. a Transaction existe e pertence ao usuário (via conta);
    2. está ACTIVE;
    3. não é perna de transferência (TRANSFER_IN/OUT);
    4. o histórico HIPOTÉTICO do par (conta, ativo) — as ACTIVE
       ordenadas por (transaction_date, created_at), EXCLUINDO a alvo —
       continua válido para o Financial Engine. As regras financeiras
       não são reimplementadas aqui: quem decide é o
       `PositionCalculator`, cujo `ValueError` é traduzido para erro
       de domínio. Ex.: BUY 100 + SELL 50 — reverter o BUY deixaria o
       SELL sem posição e é rejeitado.

    Transações sem `asset_id` (DEPOSIT, WITHDRAWAL, ...) não entram em
    posição de ativo, então não há histórico de ativo a validar.

    Nota: `created_at` na ordenação é só desempate técnico (ver
    `TRANSACTION_ORDER`), não a ordem econômica real.

    A operação não faz commit: a atomicidade com quem a chama (ex.:
    MERGE da reconciliação) é responsabilidade da sessão/transação do
    chamador.
    """
    # Lock de linha: evita que duas reversões concorrentes da mesma
    # Transaction passem ambas pela checagem de status.
    target = db.get(Transaction, transaction_id, with_for_update=True)
    if target is None:
        raise TransactionNotFoundError(f"transação {transaction_id} não encontrada")

    _get_owned_account(db, target.account_id, user_id)

    if target.status != TransactionStatus.ACTIVE:
        raise TransactionAlreadyReversedError(f"transação {transaction_id} já está {target.status}")
    if target.transaction_type in (TransactionType.TRANSFER_OUT, TransactionType.TRANSFER_IN):
        raise UnsupportedReversalError(
            "reversão de pernas de transferência não é suportada — reverter uma perna "
            "isoladamente deixaria o par inconsistente"
        )

    if target.asset_id is not None:
        hypothetical = [
            fact
            for fact in get_active_transactions(db, target.account_id, target.asset_id)
            if fact.id != target.id
        ]
        if hypothetical:
            try:
                PositionCalculator.calculate(hypothetical)
            except ValueError as exc:
                raise ReversalInvalidatesHistoryError(
                    f"reverter a transação {transaction_id} tornaria o histórico inválido: {exc}"
                ) from exc

    try:
        target.status = TransactionStatus.REVERSED
        db.flush()
    except IntegrityError as exc:
        raise DomainConflictError(str(exc.orig)) from exc

    return target


def get_transaction(db: Session, user_id: UUID, transaction_id: UUID) -> Transaction:
    """Busca uma Transaction isolada por id (Fase 11, unidade backend 1).
    Leitura pura — não altera nada, não dispara `check_after_creation`.

    Ownership validada por conta, reaproveitando `_get_owned_account`
    (mesma mensagem para "não existe" e "não é sua").
    """
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise TransactionNotFoundError(f"transação {transaction_id} não encontrada")

    _get_owned_account(db, transaction.account_id, user_id)

    return transaction


def get_position(db: Session, user_id: UUID, account_id: UUID, asset_id: UUID):
    _get_owned_account(db, account_id, user_id)
    facts = get_active_transactions(db, account_id, asset_id)
    if not facts:
        return None
    return PositionCalculator.calculate(facts)


def get_transaction_history(
    db: Session, user_id: UUID, account_id: UUID, asset_id: UUID | None = None
) -> list[Transaction]:
    _get_owned_account(db, account_id, user_id)
    return list_transactions(db, account_id, asset_id)
