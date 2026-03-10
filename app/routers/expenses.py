import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.schemas.expenses import TransactionCreate, TransactionResponse, TransactionUpdate

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get("", response_model=list[TransactionResponse])
async def list_expenses(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    category: str | None = Query(None),
    type: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[TransactionResponse]:
    query = select(Transaction).where(Transaction.user_id == current_user.id)

    if date_from:
        query = query.where(Transaction.expense_date >= date_from)
    if date_to:
        query = query.where(Transaction.expense_date <= date_to)
    if category:
        query = query.where(Transaction.category == category)
    if type:
        query = query.where(Transaction.type == TransactionType(type))

    query = query.order_by(Transaction.expense_date.desc())

    result = await session.execute(query)
    return result.scalars().all()


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_expense(
    body: TransactionCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TransactionResponse:
    transaction = Transaction(
        id=uuid.uuid4(),
        user_id=current_user.id,
        amount=body.amount,
        currency=body.currency,
        type=TransactionType(body.type),
        account=body.account,
        category=body.category,
        subcategory=body.subcategory,
        description=body.description,
        note=body.note,
        expense_date=body.expense_date,
    )
    session.add(transaction)
    await session.commit()
    await session.refresh(transaction)
    return transaction


@router.put("/{transaction_id}", response_model=TransactionResponse)
async def update_expense(
    transaction_id: uuid.UUID,
    body: TransactionUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TransactionResponse:
    transaction = await session.get(Transaction, transaction_id)
    if not transaction or transaction.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    update_data = body.model_dump(exclude_unset=True)
    if "type" in update_data:
        update_data["type"] = TransactionType(update_data["type"])

    for field, value in update_data.items():
        setattr(transaction, field, value)

    await session.commit()
    await session.refresh(transaction)
    return transaction


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(
    transaction_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    transaction = await session.get(Transaction, transaction_id)
    if not transaction or transaction.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    await session.delete(transaction)
    await session.commit()
