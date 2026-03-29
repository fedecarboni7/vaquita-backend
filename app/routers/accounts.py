import uuid
from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models.account import Account
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.schemas.accounts import AccountCreate, AccountResponse, AccountUpdate

router = APIRouter(prefix="/accounts", tags=["accounts"])


async def _calculate_balances_by_account(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> dict[str, float]:
    result = await session.execute(
        select(
            Transaction.account,
            Transaction.account_destination,
            Transaction.type,
            Transaction.amount,
        ).where(Transaction.user_id == user_id)
    )
    balances: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    for account_name, account_destination, transaction_type, amount in result.all():
        amount_decimal = Decimal(str(amount))
        if transaction_type == TransactionType.income:
            balances[account_name] += amount_decimal
        elif transaction_type == TransactionType.expense:
            balances[account_name] -= amount_decimal
        elif transaction_type == TransactionType.transfer:
            balances[account_name] -= amount_decimal
            if account_destination:
                balances[account_destination] += amount_decimal

    return {name: float(balance) for name, balance in balances.items()}


@router.get("", response_model=list[AccountResponse])
async def list_accounts(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[AccountResponse]:
    result = await session.execute(select(Account).where(Account.user_id == current_user.id).order_by(Account.name))
    accounts = result.scalars().all()
    balances_by_account = await _calculate_balances_by_account(session, current_user.id)

    return [
        AccountResponse(
            id=account.id,
            name=account.name,
            account_type=account.account_type,
            currency=account.currency,
            balance=balances_by_account.get(account.name, 0.0),
            created_at=account.created_at,
        )
        for account in accounts
    ]


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    body: AccountCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AccountResponse:
    account = Account(
        id=uuid.uuid4(),
        user_id=current_user.id,
        name=body.name,
        account_type=body.account_type,
        currency=body.currency,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return AccountResponse(
        id=account.id,
        name=account.name,
        account_type=account.account_type,
        currency=account.currency,
        balance=0.0,
        created_at=account.created_at,
    )


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    account = await session.get(Account, account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    await session.delete(account)
    await session.commit()


@router.put("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: uuid.UUID,
    body: AccountUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AccountResponse:
    account = await session.get(Account, account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    previous_name = account.name

    account.name = body.name
    account.account_type = body.account_type
    account.currency = body.currency

    if previous_name != body.name:
        await session.execute(
            update(Transaction)
            .where(
                Transaction.user_id == current_user.id,
                Transaction.account == previous_name,
            )
            .values(account=body.name)
        )
        await session.execute(
            update(Transaction)
            .where(
                Transaction.user_id == current_user.id,
                Transaction.account_destination == previous_name,
            )
            .values(account_destination=body.name)
        )

    await session.commit()
    await session.refresh(account)

    balances_by_account = await _calculate_balances_by_account(session, current_user.id)
    return AccountResponse(
        id=account.id,
        name=account.name,
        account_type=account.account_type,
        currency=account.currency,
        balance=balances_by_account.get(account.name, 0.0),
        created_at=account.created_at,
    )
