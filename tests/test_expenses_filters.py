from uuid import uuid4

from sqlalchemy import select

from app.models.transaction import Transaction, TransactionType
from app.routers.expenses import _apply_list_expenses_filters


def _base_query():
    return select(Transaction).where(Transaction.user_id == uuid4())


def test_account_ids_filter_includes_source_or_destination_account_for_transfers() -> None:
    query = _apply_list_expenses_filters(
        _base_query(),
        date_from=None,
        date_to=None,
        category=None,
        category_ids=None,
        subcategory_id=None,
        subcategory_ids=None,
        account=None,
        account_id=None,
        account_ids=[uuid4()],
        type=None,
        types=None,
    )

    compiled_sql = str(query)

    assert "transactions.account_id IN" in compiled_sql
    assert "transactions.account_destination_id IN" in compiled_sql
    assert " OR " in compiled_sql


def test_legacy_account_id_filter_also_includes_destination_account() -> None:
    query = _apply_list_expenses_filters(
        _base_query(),
        date_from=None,
        date_to=None,
        category=None,
        category_ids=None,
        subcategory_id=None,
        subcategory_ids=None,
        account=None,
        account_id=uuid4(),
        account_ids=None,
        type=None,
        types=None,
    )

    compiled_sql = str(query)

    assert "transactions.account_id IN" in compiled_sql
    assert "transactions.account_destination_id IN" in compiled_sql


def test_multi_filters_use_array_variants_and_ignore_legacy_counterparts() -> None:
    query = _apply_list_expenses_filters(
        _base_query(),
        date_from=None,
        date_to=None,
        category="Legacy category name",
        category_ids=[uuid4(), uuid4()],
        subcategory_id=uuid4(),
        subcategory_ids=[uuid4(), uuid4()],
        account="Legacy account name",
        account_id=uuid4(),
        account_ids=[uuid4(), uuid4()],
        type="income",
        types=[TransactionType.expense, TransactionType.transfer],
    )

    compiled_sql = str(query)

    assert "transactions.category_id IN" in compiled_sql
    assert "transactions.subcategory_id IN" in compiled_sql
    assert "transactions.type IN" in compiled_sql
    assert "transactions.account_id IN" in compiled_sql
    assert "transactions.account_destination_id IN" in compiled_sql

    assert "categories.name" not in compiled_sql
    assert "accounts.name" not in compiled_sql
    assert "transactions.type =" not in compiled_sql
