import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.database import get_session
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


async def _get_transaction_for_user(
    session: AsyncSession,
    current_user: User,
    transaction_id: uuid.UUID,
) -> Transaction:
    result = await session.execute(
        select(Transaction)
        .options(selectinload(Transaction.subcategory))
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
        base_query = base_query.where(Transaction.category == category)
    if subcategory_id:
        base_query = base_query.where(Transaction.subcategory_id == subcategory_id)
    if account:
        base_query = base_query.where(Transaction.account == account)
    if type:
        base_query = base_query.where(Transaction.type == TransactionType(type))

    count_result = await session.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar_one()

    items_query = (
        base_query.options(selectinload(Transaction.subcategory))
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
        if body.category and subcategory.category.name != body.category:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="subcategory_id does not belong to category",
            )

    transaction = Transaction(
        id=uuid.uuid4(),
        user_id=current_user.id,
        amount=body.amount,
        currency=body.currency,
        type=TransactionType(body.type),
        account=body.account,
        category=body.category,
        subcategory_id=body.subcategory_id,
        description=body.description,
        note=body.note,
        installments=body.installments,
        account_destination=body.account_destination,
        expense_date=body.expense_date,
    )
    session.add(transaction)
    await session.commit()
    return await _get_transaction_for_user(session, current_user, transaction.id)


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

    if "subcategory_id" in update_data:
        new_subcategory_id = update_data["subcategory_id"]
        if new_subcategory_id is not None:
            subcategory = await _get_subcategory(session, current_user, new_subcategory_id)
            category_name = update_data.get("category", transaction.category)
            if category_name and subcategory.category.name != category_name:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="subcategory_id does not belong to category",
                )
    elif "category" in update_data and transaction.subcategory_id is not None:
        subcategory = await _get_subcategory(session, current_user, transaction.subcategory_id)
        new_category_name = update_data.get("category")
        if new_category_name and subcategory.category.name != new_category_name:
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
