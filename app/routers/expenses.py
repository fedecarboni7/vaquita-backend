import uuid
from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_FLOOR

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.database import get_session
from app.models.account import Account
from app.models.category import Category
from app.models.subcategory import Subcategory
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.schemas.expenses import (
    PaginatedTransactionsResponse,
    TransactionCreate,
    TransactionResponse,
    TransactionUpdate,
)

router = APIRouter(prefix="/expenses", tags=["expenses"])
MONEY_SCALE = Decimal("0.01")


def _add_months(base_date: date, months: int) -> date:
    month_index = (base_date.month - 1) + months
    target_year = base_date.year + (month_index // 12)
    target_month = (month_index % 12) + 1
    target_day = min(base_date.day, monthrange(target_year, target_month)[1])
    return date(target_year, target_month, target_day)


def _build_installment_description(
    base_description: str,
    total_amount: Decimal,
    installment_number: int,
    installments: int,
) -> str:
    return f"{base_description} (Total: ${total_amount:.2f} - Cuota {installment_number}/{installments})"


def _build_transaction(
    *,
    user_id: uuid.UUID,
    amount: Decimal,
    currency: str,
    transaction_type: TransactionType,
    account: str,
    category_id: uuid.UUID | None,
    subcategory_id: uuid.UUID | None,
    description: str,
    note: str | None,
    installments: int | None,
    account_destination: str | None,
    expense_date: date,
) -> Transaction:
    return Transaction(
        id=uuid.uuid4(),
        user_id=user_id,
        amount=amount,
        currency=currency,
        type=transaction_type,
        account=account,
        category_id=category_id,
        subcategory_id=subcategory_id,
        description=description,
        note=note,
        installments=installments,
        account_destination=account_destination,
        expense_date=expense_date,
    )


async def _validate_account_currency_match(
    session: AsyncSession,
    current_user: User,
    account_name: str,
    currency: str,
) -> None:
    result = await session.execute(
        select(Account.currency).where(
            Account.user_id == current_user.id,
            Account.name == account_name,
        )
    )
    account_currency = result.scalar_one_or_none()
    if account_currency is None:
        return

    if account_currency != currency:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"La cuenta '{account_name}' opera en {account_currency}. "
                f"No se puede registrar una transacción en {currency}."
            ),
        )


async def _get_subcategory(
    session: AsyncSession,
    current_user: User,
    subcategory_id: uuid.UUID,
) -> Subcategory:
    result = await session.execute(
        select(Subcategory)
        .options(selectinload(Subcategory.category))
        .where(Subcategory.id == subcategory_id, Subcategory.user_id == current_user.id)
    )
    subcategory = result.scalar_one_or_none()
    if not subcategory:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid subcategory_id")
    return subcategory


