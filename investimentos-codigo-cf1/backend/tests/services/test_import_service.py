from datetime import date
from decimal import Decimal

import pytest

from app.domain.financial_engine.position import PositionCalculator
from app.models.enums import TransactionSource, TransactionType
from app.models.transaction import Transaction
from app.repositories.transactions import get_active_transactions
from app.schemas.transaction import TransactionCreate
from app.services import import_service
from app.services.exceptions import (
    AccountNotFoundError,
    ImportRowRejectedError,
    InvalidImportSignatureError,
)
from app.services.transaction_service import create_transaction
from tests.test_persistence import make_account, make_asset, make_institution, make_user

CSV_HEADER = b"data,tipo,ativo,quantidade,preco_unitario,taxas,valor,moeda\n"


def _setup(db):
    user = make_user(db, email=f"import-{id(db)}@example.com")
    institution = make_institution(db, name=f"Inst Import {id(db)}")
    account = make_account(db, user, institution, name=f"Conta Import {id(db)}")
    return user, account


class TestPreviewNaoAlteraOBanco:
    def test_preview_nao_grava_nada(self, db_session):
        user, account = _setup(db_session)
        make_asset(db_session, ticker="IMP1")
        content = CSV_HEADER + b"2026-01-05,COMPRA,IMP1,10,10.00,0,100.00,BRL\n"

        before = len(get_active_transactions(db_session, account.id))
        import_service.generate_preview(db_session, user.id, account.id, "CSV", content)
        after = len(get_active_transactions(db_session, account.id))

        assert before == after == 0


class TestLoteValidoECompleto:
    def test_todas_as_linhas_validas_sao_gravadas(self, db_session):
        user, account = _setup(db_session)
        make_asset(db_session, ticker="IMP2")
        content = (
            CSV_HEADER
            + b"2026-01-05,COMPRA,IMP2,10,10.00,0,100.00,BRL\n"
            + b"2026-01-10,DEPOSITO,,,,,500.00,BRL\n"
        )

        preview = import_service.generate_preview(db_session, user.id, account.id, "CSV", content)
        commit_request = _build_commit_request(preview, include_all=True)

        result = import_service.commit_import(db_session, user.id, commit_request)

        assert result.imported_count == 2
        assert result.excluded_count == 0
        assert len(get_active_transactions(db_session, account.id)) == 2


class TestTudoOuNada:
    def test_uma_linha_invalida_reverte_o_lote_inteiro(self, db_session):
        user, account = _setup(db_session)
        make_asset(db_session, ticker="IMP3")
        # SELL de 100 sem nenhuma posição -> viola D-A3
        content = (
            CSV_HEADER
            + b"2026-01-05,DEPOSITO,,,,,500.00,BRL\n"
            + b"2026-01-06,VENDA,IMP3,100,10.00,0,1000.00,BRL\n"
        )

        preview = import_service.generate_preview(db_session, user.id, account.id, "CSV", content)
        commit_request = _build_commit_request(preview, include_all=True)

        # SAVEPOINT: numa request real, get_db faz rollback de uma
        # transação de banco NOVA (o setup já estaria commitado antes).
        # Aqui, setup e operação compartilham a mesma transação de
        # teste — begin_nested() isola o rollback do commit sem desfazer
        # o setup (mesmo efeito prático de get_db numa request separada).
        with pytest.raises(ImportRowRejectedError), db_session.begin_nested():
            import_service.commit_import(db_session, user.id, commit_request)

        # nenhuma das duas linhas deve ter ficado gravada (nem o DEPOSITO válido)
        assert len(get_active_transactions(db_session, account.id)) == 0

    def test_erro_inesperado_de_persistencia_reverte_o_lote(self, db_session):
        user, account = _setup(db_session)
        make_asset(db_session, ticker="IMP4")

        # Um DEPOSIT manual já existente, com external_reference definido manualmente
        # simulando uma referência que vai colidir com a importação.
        existing = Transaction(
            account_id=account.id,
            asset_id=None,
            transaction_type=TransactionType.DEPOSIT,
            fees=Decimal(0),
            gross_amount=Decimal("10.00"),
            currency_code="BRL",
            transaction_date=date(2026, 1, 1),
            source=TransactionSource.IMPORT_CSV,
            external_reference="colisao-forcada:0",
        )
        db_session.add(existing)
        db_session.flush()

        content = (
            CSV_HEADER
            + b"2026-01-05,DEPOSITO,,,,,100.00,BRL\n"
            + b"2026-01-06,DEPOSITO,,,,,200.00,BRL\n"
        )
        preview = import_service.generate_preview(db_session, user.id, account.id, "CSV", content)
        # força colisão de external_reference na segunda linha, simulando erro de persistência
        preview.rows[1].external_reference = "colisao-forcada:0"
        # a assinatura precisa ser recalculada para o teste conseguir passar da checagem de HMAC
        # e cair de fato no erro de persistência (não no erro de assinatura)
        preview.signature = import_service._sign(
            import_service._canonical_payload_bytes(
                preview.account_id, preview.source_format, preview.rows
            )
        )
        commit_request = _build_commit_request(preview, include_all=True)

        with pytest.raises(ImportRowRejectedError), db_session.begin_nested():
            import_service.commit_import(db_session, user.id, commit_request)

        # só a transação pré-existente continua lá — nada do lote foi gravado
        remaining = get_active_transactions(db_session, account.id)
        assert len(remaining) == 1
        assert remaining[0].gross_amount == Decimal("10.00")


