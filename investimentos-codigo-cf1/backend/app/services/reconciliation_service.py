"""Serviço de scan de reconciliação — Fase 10b, unidade 5.

Descobre pares CANDIDATOS entre Transactions ACTIVE de uma ou mais
contas e registra os que ainda não têm `ReconciliationLog` como
PENDING. Não faz merge, não resolve, não reverte nada e não altera
nenhuma Transaction — apenas detecta e registra.

Toda a lógica de candidatura/comparação/classificação vem do matcher
puro da unidade 4 (`app/domain/reconciliation/matcher.py`); este
módulo não reimplementa nenhum critério de matching, só decide QUAIS
Transactions comparar entre si (escopo e agrupamento por conta) e o
que fazer com o resultado (persistir como PENDING, se novo).

Sobre EQUIVALENT vs DIVERGENT (decisão do usuário para a Fase 10b):
ambos geram `ReconciliationLog PENDING` quando o par vem de fontes
diferentes. "EQUIVALENT" não autoriza nenhuma ação automática — só diz
que os campos comparados batem; a decisão de qual Transaction
permanece (se for o caso) continua sendo humana, na resolução (unidade
futura). O scan nunca faz MERGE nem marca nada como REVERSED.

Complexidade: comparação O(n²) DENTRO de cada conta (Transactions de
contas diferentes nunca são comparadas entre si — nem pelo agrupamento
aqui, nem pelo matcher, que já rejeita `account_id` diferente). Para
poucas centenas/milhares de Transactions por conta isso é aceitável;
se o volume crescer a ponto de doer, a otimização natural é reduzir o
espaço de busca (ex.: janela por data antes do produto cartesiano) —
não implementada aqui por não haver necessidade comprovada (ver §43 do
handoff).

Unidade 7 acrescenta a INTEGRAÇÃO com os fluxos de criação/correção
(`check_after_creation`, D-H1: checagem síncrona pós-operação) e de
importação (`check_batch_after_import` + `run_batch_reconciliation_task`,
chamada em uma única `BackgroundTask` por lote, com sessão própria). A
regra que atravessa toda essa unidade: uma falha da reconciliação
NUNCA pode desfazer ou impedir a operação financeira que a disparou —
por isso `check_after_creation` nunca propaga exceção, e a
`BackgroundTask` de import faz seu próprio commit/rollback numa sessão
independente da requisição que já respondeu.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from itertools import combinations
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.domain.reconciliation.matcher import classify, compare_transactions, match

logger = logging.getLogger(__name__)

from app.domain.reconciliation.types import MatchResult, TransactionSnapshot
from app.models.account import Account
from app.models.enums import ReconciliationStatus
from app.models.portfolio import Portfolio
from app.models.reconciliation_log import ReconciliationLog
from app.models.transaction import Transaction
from app.repositories.transactions import get_active_transactions_for_accounts
from app.schemas.reconciliation import ReconciliationDecision
from app.services.exceptions import (
    InvalidMergeSurvivorError,
    InvalidScanScopeError,
    PortfolioNotFoundError,
    ReconciliationAlreadyResolvedError,
    ReconciliationLogNotFoundError,
    TransactionNotFoundError,
)
from app.services.transaction_service import _get_owned_account, reverse_transaction

_DECISION_TO_STATUS = {
    ReconciliationDecision.IGNORE: ReconciliationStatus.IGNORED,
    ReconciliationDecision.KEEP_BOTH: ReconciliationStatus.KEPT_BOTH,
}


def _get_owned_portfolio(db: Session, portfolio_id: UUID, user_id: UUID) -> Portfolio:
    portfolio = db.get(Portfolio, portfolio_id)
    if portfolio is None or portfolio.user_id != user_id:
        # Mesmo padrão de _get_owned_account: não distingue "não existe"
        # de "não é seu", para não vazar a existência do registro alheio.
        raise PortfolioNotFoundError(f"portfolio {portfolio_id} não encontrado")
    return portfolio


def _resolve_account_ids(
    db: Session, user_id: UUID, account_id: UUID | None, portfolio_id: UUID | None
) -> list[UUID]:
    """Resolve o escopo do scan para uma lista de `account_id`,
    validando posse. Nunca aceita `account_id`/`portfolio_id` vindos do
    cliente sem checar que pertencem a `user_id`.
    """
    if account_id is not None and portfolio_id is not None:
        raise InvalidScanScopeError(
            "informe account_id OU portfolio_id, nunca os dois — ou nenhum, para escanear "
            "todas as contas do usuário"
        )

    if account_id is not None:
        account = _get_owned_account(db, account_id, user_id)
        return [account.id]

    if portfolio_id is not None:
        _get_owned_portfolio(db, portfolio_id, user_id)
        stmt = select(Account.id).where(
            Account.user_id == user_id, Account.portfolio_id == portfolio_id
        )
        return list(db.execute(stmt).scalars().all())

    # Sem escopo: todas as contas do usuário (scan global).
    stmt = select(Account.id).where(Account.user_id == user_id)
    return list(db.execute(stmt).scalars().all())


def _existing_pairs(db: Session, transaction_ids: list[UUID]) -> set[tuple[UUID, UUID]]:
    """Pares que já têm `ReconciliationLog`, em QUALQUER status. Um par
    já registrado nunca é recriado: PENDING não duplica, e um já
    resolvido (IGNORED/KEPT_BOTH/MERGED) não é reapresentado — a
    reabertura de um caso resolvido é decisão humana explícita
    (resolução), não algo que o scan deva fazer sozinho. Isso também
    cobre STALE por ora; a Fase 10b não trata "re-escanear um par
    STALE" nesta unidade.
    """
    if not transaction_ids:
        return set()
    stmt = select(ReconciliationLog.transaction_a_id, ReconciliationLog.transaction_b_id).where(
        ReconciliationLog.transaction_a_id.in_(transaction_ids)
        | ReconciliationLog.transaction_b_id.in_(transaction_ids)
    )
    return {(a, b) for a, b in db.execute(stmt).all()}


def scan_for_reconciliation(
    db: Session,
    user_id: UUID,
    *,
    account_id: UUID | None = None,
    portfolio_id: UUID | None = None,
) -> list[ReconciliationLog]:
    """Executa o scan e devolve os `ReconciliationLog` NOVOS criados
    (PENDING). Não comprete a transação — como `reverse_transaction`,
    a atomicidade com o restante da operação do chamador (ex.: rodar
    dentro de uma `BackgroundTask` própria) é responsabilidade de quem
    chama.

    Escopo (mutuamente exclusivo): uma conta, um portfolio (todas as
    contas dele), ou nenhum dos dois (todas as contas do usuário).
    Busca só Transactions ACTIVE; REVERSED nunca entra no matching.
    """
    account_ids = _resolve_account_ids(db, user_id, account_id, portfolio_id)
    if not account_ids:
        return []

    transactions = get_active_transactions_for_accounts(db, account_ids)
    if len(transactions) < 2:
        return []

    existing = _existing_pairs(db, [t.id for t in transactions])

    by_account: dict[UUID, list[Transaction]] = {}
    for tx in transactions:
        by_account.setdefault(tx.account_id, []).append(tx)

    created: list[ReconciliationLog] = []
    for account_transactions in by_account.values():
        # combinations() gera cada par NÃO ORDENADO uma única vez —
        # (A,B) e (B,A) nunca são avaliados separadamente aqui, e o
        # matcher ainda canonicaliza o resultado por conta própria.
        for row_a, row_b in combinations(account_transactions, 2):
            result = match(
                TransactionSnapshot.from_transaction(row_a),
                TransactionSnapshot.from_transaction(row_b),
            )
            if result is None:
                continue

            pair = (result.transaction_a.id, result.transaction_b.id)
            if pair in existing:
                continue

            # Mesma proteção da unidade 7: INSERT isolado em SAVEPOINT.
            # Se outro processo (outro scan, uma checagem pós-criação
            # ou a BackgroundTask de import) registrou este par depois
            # da leitura de `existing`, o UNIQUE rejeita só ESTE insert
            # — tratado como benigno, o scan segue com os demais pares.
            log = _create_reconciliation_log_safe(db, user_id, pair, result.match_reason)
            existing.add(pair)
            if log is not None:
                created.append(log)

    if created:
        db.flush()

    return created


def _get_owned_pending_log(db: Session, log_id: UUID, user_id: UUID) -> ReconciliationLog:
    """Busca o log com lock de linha (mesmo padrão de `reverse_transaction`:
    evita que duas resoluções concorrentes do MESMO log passem ambas
    pela checagem de status) e valida posse. Não valida status aqui —
    quem chama decide o que fazer com um status que não seja PENDING.
    """
    log = db.get(ReconciliationLog, log_id, with_for_update=True)
    if log is None or log.user_id != user_id:
        # Mesmo padrão de _get_owned_account/_get_owned_portfolio: não
        # distingue "não existe" de "não é seu".
        raise ReconciliationLogNotFoundError(f"reconciliação {log_id} não encontrada")
    return log


def _get_owned_log(db: Session, log_id: UUID, user_id: UUID) -> ReconciliationLog:
    """Como `_get_owned_pending_log`, mas para LEITURA: sem lock de
    linha (nada é alterado) e sem nenhuma expectativa de status — o
    chamador pode consultar um log em qualquer status. Mesmo padrão de
    posse do projeto: não distingue "não existe" de "não é seu".
    """
    log = db.get(ReconciliationLog, log_id)
    if log is None or log.user_id != user_id:
        raise ReconciliationLogNotFoundError(f"reconciliação {log_id} não encontrada")
    return log


def get_comparison(db: Session, user_id: UUID, log_id: UUID) -> MatchResult:
    """Comparação campo a campo do par de um `ReconciliationLog` —
    Fase 11, unidade backend 2. Leitura pura: não altera Transaction
    nem log, e funciona para qualquer status do log (o par continua
    inspecionável depois de resolvido).

    A comparação e a classificação são RECALCULADAS pelo matcher
    (`compare_transactions` + `classify`) a partir das duas
    Transactions — nada é reimplementado aqui. `match()` NÃO é usado de
    propósito: ele reavalia `is_candidate`, o que não faz sentido para
    um par que já está registrado (é exibição, não descoberta) e
    devolveria `None` para pares que deixaram de ser candidatos.

    `match_reason` devolvido é o texto GUARDADO no log (registro
    histórico do momento da detecção), nunca um texto regenerado — é
    informação complementar; a fonte estrutural é `comparison`.

    O par já está em ordem canônica no log (`transaction_a_id <
    transaction_b_id`, garantido por CHECK no banco), então A/B aqui
    são os mesmos A/B do log.
    """
    log = _get_owned_log(db, log_id, user_id)

    transaction_a = db.get(Transaction, log.transaction_a_id)
    transaction_b = db.get(Transaction, log.transaction_b_id)
    if transaction_a is None or transaction_b is None:
        # Defensivo: as FKs do log impedem isso; se acontecer, é o
        # mesmo 404 genérico do restante do projeto.
        raise TransactionNotFoundError(
            f"transações do par da reconciliação {log_id} não encontradas"
        )

    snapshot_a = TransactionSnapshot.from_transaction(transaction_a)
    snapshot_b = TransactionSnapshot.from_transaction(transaction_b)
    comparison = compare_transactions(snapshot_a, snapshot_b)
    return MatchResult(
        transaction_a=snapshot_a,
        transaction_b=snapshot_b,
        comparison=comparison,
        classification=classify(comparison),
        match_reason=log.match_reason,
    )


def list_pending(db: Session, user_id: UUID) -> list[ReconciliationLog]:
    """`ReconciliationLog PENDING` do usuário autenticado, mais
    recentes primeiro. Nunca inclui logs de outro usuário.
    """
    stmt = (
        select(ReconciliationLog)
        .where(
            ReconciliationLog.user_id == user_id,
            ReconciliationLog.status == ReconciliationStatus.PENDING,
        )
        .order_by(ReconciliationLog.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def resolve_reconciliation(
    db: Session,
    user_id: UUID,
    log_id: UUID,
    decision: ReconciliationDecision,
    surviving_transaction_id: UUID | None = None,
) -> ReconciliationLog:
    """Resolve um `ReconciliationLog PENDING` com uma decisão humana.

    IGNORE e KEEP_BOTH: alteram SOMENTE o log (`status` +
    `resolved_at`). Nenhuma Transaction é tocada.

    MERGE: `surviving_transaction_id` precisa ser exatamente uma das
    duas Transactions do par (senão `InvalidMergeSurvivorError`, e
    NADA muda). A outra é revertida via `reverse_transaction` — a
    MESMA função da unidade 2, sem reimplementar nenhuma validação de
    histórico. Se ela rejeitar a reversão, a exceção sobe e o MERGE
    inteiro falha: como esta função não comita (a transação de banco é
    do chamador/`get_db`, seguindo o padrão do projeto), nenhuma
    alteração — nem na Transaction, nem no log — sobrevive ao rollback
    que o chamador faz ao ver a exceção propagar.

    Só um log PENDING pode ser resolvido; qualquer outro status
    (IGNORED, KEPT_BOTH, MERGED, STALE) levanta
    `ReconciliationAlreadyResolvedError` e não faz NENHUMA alteração —
    nem tenta a reversão do MERGE antes de checar o status.
    """
    log = _get_owned_pending_log(db, log_id, user_id)
    if log.status != ReconciliationStatus.PENDING:
        raise ReconciliationAlreadyResolvedError(
            f"reconciliação {log_id} já está {log.status} — não pode ser resolvida novamente"
        )

    now = datetime.now(UTC)

    if decision == ReconciliationDecision.MERGE:
        pair = (log.transaction_a_id, log.transaction_b_id)
        if surviving_transaction_id not in pair:
            raise InvalidMergeSurvivorError(
                f"surviving_transaction_id {surviving_transaction_id} não pertence ao par "
                f"{pair[0]}/{pair[1]}"
            )
        reversed_id = pair[0] if surviving_transaction_id == pair[1] else pair[1]

        # Se reverse_transaction levantar, a exceção sobe sem que
        # NENHUMA das linhas abaixo seja executada — o log permanece
        # PENDING (e o rollback do chamador desfaz o que quer que
        # reverse_transaction já tenha preparado na sessão).
        reverse_transaction(db, user_id, reversed_id)

        log.surviving_transaction_id = surviving_transaction_id
        log.reversed_transaction_id = reversed_id
        log.status = ReconciliationStatus.MERGED
    else:
        log.status = _DECISION_TO_STATUS[decision]

    log.resolved_at = now
    db.flush()
    return log


# --- Unidade 7: integração com criação/correção e importação --------------


def _create_reconciliation_log_safe(
    db: Session, user_id: UUID, pair: tuple[UUID, UUID], match_reason: str
) -> ReconciliationLog | None:
    """Cria UM `ReconciliationLog PENDING` para `pair`, isolado num
    SAVEPOINT próprio (`db.begin_nested()`).

    Se OUTRO processo já criou o MESMO par entre a checagem de
    existência (feita por quem chama) e este ponto — corrida real
    entre duas checagens concorrentes, o risco que a Unidade 5 deixou
    registrado —, o `UNIQUE(transaction_a_id, transaction_b_id)`
    rejeita esta segunda tentativa. Tratamos ESSE conflito específico
    como benigno (o resultado desejado — o par registrado — já existe)
    e devolvemos `None`, sem logar como erro. QUALQUER outro
    `IntegrityError` (ex.: uma FK quebrada) é RELANÇADO — não
    mascaramos erros inesperados atrás dessa tolerância.

    O savepoint garante que, nos dois casos, só o INSERT desta função
    é desfeito — nunca o que a chamadora já tenha preparado antes.
    """
    try:
        with db.begin_nested():
            log = ReconciliationLog(
                user_id=user_id,
                transaction_a_id=pair[0],
                transaction_b_id=pair[1],
                match_reason=match_reason,
            )
            db.add(log)
            db.flush()
            return log
    except IntegrityError as exc:
        if "uq_reconciliation_logs_pair" in str(exc.orig):
            return None
        raise


def _check_after_creation_unsafe(
    db: Session, user_id: UUID, transaction: Transaction
) -> list[ReconciliationLog]:
    """Núcleo da checagem pós-criação (D-H1): compara `transaction`
    contra as DEMAIS ACTIVE da MESMA conta (mesmo escopo do matcher —
    nada aqui reimplementa critério nenhum, só decide o QUE comparar).
    Não recompara as demais entre si — isso já foi feito, uma a uma,
    quando cada uma delas foi criada. Pode levantar (chamado só através
    de `check_after_creation`, que isola e nunca deixa escapar).
    """
    siblings = [
        row
        for row in get_active_transactions_for_accounts(db, [transaction.account_id])
        if row.id != transaction.id
    ]
    if not siblings:
        return []

    target_snapshot = TransactionSnapshot.from_transaction(transaction)
    existing = _existing_pairs(db, [transaction.id, *[s.id for s in siblings]])

    created: list[ReconciliationLog] = []
    for sibling in siblings:
        result = match(target_snapshot, TransactionSnapshot.from_transaction(sibling))
        if result is None:
            continue
        pair = (result.transaction_a.id, result.transaction_b.id)
        if pair in existing:
            continue
        log = _create_reconciliation_log_safe(db, user_id, pair, result.match_reason)
        existing.add(pair)  # nunca tentar de novo o mesmo par nesta chamada
        if log is not None:
            created.append(log)

    if created:
        db.flush()
    return created


def check_after_creation(
    db: Session, user_id: UUID, transaction: Transaction
) -> list[ReconciliationLog]:
    """Checagem síncrona pós-criação/correção (D-H1 — "automática/pós-
    operação"). Chamada pelos routers logo após `POST /transactions` e
    `POST /transactions/{id}/correct` criarem uma Transaction nova.

    CONTRATO: NUNCA levanta exceção, e NUNCA deixa a Transaction que a
    disparou em risco. Todo o trabalho roda dentro de UM SAVEPOINT
    (`db.begin_nested()`); se qualquer coisa inesperada acontecer —
    incluindo um `IntegrityError` que não seja o conflito de par
    duplicado já tratado internamente —, o savepoint desfaz só o que
    esta função tentou fazer, o erro é registrado com
    `logger.exception` (contexto: usuário, Transaction e conta) e a
    função devolve `[]`. Quem chama nunca precisa de try/except.

    Só cria `ReconciliationLog PENDING`. Nunca MERGE, IGNORE, KEEP_BOTH
    ou REVERSED.
    """
    try:
        with db.begin_nested():
            return _check_after_creation_unsafe(db, user_id, transaction)
    except Exception:
        logger.exception(
            "Falha na checagem de reconciliação pós-criação "
            "(user_id=%s, transaction_id=%s, account_id=%s)",
            user_id,
            transaction.id,
            transaction.account_id,
        )
        return []


def check_batch_after_import(
    db: Session, user_id: UUID, transaction_ids: list[UUID]
) -> list[ReconciliationLog]:
    """Reconciliação em LOTE após um `POST /imports/commit` (D-H1 +
    integração de import, unidade 7): roda `check_after_creation` uma
    vez para cada Transaction recém-importada, contra TODAS as ACTIVE
    da conta — as demais recém-importadas incluídas, já visíveis nesta
    sessão porque o commit do import acontece ANTES desta função ser
    chamada (ver `run_batch_reconciliation_task`). Nunca compara duas
    Transactions pré-existentes entre si (já coberto quando cada uma
    foi criada). Como cada chamada de `check_after_creation` já é
    isolada e nunca propaga, uma falha numa Transaction do lote não
    impede a checagem das demais.
    """
    created: list[ReconciliationLog] = []
    for transaction_id in transaction_ids:
        transaction = db.get(Transaction, transaction_id)
        if transaction is None:
            continue  # defensivo; não deveria acontecer logo após o commit
        created.extend(check_after_creation(db, user_id, transaction))
    return created


def run_batch_reconciliation_task(
    user_id: UUID, account_id: UUID, transaction_ids: list[UUID]
) -> None:
    """Ponto de entrada da `BackgroundTask` agendada por
    `POST /imports/commit` (uma única tarefa por lote — nunca uma por
    linha).

    Abre sua PRÓPRIA sessão via `get_session()` — a sessão do request
    já foi fechada quando esta função roda. Isso só enxerga as
    Transactions do import porque o endpoint já deu `commit()` real
    ANTES de agendar esta tarefa (ver `app/api/routers/imports.py`);
    sem esse commit explícito, esta sessão nova não veria nada.

    Nunca deixa uma falha aqui alterar o resultado financeiro do
    import, reverter Transactions, ou impedir a resposta já enviada
    (que já foi enviada de qualquer forma) — só comita
    `ReconciliationLog`s novos, ou reverte e registra em caso de erro.
    Fecha a sessão em qualquer cenário.
    """
    session = get_session()
    try:
        created = check_batch_after_import(session, user_id, transaction_ids)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception(
            "Falha na reconciliação em lote pós-import "
            "(user_id=%s, account_id=%s, transaction_count=%d, operation=import_commit)",
            user_id,
            account_id,
            len(transaction_ids),
        )
    else:
        if created:
            logger.info(
                "Reconciliação pós-import criou %d ReconciliationLog(s) "
                "(user_id=%s, account_id=%s, operation=import_commit)",
                len(created),
                user_id,
                account_id,
            )
    finally:
        session.close()