async def _get_category(
    session: AsyncSession,
    current_user: User,
    category_id: uuid.UUID,
) -> Category:
    result = await session.execute(
        select(Category).where(Category.id == category_id, Category.user_id == current_user.id)
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category_id")
    return category


async def _get_transaction_for_user(
    session: AsyncSession,
    current_user: User,
    transaction_id: uuid.UUID,
) -> Transaction:
    result = await session.execute(
        select(Transaction)
        .options(selectinload(Transaction.subcategory), selectinload(Transaction.category))
        .where(Transaction.id == transaction_id, Transaction.user_id == current_user.id)
    )
    transaction = result.scalar_one_or_none()
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return transaction


@router.get("", response_model=PaginatedTransactionsResponse)
async def list_expenses(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    category: str | None = Query(None),
    subcategory_id: uuid.UUID | None = Query(None),
    account: str | None = Query(None),
    type: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PaginatedTransactionsResponse:
    base_query = select(Transaction).where(Transaction.user_id == current_user.id)

    if date_from:
        base_query = base_query.where(Transaction.expense_date >= date_from)
    if date_to:
        base_query = base_query.where(Transaction.expense_date <= date_to)
    if category:
        base_query = base_query.where(Transaction.category.has(Category.name == category))
    if subcategory_id:
        base_query = base_query.where(Transaction.subcategory_id == subcategory_id)
    if account:
        base_query = base_query.where(Transaction.account == account)
    if type:
        base_query = base_query.where(Transaction.type == TransactionType(type))

    count_result = await session.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    items_query = (
        base_query.options(selectinload(Transaction.subcategory), selectinload(Transaction.category))
        .order_by(Transaction.expense_date.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(items_query)
    items = result.scalars().all()

    return PaginatedTransactionsResponse(
        items=items,
        total=total,
        has_more=(offset + limit) < total,
    )


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_expense(
    body: TransactionCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TransactionResponse:
    if body.subcategory_id:
        subcategory = await _get_subcategory(session, current_user, body.subcategory_id)
        if body.category_id:
            if subcategory.category_id != body.category_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="subcategory_id does not belong to category",
                )
        else:
            # Derive category from the subcategory when not explicitly provided
            body.category_id = subcategory.category_id
    elif body.category_id:
        await _get_category(session, current_user, body.category_id)

    await _validate_account_currency_match(session, current_user, body.account, body.currency)
    if body.type == "transfer" and body.account_destination:
        await _validate_account_currency_match(session, current_user, body.account_destination, body.currency)

    transaction_type = TransactionType(body.type)
    total_amount = Decimal(str(body.amount)).quantize(MONEY_SCALE)

    if body.installments is not None:
        installments = body.installments
        if installments <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="installments must be greater than 0",
            )

        installment_amount = (total_amount / installments).quantize(MONEY_SCALE, rounding=ROUND_FLOOR)
        residual = (total_amount - (installment_amount * installments)).quantize(MONEY_SCALE)

        transactions: list[Transaction] = []
        for index in range(installments):
            installment_number = index + 1
            current_amount = installment_amount
            if installment_number == installments:
                current_amount += residual

            transactions.append(
                _build_transaction(
                    user_id=current_user.id,
                    amount=current_amount,
                    currency=body.currency,
                    transaction_type=transaction_type,
                    account=body.account,
                    category_id=body.category_id,
                    subcategory_id=body.subcategory_id,
                    description=_build_installment_description(
                        base_description=body.description,
                        total_amount=total_amount,
                        installment_number=installment_number,
                        installments=installments,
                    ),
                    note=body.note,
                    installments=installments,
                    account_destination=body.account_destination,
                    expense_date=_add_months(body.expense_date, index),
                )
            )

        session.add_all(transactions)
        created_transaction_id = transactions[0].id
    else:
        transaction = _build_transaction(
            user_id=current_user.id,
            amount=total_amount,
            currency=body.currency,
            transaction_type=transaction_type,
            account=body.account,
            category_id=body.category_id,
            subcategory_id=body.subcategory_id,
            description=body.description,
            note=body.note,
            installments=body.installments,
            account_destination=body.account_destination,
            expense_date=body.expense_date,
        )
        session.add(transaction)
        created_transaction_id = transaction.id

    await session.commit()
    return await _get_transaction_for_user(session, current_user, created_transaction_id)


@router.put("/{transaction_id}", response_model=TransactionResponse)
async def update_expense(
    transaction_id: uuid.UUID,
    body: TransactionUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TransactionResponse:
    transaction = await _get_transaction_for_user(session, current_user, transaction_id)

    update_data = body.model_dump(exclude_unset=True)
    if "type" in update_data:
        update_data["type"] = TransactionType(update_data["type"])

    resolved_currency = update_data.get("currency", transaction.currency)
    resolved_account = update_data.get("account", transaction.account)
    resolved_type = update_data.get("type", transaction.type)
    resolved_destination = update_data.get("account_destination", transaction.account_destination)

    await _validate_account_currency_match(session, current_user, resolved_account, resolved_currency)
    if resolved_type == TransactionType.transfer and resolved_destination:
        await _validate_account_currency_match(session, current_user, resolved_destination, resolved_currency)

    if "category_id" in update_data and update_data["category_id"] is not None:
        await _get_category(session, current_user, update_data["category_id"])

    if "subcategory_id" in update_data:
        new_subcategory_id = update_data["subcategory_id"]
        if new_subcategory_id is not None:
            subcategory = await _get_subcategory(session, current_user, new_subcategory_id)
            category_id = update_data.get("category_id", transaction.category_id)
            if category_id and subcategory.category_id != category_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="subcategory_id does not belong to category",
                )
    elif "category_id" in update_data and transaction.subcategory_id is not None:
        subcategory = await _get_subcategory(session, current_user, transaction.subcategory_id)
        new_category_id = update_data.get("category_id")
        if new_category_id and subcategory.category_id != new_category_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Current subcategory_id does not belong to category",
            )

    for field, value in update_data.items():
        setattr(transaction, field, value)

    await session.commit()
    return await _get_transaction_for_user(session, current_user, transaction.id)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(
    transaction_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    transaction = await _get_transaction_for_user(session, current_user, transaction_id)

    await session.delete(transaction)
    await session.commit()