class TestLinhasIdenticasNoMesmoArquivo:
    def test_duas_compras_identicas_no_mesmo_lote_sao_ambas_importadas(self, db_session):
        user, account = _setup(db_session)
        make_asset(db_session, ticker="IMP5")
        content = (
            CSV_HEADER
            + b"2026-01-05,COMPRA,IMP5,10,10.00,0,100.00,BRL\n"
            + b"2026-01-05,COMPRA,IMP5,10,10.00,0,100.00,BRL\n"
        )

        preview = import_service.generate_preview(db_session, user.id, account.id, "CSV", content)
        assert preview.rows[0].external_reference != preview.rows[1].external_reference
        assert not preview.rows[0].is_exact_duplicate
        assert not preview.rows[1].is_exact_duplicate

        commit_request = _build_commit_request(preview, include_all=True)
        result = import_service.commit_import(db_session, user.id, commit_request)

        assert result.imported_count == 2


class TestReimportacaoDoMesmoArquivo:
    def test_reimportar_o_mesmo_arquivo_detecta_duplicata_exata(self, db_session):
        user, account = _setup(db_session)
        make_asset(db_session, ticker="IMP6")
        content = CSV_HEADER + b"2026-01-05,COMPRA,IMP6,10,10.00,0,100.00,BRL\n"

        preview_1 = import_service.generate_preview(db_session, user.id, account.id, "CSV", content)
        commit_1 = _build_commit_request(preview_1, include_all=True)
        import_service.commit_import(db_session, user.id, commit_1)

        preview_2 = import_service.generate_preview(db_session, user.id, account.id, "CSV", content)
        assert preview_2.rows[0].is_exact_duplicate is True


class TestPossibleDuplicateEntreFontes:
    def test_manual_seguido_de_importacao_equivalente_marca_possible_duplicate(self, db_session):
        user, account = _setup(db_session)
        asset = make_asset(db_session, ticker="IMP7")

        create_transaction(
            db_session,
            user.id,
            TransactionCreate(
                account_id=account.id,
                asset_id=asset.id,
                transaction_type=TransactionType.BUY,
                quantity=Decimal(10),
                unit_price=Decimal(10),
                fees=Decimal(0),
                gross_amount=Decimal(100),
                currency_code="BRL",
                transaction_date=date(2026, 1, 5),
            ),
        )

        content = CSV_HEADER + b"2026-01-05,COMPRA,IMP7,10,10.00,0,100.00,BRL\n"
        preview = import_service.generate_preview(db_session, user.id, account.id, "CSV", content)

        assert (
            preview.rows[0].is_exact_duplicate is False
        )  # fontes diferentes, sem external_reference igual
        assert preview.rows[0].possible_duplicate is True


class TestAssinaturaHMAC:
    def test_payload_alterado_e_rejeitado(self, db_session):
        user, account = _setup(db_session)
        make_asset(db_session, ticker="IMP8")
        content = CSV_HEADER + b"2026-01-05,COMPRA,IMP8,10,10.00,0,100.00,BRL\n"

        preview = import_service.generate_preview(db_session, user.id, account.id, "CSV", content)
        commit_request = _build_commit_request(preview, include_all=True)
        commit_request.rows[0].gross_amount = Decimal("999999.00")  # adulterado após a preview

        with pytest.raises(InvalidImportSignatureError):
            import_service.commit_import(db_session, user.id, commit_request)


