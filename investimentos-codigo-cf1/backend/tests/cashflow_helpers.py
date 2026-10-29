from app.models import Account
from app.models.enums import AccountType


def make_typed_account(
    session, user, institution, name, account_type=AccountType.CHECKING, currency_code="BRL"
) -> Account:
    account = Account(
        user_id=user.id,
        institution_id=institution.id,
        name=name,
        currency_code=currency_code,
        account_type=account_type,
    )
    session.add(account)
    session.flush()
    return account
