"""Classificação do livro de caixa (CF-2): categorias, tags,
classificação manual, regras e quebra por categoria.

Princípios:

- nada aqui altera o FATO de um lançamento;
- regra é determinística e explicável: a primeira que casa decide, e o
  lançamento guarda qual foi (`classified_by_rule_id`);
- decisão manual vence sempre: lançamento classificado à mão nunca é
  tocado por regra;
- transferência não é classificada por aqui.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from uuid import UUID

from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.cashflow_engine import (
    CashflowSummaryCalculator,
    CategoryBreakdownCalculator,
    RuleSpec,
    RuleTarget,
    first_matching_rule,
    parse_description,
)
from app.models.account import Account
from app.models.cashflow_classification import (
    CashflowCategory,
    CashflowRule,
    CashflowTag,
    cashflow_entry_tags,
    cashflow_rule_tags,
)
from app.models.cashflow_entry import CashflowEntry
from app.models.enums import AccountType, CashflowEntryStatus, CashflowNature
from app.repositories import cashflow as cashflow_repo
from app.schemas.cashflow import CashflowEntryRead
from app.schemas.cashflow_classification import (
    CategoryBreakdown,
    CategoryTotalsRead,
    CategoryWrite,
    CurrencyCategoryBreakdown,
    EntryClassificationWrite,
    RuleApplyChange,
    RuleApplyRequest,
    RuleApplyResult,
    RuleRead,
    RuleWrite,
    TagWrite,
)
from app.services import cashflow_service
from app.services.exceptions import (
    AccountNotFoundError,
    CashflowCategoryNotFoundError,
    CashflowClassificationInUseError,
    CashflowEntryAlreadyReversedError,
    CashflowRuleNotFoundError,
    CashflowTagNotFoundError,
    DuplicateRegistryEntryError,
    InvalidCashflowClassificationError,
    InvalidCashflowPeriodError,
)

# Árvore inicial, derivada do histórico real (CF-0, seção 6) — não é
# imposta: só é criada quando o usuário pede, e pode ser editada.
DEFAULT_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Moradia e contas", ("Energia", "Telefone e internet", "Gás")),
    ("Alimentação", ("Mercado", "Restaurantes e delivery")),
    ("Transporte", ("Aplicativo", "Transporte público", "Estacionamento")),
    ("Saúde", ("Odontologia", "Farmácia", "Academia", "Suplementos")),
    ("Cuidados pessoais", ()),
    ("Vestuário", ()),
    ("Eletrônicos e games", ()),
    ("Lazer e viagens", ("Cinema e ingressos", "Hospedagem")),
    ("Assinaturas e software", ()),
    ("Educação", ()),
    ("Presentes e doações", ()),
    ("Compras diversas", ()),
    ("Transferências a pessoas", ()),
    ("Encargos financeiros", ()),
    ("Salário", ()),
)


# --- Categorias --------------------------------------------------------------


def list_categories(db: Session, user_id: UUID) -> list[CashflowCategory]:
    stmt = (
        select(CashflowCategory)
        .where(CashflowCategory.user_id == user_id)
        .order_by(CashflowCategory.name, CashflowCategory.id)
    )
    return list(db.execute(stmt).scalars().all())


def _get_category(db: Session, user_id: UUID, category_id: UUID) -> CashflowCategory:
    category = db.get(CashflowCategory, category_id)
    if category is None or category.user_id != user_id:
        raise CashflowCategoryNotFoundError(f"categoria {category_id} não encontrada")
    return category


def _check_parent(db: Session, user_id: UUID, parent_id: UUID | None, own_id: UUID | None) -> None:
    if parent_id is None:
        return
    if parent_id == own_id:
        raise InvalidCashflowClassificationError("uma categoria não pode ser pai dela mesma")
    parent = _get_category(db, user_id, parent_id)
    if parent.parent_id is not None:
        raise InvalidCashflowClassificationError(
            f"{parent.name} já é uma subcategoria: o máximo são dois níveis"
        )
    if (
        own_id is not None
        and db.execute(
            select(CashflowCategory.id).where(CashflowCategory.parent_id == own_id).limit(1)
        ).first()
    ):
        raise InvalidCashflowClassificationError(
            "esta categoria tem subcategorias e não pode virar subcategoria"
        )


def create_category(db: Session, user_id: UUID, payload: CategoryWrite) -> CashflowCategory:
    _check_parent(db, user_id, payload.parent_id, None)
    category = CashflowCategory(user_id=user_id, name=payload.name, parent_id=payload.parent_id)
    try:
        with db.begin_nested():
            db.add(category)
            db.flush()
    except IntegrityError as exc:
        raise DuplicateRegistryEntryError(
            f"já existe uma categoria chamada {payload.name} neste nível"
        ) from exc
    return category


def update_category(
    db: Session, user_id: UUID, category_id: UUID, payload: CategoryWrite
) -> CashflowCategory:
    category = _get_category(db, user_id, category_id)
    _check_parent(db, user_id, payload.parent_id, category.id)
    try:
        with db.begin_nested():
            category.name = payload.name
            category.parent_id = payload.parent_id
            db.flush()
    except IntegrityError as exc:
        db.refresh(category)
        raise DuplicateRegistryEntryError(
            f"já existe uma categoria chamada {payload.name} neste nível"
        ) from exc
    return category


def delete_category(db: Session, user_id: UUID, category_id: UUID) -> None:
    category = _get_category(db, user_id, category_id)
    checks = (
        (
            select(CashflowCategory.id).where(CashflowCategory.parent_id == category.id),
            "tem subcategorias",
        ),
        (
            select(CashflowEntry.id).where(CashflowEntry.category_id == category.id),
            "tem lançamentos",
        ),
        (
            select(CashflowRule.id).where(CashflowRule.set_category_id == category.id),
            "é usada por regras",
        ),
    )
    for stmt, reason in checks:
        if db.execute(stmt.limit(1)).first():
            raise CashflowClassificationInUseError(
                f"a categoria {category.name} {reason} e não pode ser excluída"
            )
    db.delete(category)
    db.flush()


def create_default_categories(db: Session, user_id: UUID) -> list[CashflowCategory]:
    """Cria o que faltar da árvore inicial. Idempotente: o que já existe
    (pelo nome, no mesmo nível) é mantido como está.
    """
    existing = {(c.parent_id, c.name): c for c in list_categories(db, user_id)}
    for root_name, children in DEFAULT_CATEGORIES:
        root = existing.get((None, root_name))
        if root is None:
            root = CashflowCategory(user_id=user_id, name=root_name)
            db.add(root)
            db.flush()
            existing[(None, root_name)] = root
        for child_name in children:
            if (root.id, child_name) not in existing:
                child = CashflowCategory(user_id=user_id, name=child_name, parent_id=root.id)
                db.add(child)
                existing[(root.id, child_name)] = child
    db.flush()
    return list_categories(db, user_id)


# --- Tags --------------------------------------------------------------------


def list_tags(db: Session, user_id: UUID) -> list[CashflowTag]:
    stmt = (
        select(CashflowTag)
        .where(CashflowTag.user_id == user_id)
        .order_by(CashflowTag.tag_group, CashflowTag.name, CashflowTag.id)
    )
    return list(db.execute(stmt).scalars().all())


def _get_tag(db: Session, user_id: UUID, tag_id: UUID) -> CashflowTag:
    tag = db.get(CashflowTag, tag_id)
    if tag is None or tag.user_id != user_id:
        raise CashflowTagNotFoundError(f"tag {tag_id} não encontrada")
    return tag


def create_tag(db: Session, user_id: UUID, payload: TagWrite) -> CashflowTag:
    tag = CashflowTag(user_id=user_id, name=payload.name, tag_group=payload.tag_group)
    try:
        with db.begin_nested():
            db.add(tag)
            db.flush()
    except IntegrityError as exc:
        raise DuplicateRegistryEntryError(f"já existe a tag {payload.name} neste grupo") from exc
    return tag


def update_tag(db: Session, user_id: UUID, tag_id: UUID, payload: TagWrite) -> CashflowTag:
    tag = _get_tag(db, user_id, tag_id)
    try:
        with db.begin_nested():
            tag.name = payload.name
            tag.tag_group = payload.tag_group
            db.flush()
    except IntegrityError as exc:
        db.refresh(tag)
        raise DuplicateRegistryEntryError(f"já existe a tag {payload.name} neste grupo") from exc
    return tag


def delete_tag(db: Session, user_id: UUID, tag_id: UUID) -> None:
    """Tag é só um marcador: excluir a tira dos lançamentos e das
    regras (CASCADE), sem mudar natureza nem categoria de nada.
    """
    tag = _get_tag(db, user_id, tag_id)
    db.delete(tag)
    db.flush()


def _check_tags(db: Session, user_id: UUID, tag_ids: Iterable[UUID]) -> list[UUID]:
    unique = list(dict.fromkeys(tag_ids))
    for tag_id in unique:
        _get_tag(db, user_id, tag_id)
    return unique


# --- Leitura de lançamentos com classificação ---------------------------------


def _tags_by_entry(db: Session, entry_ids: list[UUID]) -> dict[UUID, list[UUID]]:
    if not entry_ids:
        return {}
    rows = db.execute(
        select(cashflow_entry_tags.c.entry_id, cashflow_entry_tags.c.tag_id)
        .where(cashflow_entry_tags.c.entry_id.in_(entry_ids))
        .order_by(cashflow_entry_tags.c.tag_id)
    ).all()
    result: dict[UUID, list[UUID]] = {}
    for entry_id, tag_id in rows:
        result.setdefault(entry_id, []).append(tag_id)
    return result


def to_read(db: Session, entries: list[CashflowEntry]) -> list[CashflowEntryRead]:
    """Lançamentos com as tags e o texto que as regras enxergam."""
    tags = _tags_by_entry(db, [e.id for e in entries])
    return [
        CashflowEntryRead.model_validate(entry).model_copy(
            update={
                "tag_ids": tags.get(entry.id, []),
                "match_text": parse_description(entry.description).match_text,
            }
        )
        for entry in entries
    ]


def _replace_entry_tags(db: Session, entry_id: UUID, tag_ids: Iterable[UUID]) -> None:
    db.execute(delete(cashflow_entry_tags).where(cashflow_entry_tags.c.entry_id == entry_id))
    rows = [{"entry_id": entry_id, "tag_id": tag_id} for tag_id in tag_ids]
    if rows:
        db.execute(insert(cashflow_entry_tags), rows)


# --- Classificação manual -----------------------------------------------------


def classify_entry(
    db: Session, user_id: UUID, entry_id: UUID, payload: EntryClassificationWrite
) -> CashflowEntry:
    entry = cashflow_service._get_owned_entry(db, user_id, entry_id, lock=True)
    if entry.status is CashflowEntryStatus.REVERSED:
        raise CashflowEntryAlreadyReversedError(f"lançamento {entry_id} está estornado")
    if entry.nature is CashflowNature.TRANSFER or payload.nature is CashflowNature.TRANSFER:
        raise InvalidCashflowClassificationError(
            "transferência não é reclassificada: estorne e registre de novo"
        )
    if payload.category_id is not None:
        _get_category(db, user_id, payload.category_id)
    tag_ids = _check_tags(db, user_id, payload.tag_ids)

    entry.nature = payload.nature
    entry.category_id = payload.category_id
    # Decisão manual: a regra que tinha classificado deixa de valer aqui.
    entry.classified_by_rule_id = None
    _replace_entry_tags(db, entry.id, tag_ids)
    db.flush()
    return entry


# --- Regras -------------------------------------------------------------------


def _rule_tag_ids(db: Session, rule_ids: list[UUID]) -> dict[UUID, list[UUID]]:
    if not rule_ids:
        return {}
    rows = db.execute(
        select(cashflow_rule_tags.c.rule_id, cashflow_rule_tags.c.tag_id)
        .where(cashflow_rule_tags.c.rule_id.in_(rule_ids))
        .order_by(cashflow_rule_tags.c.tag_id)
    ).all()
    result: dict[UUID, list[UUID]] = {}
    for rule_id, tag_id in rows:
        result.setdefault(rule_id, []).append(tag_id)
    return result


def _load_rules(db: Session, user_id: UUID) -> list[CashflowRule]:
    stmt = (
        select(CashflowRule)
        .where(CashflowRule.user_id == user_id)
        .order_by(CashflowRule.priority, CashflowRule.created_at, CashflowRule.id)
    )
    return list(db.execute(stmt).scalars().all())


def _rule_read(rule: CashflowRule, tag_ids: list[UUID]) -> RuleRead:
    return RuleRead(
        id=rule.id,
        name=rule.name,
        priority=rule.priority,
        is_active=rule.is_active,
        match_type=rule.match_type,
        pattern=rule.pattern,
        direction=rule.direction,
        account_id=rule.account_id,
        set_nature=rule.set_nature,
        set_category_id=rule.set_category_id,
        tag_ids=tag_ids,
    )


def list_rules(db: Session, user_id: UUID) -> list[RuleRead]:
    rules = _load_rules(db, user_id)
    tags = _rule_tag_ids(db, [r.id for r in rules])
    return [_rule_read(rule, tags.get(rule.id, [])) for rule in rules]


def _get_rule(db: Session, user_id: UUID, rule_id: UUID) -> CashflowRule:
    rule = db.get(CashflowRule, rule_id)
    if rule is None or rule.user_id != user_id:
        raise CashflowRuleNotFoundError(f"regra {rule_id} não encontrada")
    return rule


def _validate_rule(db: Session, user_id: UUID, payload: RuleWrite) -> list[UUID]:
    if payload.set_nature is CashflowNature.TRANSFER:
        raise InvalidCashflowClassificationError(
            "regra não classifica como transferência: transferência tem contraparte"
        )
    if payload.set_nature is CashflowNature.UNCLASSIFIED:
        raise InvalidCashflowClassificationError(
            "a regra precisa definir uma natureza (renda, gasto, terceiros ou ajuste)"
        )
    if payload.set_category_id is not None:
        _get_category(db, user_id, payload.set_category_id)
    if payload.account_id is not None:
        account = db.get(Account, payload.account_id)
        if account is None or account.user_id != user_id:
            raise AccountNotFoundError(f"conta {payload.account_id} não encontrada")
        if account.account_type is AccountType.BROKERAGE:
            raise InvalidCashflowClassificationError(
                "regra do livro de caixa não se aplica a conta de investimentos"
            )
    return _check_tags(db, user_id, payload.tag_ids)


def _apply_rule_payload(rule: CashflowRule, payload: RuleWrite) -> None:
    rule.name = payload.name
    rule.priority = payload.priority
    rule.is_active = payload.is_active
    rule.match_type = payload.match_type
    rule.pattern = payload.pattern
    rule.direction = payload.direction
    rule.account_id = payload.account_id
    rule.set_nature = payload.set_nature
    rule.set_category_id = payload.set_category_id


def _replace_rule_tags(db: Session, rule_id: UUID, tag_ids: list[UUID]) -> None:
    db.execute(delete(cashflow_rule_tags).where(cashflow_rule_tags.c.rule_id == rule_id))
    if tag_ids:
        db.execute(
            insert(cashflow_rule_tags),
            [{"rule_id": rule_id, "tag_id": tag_id} for tag_id in tag_ids],
        )


def create_rule(db: Session, user_id: UUID, payload: RuleWrite) -> RuleRead:
    tag_ids = _validate_rule(db, user_id, payload)
    rule = CashflowRule(user_id=user_id)
    _apply_rule_payload(rule, payload)
    db.add(rule)
    db.flush()
    _replace_rule_tags(db, rule.id, tag_ids)
    return _rule_read(rule, sorted(tag_ids))


def update_rule(db: Session, user_id: UUID, rule_id: UUID, payload: RuleWrite) -> RuleRead:
    rule = _get_rule(db, user_id, rule_id)
    tag_ids = _validate_rule(db, user_id, payload)
    _apply_rule_payload(rule, payload)
    db.flush()
    _replace_rule_tags(db, rule.id, tag_ids)
    return _rule_read(rule, sorted(tag_ids))


def delete_rule(db: Session, user_id: UUID, rule_id: UUID) -> None:
    """Excluir a regra não desfaz o que ela classificou: os lançamentos
    ficam como estão, só deixam de apontar para ela (passam a contar
    como decisão manual).
    """
    rule = _get_rule(db, user_id, rule_id)
    db.delete(rule)
    db.flush()


def apply_rules(
    db: Session,
    user_id: UUID,
    request: RuleApplyRequest,
    *,
    dry_run: bool,
    only_entry_ids: set[UUID] | None = None,
) -> RuleApplyResult:
    """Avalia as regras ativas sobre os lançamentos elegíveis.

    Elegível: ACTIVE, não é transferência e (a) ainda não classificado
    — natureza UNCLASSIFIED, sem categoria, sem regra — ou, com
    `reevaluate`, (b) classificado por regra. O grupo (b) é reavaliado
    do zero: se nenhuma regra casa mais, volta a não classificado.
    Lançamento classificado à mão nunca entra.
    """
    if request.start and request.end and request.start > request.end:
        raise InvalidCashflowPeriodError("início do período depois do fim")
    if request.account_id is not None:
        account_ids = [cashflow_service._get_owned_account(db, request.account_id, user_id).id]
    else:
        account_ids = [a.id for a in cashflow_repo.list_cash_accounts(db, user_id)]

    rules = [r for r in _load_rules(db, user_id) if r.is_active]
    rule_tags = _rule_tag_ids(db, [r.id for r in rules])
    names = {r.id: r.name for r in rules}
    specs = [
        RuleSpec(
            rule_id=r.id,
            priority=r.priority,
            order=index,
            match_type=r.match_type,
            pattern=r.pattern,
            direction=r.direction,
            account_id=r.account_id,
            set_nature=r.set_nature,
            set_category_id=r.set_category_id,
            tag_ids=frozenset(rule_tags.get(r.id, [])),
        )
        for index, r in enumerate(rules)
    ]

    if not account_ids:
        return RuleApplyResult(applied=not dry_run, examined=0, changes=[])
    stmt = select(CashflowEntry).where(
        CashflowEntry.account_id.in_(account_ids),
        CashflowEntry.status == CashflowEntryStatus.ACTIVE,
        CashflowEntry.nature != CashflowNature.TRANSFER,
    )
    if only_entry_ids is not None:
        # Importação: só os lançamentos que acabaram de entrar.
        stmt = stmt.where(CashflowEntry.id.in_(only_entry_ids))
    if request.start is not None:
        stmt = stmt.where(CashflowEntry.entry_date >= request.start)
    if request.end is not None:
        stmt = stmt.where(CashflowEntry.entry_date <= request.end)
    stmt = stmt.order_by(CashflowEntry.entry_date, CashflowEntry.created_at, CashflowEntry.id)
    if not dry_run:
        stmt = stmt.with_for_update()
    entries = list(db.execute(stmt).scalars().all())
    current_tags = _tags_by_entry(db, [e.id for e in entries])

    examined = 0
    changes: list[RuleApplyChange] = []
    for entry in entries:
        by_rule = entry.classified_by_rule_id is not None
        untouched = (
            not by_rule
            and entry.nature is CashflowNature.UNCLASSIFIED
            and entry.category_id is None
        )
        if not (untouched or (by_rule and request.reevaluate)):
            continue
        examined += 1
        match_text = parse_description(entry.description).match_text
        chosen = first_matching_rule(
            specs,
            RuleTarget(match_text=match_text, amount=entry.amount, account_id=entry.account_id),
        )
        if chosen is None:
            new_nature, new_category, new_tags, new_rule = (
                CashflowNature.UNCLASSIFIED,
                None,
                [],
                None,
            )
        else:
            new_nature = chosen.set_nature
            new_category = chosen.set_category_id
            new_tags = sorted(chosen.tag_ids)
            new_rule = chosen.rule_id
        old_tags = sorted(current_tags.get(entry.id, []))
        if (
            entry.nature is new_nature
            and entry.category_id == new_category
            and entry.classified_by_rule_id == new_rule
            and old_tags == new_tags
        ):
            continue
        changes.append(
            RuleApplyChange(
                entry_id=entry.id,
                description=entry.description,
                match_text=match_text,
                amount=entry.amount,
                currency_code=entry.currency_code,
                entry_date=entry.entry_date,
                rule_id=new_rule,
                rule_name=names.get(new_rule) if new_rule else None,
                nature=new_nature,
                category_id=new_category,
                tag_ids=new_tags,
            )
        )
        if not dry_run:
            entry.nature = new_nature
            entry.category_id = new_category
            entry.classified_by_rule_id = new_rule
            _replace_entry_tags(db, entry.id, new_tags)
    if not dry_run:
        db.flush()
    return RuleApplyResult(applied=not dry_run, examined=examined, changes=changes)


# --- Quebra por categoria -------------------------------------------------------


def get_category_breakdown(db: Session, user_id: UUID, start: date, end: date) -> CategoryBreakdown:
    if start > end:
        raise InvalidCashflowPeriodError("início do período depois do fim")
    categories = {c.id: c for c in list_categories(db, user_id)}
    parent_of = {c.id: c.parent_id for c in categories.values()}
    _accounts, facts = cashflow_service._load_facts(db, user_id, until=end)
    breakdown = CategoryBreakdownCalculator.calculate(facts, start, end, parent_of)
    summaries = CashflowSummaryCalculator.calculate(facts, start, end)

    blocks: list[CurrencyCategoryBreakdown] = []
    for currency, rows in breakdown.items():
        summary = summaries[currency]
        own_expenses = sum((r.own_expenses for r in rows), start=summary.expenses * 0)
        own_income = sum((r.own_income for r in rows), start=summary.income * 0)
        if own_expenses != summary.expenses or own_income != summary.income:
            # Mesma política do resumo: se não fecha, não devolve número.
            raise RuntimeError(
                f"quebra por categoria não fecha com o resumo em {currency}: "
                f"gastos {own_expenses} x {summary.expenses}, renda {own_income} x {summary.income}"
            )

        def _sort_key(row):
            category = categories.get(row.category_id) if row.category_id else None
            return (category is None, category.name if category else "")

        blocks.append(
            CurrencyCategoryBreakdown(
                currency_code=currency,
                expenses=summary.expenses,
                income=summary.income,
                categories=[
                    CategoryTotalsRead(
                        category_id=row.category_id,
                        category_name=(
                            categories[row.category_id].name if row.category_id else None
                        ),
                        parent_id=(parent_of[row.category_id] if row.category_id else None),
                        own_expenses=row.own_expenses,
                        own_income=row.own_income,
                        total_expenses=row.total_expenses,
                        total_income=row.total_income,
                    )
                    for row in sorted(rows, key=_sort_key)
                ],
            )
        )
    return CategoryBreakdown(start=start, end=end, totals_by_currency=blocks)
