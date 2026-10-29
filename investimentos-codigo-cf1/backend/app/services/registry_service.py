"""Cadastros: ativos, instituições, contas e carteiras.

Criação, listagem, edição e exclusão — nenhuma regra financeira vive
aqui. Ativos,
instituições, moedas e classes de ativo são cadastros GLOBAIS (não
pertencem a um usuário); contas e carteiras pertencem ao usuário
resolvido pela dependency de autenticação, nunca a um `user_id` vindo
do cliente.

Edição e exclusão respeitam o que já foi gravado: lançamentos
imutáveis referenciam esses cadastros (a moeda de um ativo, por
exemplo, é regra de validação da Moeda-3). O que os lançamentos
dependem só muda enquanto o cadastro não foi usado, e só se exclui o
que nunca foi usado.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.asset import Asset
from app.models.asset_class import AssetClass
from app.models.asset_price import AssetPrice
from app.models.cashflow_entry import CashflowEntry
from app.models.currency import Currency
from app.models.enums import AccountType
from app.models.institution import Institution
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction
from app.schemas.registry import AccountCreate, AssetCreate, InstitutionCreate, PortfolioCreate
from app.services.exceptions import (
    AccountNotFoundError,
    DuplicateRegistryEntryError,
    InvalidRegistryReferenceError,
    PortfolioNotFoundError,
    RegistryEntryNotFoundError,
    RegistryInUseError,
)


def list_currencies(db: Session) -> list[Currency]:
    return list(db.execute(select(Currency).order_by(Currency.code)).scalars().all())


def list_asset_classes(db: Session) -> list[AssetClass]:
    return list(db.execute(select(AssetClass).order_by(AssetClass.label)).scalars().all())


def list_assets(db: Session) -> list[Asset]:
    return list(db.execute(select(Asset).order_by(Asset.ticker, Asset.country)).scalars().all())


def list_institutions(db: Session) -> list[Institution]:
    return list(db.execute(select(Institution).order_by(Institution.name)).scalars().all())


def get_institution(db: Session, institution_id: UUID) -> Institution:
    return db.get(Institution, institution_id)


def _require_currency(db: Session, code: str) -> None:
    if db.get(Currency, code) is None:
        raise InvalidRegistryReferenceError(f"moeda {code} não cadastrada")


def create_asset(db: Session, payload: AssetCreate) -> Asset:
    _require_currency(db, payload.currency_code)
    if db.get(AssetClass, payload.asset_class_code) is None:
        raise InvalidRegistryReferenceError(
            f"classe de ativo {payload.asset_class_code} não cadastrada"
        )

    asset = Asset(
        ticker=payload.ticker,
        name=payload.name,
        asset_class_code=payload.asset_class_code,
        country=payload.country,
        currency_code=payload.currency_code,
        maturity_date=payload.maturity_date,
        annual_rate=payload.annual_rate,
    )
    try:
        with db.begin_nested():
            db.add(asset)
            db.flush()
    except IntegrityError as exc:
        raise DuplicateRegistryEntryError(
            f"já existe um ativo {payload.ticker} no país {payload.country}"
        ) from exc
    return asset


def create_institution(db: Session, payload: InstitutionCreate) -> Institution:
    institution = Institution(
        name=payload.name,
        institution_type=payload.institution_type,
        country=payload.country,
    )
    db.add(institution)
    db.flush()
    return institution


def create_portfolio(db: Session, user_id: UUID, payload: PortfolioCreate) -> Portfolio:
    portfolio = Portfolio(user_id=user_id, name=payload.name)
    try:
        with db.begin_nested():
            db.add(portfolio)
            db.flush()
    except IntegrityError as exc:
        raise DuplicateRegistryEntryError(f"já existe uma carteira chamada {payload.name}") from exc
    return portfolio


def create_account(db: Session, user_id: UUID, payload: AccountCreate) -> Account:
    institution = db.get(Institution, payload.institution_id)
    if institution is None:
        raise InvalidRegistryReferenceError(f"instituição {payload.institution_id} não encontrada")
    _require_currency(db, payload.currency_code)
    if payload.portfolio_id is not None:
        if payload.account_type is not AccountType.BROKERAGE:
            raise InvalidRegistryReferenceError(
                "carteira só pode ser vinculada a uma conta de investimentos"
            )
        portfolio = db.get(Portfolio, payload.portfolio_id)
        if portfolio is None or portfolio.user_id != user_id:
            # Mesmo padrão do projeto: não distingue "não existe" de
            # "não é sua".
            raise PortfolioNotFoundError(f"portfolio {payload.portfolio_id} não encontrado")

    account = Account(
        user_id=user_id,
        institution_id=institution.id,
        name=payload.name,
        currency_code=payload.currency_code,
        portfolio_id=payload.portfolio_id,
        account_type=payload.account_type,
    )
    try:
        with db.begin_nested():
            db.add(account)
            db.flush()
    except IntegrityError as exc:
        raise DuplicateRegistryEntryError(
            f"já existe uma conta chamada {payload.name} nesta instituição"
        ) from exc
    return account


# --- Edição e exclusão -----------------------------------------------------
# Regra geral: nome, classificação e vínculos mudam livremente; o que os
# lançamentos já gravados dependem (moeda, livro da conta) só muda
# enquanto o cadastro não foi usado. Excluir só o que nunca foi usado.


def _exists(db: Session, stmt) -> bool:
    return db.execute(stmt.limit(1)).first() is not None


def _account_usage(db: Session, account_id: UUID) -> bool:
    return (
        _exists(db, select(Transaction.id).where(Transaction.account_id == account_id))
        or _exists(db, select(CashflowEntry.id).where(CashflowEntry.account_id == account_id))
        or _exists(
            db,
            select(CashflowEntry.id).where(CashflowEntry.counterparty_account_id == account_id),
        )
    )


def _asset_usage(db: Session, asset_id: UUID) -> bool:
    return _exists(db, select(Transaction.id).where(Transaction.asset_id == asset_id)) or _exists(
        db, select(AssetPrice.id).where(AssetPrice.asset_id == asset_id)
    )


def _get_institution(db: Session, institution_id: UUID) -> Institution:
    institution = db.get(Institution, institution_id)
    if institution is None:
        raise RegistryEntryNotFoundError(f"instituição {institution_id} não encontrada")
    return institution


def _get_asset(db: Session, asset_id: UUID) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise RegistryEntryNotFoundError(f"ativo {asset_id} não encontrado")
    return asset


def _get_owned_portfolio(db: Session, user_id: UUID, portfolio_id: UUID) -> Portfolio:
    portfolio = db.get(Portfolio, portfolio_id)
    if portfolio is None or portfolio.user_id != user_id:
        raise PortfolioNotFoundError(f"portfolio {portfolio_id} não encontrado")
    return portfolio


def _get_owned_account(db: Session, user_id: UUID, account_id: UUID) -> Account:
    account = db.get(Account, account_id)
    if account is None or account.user_id != user_id:
        raise AccountNotFoundError(f"conta {account_id} não encontrada")
    return account


def update_institution(
    db: Session, institution_id: UUID, payload: InstitutionCreate
) -> Institution:
    institution = _get_institution(db, institution_id)
    institution.name = payload.name
    institution.institution_type = payload.institution_type
    institution.country = payload.country
    db.flush()
    return institution


def delete_institution(db: Session, institution_id: UUID) -> None:
    institution = _get_institution(db, institution_id)
    if _exists(db, select(Account.id).where(Account.institution_id == institution.id)):
        raise RegistryInUseError(
            f"a instituição {institution.name} tem contas: exclua ou mova as contas antes"
        )
    db.delete(institution)
    db.flush()


def update_portfolio(
    db: Session, user_id: UUID, portfolio_id: UUID, payload: PortfolioCreate
) -> Portfolio:
    portfolio = _get_owned_portfolio(db, user_id, portfolio_id)
    try:
        with db.begin_nested():
            portfolio.name = payload.name
            db.flush()
    except IntegrityError as exc:
        db.refresh(portfolio)
        raise DuplicateRegistryEntryError(f"já existe uma carteira chamada {payload.name}") from exc
    return portfolio


def delete_portfolio(db: Session, user_id: UUID, portfolio_id: UUID) -> None:
    portfolio = _get_owned_portfolio(db, user_id, portfolio_id)
    if _exists(db, select(Account.id).where(Account.portfolio_id == portfolio.id)):
        raise RegistryInUseError(
            f"a carteira {portfolio.name} tem contas vinculadas: desvincule as contas antes"
        )
    db.delete(portfolio)
    db.flush()


def update_account(db: Session, user_id: UUID, account_id: UUID, payload: AccountCreate) -> Account:
    """Nome, instituição e carteira mudam sempre. Moeda e livro
    (BROKERAGE x caixa) só mudam enquanto a conta não tem lançamento
    nem é contraparte de transferência: os lançamentos foram gravados
    na moeda e no livro da conta. Trocar entre tipos de caixa
    (corrente, reserva, cartão, dinheiro) é sempre permitido.
    """
    account = _get_owned_account(db, user_id, account_id)
    institution = db.get(Institution, payload.institution_id)
    if institution is None:
        raise InvalidRegistryReferenceError(f"instituição {payload.institution_id} não encontrada")
    _require_currency(db, payload.currency_code)
    if payload.portfolio_id is not None:
        if payload.account_type is not AccountType.BROKERAGE:
            raise InvalidRegistryReferenceError(
                "carteira só pode ser vinculada a uma conta de investimentos"
            )
        _get_owned_portfolio(db, user_id, payload.portfolio_id)

    currency_changes = payload.currency_code != account.currency_code
    ledger_changes = (payload.account_type is AccountType.BROKERAGE) != (
        account.account_type is AccountType.BROKERAGE
    )
    if (currency_changes or ledger_changes) and _account_usage(db, account.id):
        what = "a moeda" if currency_changes else "o tipo entre investimentos e caixa"
        raise RegistryInUseError(
            f"a conta {account.name} já tem lançamentos: não é possível trocar {what}"
        )

    try:
        with db.begin_nested():
            account.name = payload.name
            account.institution_id = institution.id
            account.currency_code = payload.currency_code
            account.portfolio_id = payload.portfolio_id
            account.account_type = payload.account_type
            db.flush()
    except IntegrityError as exc:
        db.refresh(account)
        raise DuplicateRegistryEntryError(
            f"já existe uma conta chamada {payload.name} nesta instituição"
        ) from exc
    return account


def delete_account(db: Session, user_id: UUID, account_id: UUID) -> None:
    account = _get_owned_account(db, user_id, account_id)
    if _account_usage(db, account.id):
        raise RegistryInUseError(
            f"a conta {account.name} já tem lançamentos e não pode ser excluída"
        )
    db.delete(account)
    db.flush()


def update_asset(db: Session, asset_id: UUID, payload: AssetCreate) -> Asset:
    """Ticker, nome, classe e país mudam sempre (o ticker de um ativo
    pode mudar na bolsa). A moeda só muda enquanto o ativo não tem
    lançamento nem cotação: ambos foram gravados na moeda do ativo.
    """
    asset = _get_asset(db, asset_id)
    _require_currency(db, payload.currency_code)
    if db.get(AssetClass, payload.asset_class_code) is None:
        raise InvalidRegistryReferenceError(
            f"classe de ativo {payload.asset_class_code} não cadastrada"
        )
    if payload.currency_code != asset.currency_code and _asset_usage(db, asset.id):
        raise RegistryInUseError(
            f"o ativo {asset.ticker} já tem lançamentos ou cotações: não é possível trocar a moeda"
        )
    try:
        with db.begin_nested():
            asset.ticker = payload.ticker
            asset.name = payload.name
            asset.asset_class_code = payload.asset_class_code
            asset.country = payload.country
            asset.currency_code = payload.currency_code
            # Ausente no corpo = mantém (telas antigas não mandam o campo).
            if "maturity_date" in payload.model_fields_set:
                asset.maturity_date = payload.maturity_date
            if "annual_rate" in payload.model_fields_set:
                asset.annual_rate = payload.annual_rate
            db.flush()
    except IntegrityError as exc:
        db.refresh(asset)
        raise DuplicateRegistryEntryError(
            f"já existe um ativo {payload.ticker} em {payload.country}"
        ) from exc
    return asset


def delete_asset(db: Session, asset_id: UUID) -> None:
    asset = _get_asset(db, asset_id)
    if _asset_usage(db, asset.id):
        raise RegistryInUseError(
            f"o ativo {asset.ticker} já tem lançamentos ou cotações e não pode ser excluído"
        )
    db.delete(asset)
    db.flush()