class TestInclusaoExclusaoDeLinhas:
    def test_somente_linhas_incluidas_sao_processadas(self, db_session):
        user, account = _setup(db_session)
        make_asset(db_session, ticker="IMP9")
        content = (
            CSV_HEADER
            + b"2026-01-05,DEPOSITO,,,,,100.00,BRL\n"
            + b"2026-01-06,DEPOSITO,,,,,200.00,BRL\n"
        )
        preview = import_service.generate_preview(db_session, user.id, account.id, "CSV", content)
        commit_request = _build_commit_request(preview, include_all=False, included=[0])

        result = import_service.commit_import(db_session, user.id, commit_request)

        assert result.imported_count == 1
        assert result.excluded_count == 1
        transactions = get_active_transactions(db_session, account.id)
        assert len(transactions) == 1
        assert transactions[0].gross_amount == Decimal("100.00")


class TestOrdemCronologica:
    def test_sell_antes_da_buy_no_arquivo_mas_com_data_posterior_e_aceita(self, db_session):
        user, account = _setup(db_session)
        make_asset(db_session, ticker="IMP10")
        # SELL aparece PRIMEIRO no arquivo, mas sua data é POSTERIOR à BUY.
        content = (
            CSV_HEADER
            + b"2026-02-01,VENDA,IMP10,5,12.00,0,60.00,BRL\n"
            + b"2026-01-01,COMPRA,IMP10,10,10.00,0,100.00,BRL\n"
        )

        preview = import_service.generate_preview(db_session, user.id, account.id, "CSV", content)
        # confirma que a preview já devolve ordenado cronologicamente
        assert preview.rows[0].transaction_type == TransactionType.BUY
        assert preview.rows[1].transaction_type == TransactionType.SELL

        commit_request = _build_commit_request(preview, include_all=True)
        result = import_service.commit_import(db_session, user.id, commit_request)

        assert result.imported_count == 2


class TestRegressaoFinanceira:
    def test_importacao_produz_a_mesma_posicao_que_lancamento_manual_equivalente(self, db_session):
        user, account_manual = _setup(db_session)
        institution = make_institution(db_session, name=f"Inst Import Regressao {id(db_session)}")
        account_import = make_account(
            db_session, user, institution, name=f"Conta Import Regressao {id(db_session)}"
        )
        asset = make_asset(db_session, ticker="IMP11")

        create_transaction(
            db_session,
            user.id,
            TransactionCreate(
                account_id=account_manual.id,
                asset_id=asset.id,
                transaction_type=TransactionType.BUY,
                quantity=Decimal(100),
                unit_price=Decimal(10),
                fees=Decimal(0),
                gross_amount=Decimal(1000),
                currency_code="BRL",
                transaction_date=date(2026, 1, 1),
            ),
        )

        content = CSV_HEADER + b"2026-01-01,COMPRA,IMP11,100,10.00,0,1000.00,BRL\n"
        preview = import_service.generate_preview(
            db_session, user.id, account_import.id, "CSV", content
        )
        commit_request = _build_commit_request(preview, include_all=True)
        import_service.commit_import(db_session, user.id, commit_request)

        manual_facts = get_active_transactions(db_session, account_manual.id, asset.id)
        import_facts = get_active_transactions(db_session, account_import.id, asset.id)

        manual_result = PositionCalculator.calculate(manual_facts)
        import_result = PositionCalculator.calculate(import_facts)

        assert manual_result.quantity == import_result.quantity
        assert manual_result.average_cost == import_result.average_cost
        assert manual_result.total_cost_basis == import_result.total_cost_basis


class TestIsolamentoDeUsuario:
    def test_importar_para_conta_de_outro_usuario_e_rejeitado(self, db_session):
        user, _account = _setup(db_session)
        outro_user = make_user(db_session, email=f"outro-import-{id(db_session)}@example.com")
        institution = make_institution(db_session, name=f"Inst Outro Import {id(db_session)}")
        conta_de_outro = make_account(
            db_session, outro_user, institution, name=f"Conta De Outro Import {id(db_session)}"
        )

        content = CSV_HEADER + b"2026-01-05,DEPOSITO,,,,,100.00,BRL\n"
        with pytest.raises(AccountNotFoundError):
            import_service.generate_preview(db_session, user.id, conta_de_outro.id, "CSV", content)


def _build_commit_request(preview, include_all: bool, included: list[int] | None = None):
    from app.schemas.imports import ImportCommitRequest

    indexes = [r.row_index for r in preview.rows] if include_all else (included or [])
    return ImportCommitRequest(
        account_id=preview.account_id,
        source_format=preview.source_format,
        rows=preview.rows,
        signature=preview.signature,
        included_row_indexes=indexes,
    )
