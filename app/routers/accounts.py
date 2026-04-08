import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models.account import Account
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.schemas.accounts import (
    AccountAdjustRequest,
    AccountAdjustResponse,
    AccountCreate,
    AccountResponse,
    AccountUpdate,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])
MONEY_SCALE = Decimal("0.01")


def _resolve_include_in_total(account_type: str, include_in_total: bool | None) -> bool:
    if include_in_total is not None:
        return include_in_total
    return account_type != "credit_card"


def _build_credit_card_windows(
    account: Account,
) -> tuple[date, date] | None:
    if account.account_type != "credit_card":
        return None

    if account.billing_period_start is None or account.billing_period_end is None:
        return None

    if account.billing_period_end < account.billing_period_start:
        return None

    return (
        account.billing_period_start,
        account.billing_period_end,
    )


def _build_account_response(
    account: Account,
    balance: float,
    closed_period_balance: float | None,
) -> AccountResponse:
    return AccountResponse(
        id=account.id,
        name=account.name,
        account_type=account.account_type,
        currency=account.currency,
        include_in_total=account.include_in_total,
        billing_period_start=account.billing_period_start,
        billing_period_end=account.billing_period_end,
        payment_due_date=account.payment_due_date,
        closed_period_balance=closed_period_balance,
        balance=balance,
        created_at=account.created_at,
    )


async def _calculate_balances_by_account(
    session: AsyncSession,
    user_id: uuid.UUID,
    accounts: list[Account],
    today: date,
) -> tuple[dict[str, float], dict[str, float | None]]:
    del today
    windows_by_account_name: dict[str, tuple[date, date] | None] = {
        account.name: _build_credit_card_windows(account) for account in accounts
    }

    result = await session.execute(
        select(
            Transaction.account,
            Transaction.account_destination,
            Transaction.type,
            Transaction.amount,
            Transaction.expense_date,
        ).where(Transaction.user_id == user_id)
    )

    balances: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    closed_period_balances: dict[str, Decimal | None] = {}

    for account in accounts:
        windows = windows_by_account_name.get(account.name)
        if windows is None:
            closed_period_balances[account.name] = None
        else:
            closed_period_balances[account.name] = Decimal("0")

    def apply_delta(account_name: str | None, delta: Decimal, expense_date: date) -> None:
        if not account_name:
            return

        balances[account_name] += delta

        windows = windows_by_account_name.get(account_name)
        if windows is None:
            return

        closed_period_start, closed_period_end = windows
        if closed_period_start <= expense_date <= closed_period_end:
            closed_balance = closed_period_balances.get(account_name)
            if closed_balance is not None:
                closed_period_balances[account_name] = closed_balance + delta

    for account_name, account_destination, transaction_type, amount, expense_date in result.all():
        amount_decimal = Decimal(str(amount))

        if transaction_type == TransactionType.income:
            apply_delta(account_name, amount_decimal, expense_date)
        elif transaction_type == TransactionType.expense:
            apply_delta(account_name, -amount_decimal, expense_date)
        elif transaction_type == TransactionType.transfer:
            apply_delta(account_name, -amount_decimal, expense_date)
            apply_delta(account_destination, amount_decimal, expense_date)

    total_balances = {name: float(balance) for name, balance in balances.items()}
    closed_balances = {
        name: (None if balance is None else float(balance)) for name, balance in closed_period_balances.items()
    }
    return total_balances, closed_balances


@router.get("", response_model=list[AccountResponse])
async def list_accounts(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[AccountResponse]:
    today = date.today()
    result = await session.execute(select(Account).where(Account.user_id == current_user.id).order_by(Account.name))
    accounts = result.scalars().all()
    balances_by_account, closed_period_balances = await _calculate_balances_by_account(
        session,
        current_user.id,
        accounts,
        today,
    )

    return [
        _build_account_response(
            account,
            balances_by_account.get(account.name, 0.0),
            closed_period_balances.get(account.name),
        )
        for account in accounts
    ]


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AccountResponse:
    account = await session.get(Account, account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    today = date.today()
    balances_by_account, closed_period_balances = await _calculate_balances_by_account(
        session,
        current_user.id,
        [account],
        today,
    )
    return _build_account_response(
        account,
        balances_by_account.get(account.name, 0.0),
        closed_period_balances.get(account.name),
    )


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    body: AccountCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AccountResponse:
    include_in_total = _resolve_include_in_total(body.account_type, body.include_in_total)

    account = Account(
        id=uuid.uuid4(),
        user_id=current_user.id,
        name=body.name,
        account_type=body.account_type,
        currency=body.currency,
        include_in_total=include_in_total,
        billing_period_start=body.billing_period_start,
        billing_period_end=body.billing_period_end,
        payment_due_date=body.payment_due_date,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)

    today = date.today()
    balances_by_account, closed_period_balances = await _calculate_balances_by_account(
        session,
        current_user.id,
        [account],
        today,
    )
    return _build_account_response(
        account,
        balances_by_account.get(account.name, 0.0),
        closed_period_balances.get(account.name),
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
    today = date.today()
    account = await session.get(Account, account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    previous_name = account.name

    account.name = body.name
    account.account_type = body.account_type
    account.currency = body.currency
    fields_set = body.model_fields_set
    if "include_in_total" in fields_set:
        account.include_in_total = _resolve_include_in_total(body.account_type, body.include_in_total)
    if "billing_period_start" in fields_set:
        account.billing_period_start = body.billing_period_start
    if "billing_period_end" in fields_set:
        account.billing_period_end = body.billing_period_end
    if "payment_due_date" in fields_set:
        account.payment_due_date = body.payment_due_date

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

    balances_by_account, closed_period_balances = await _calculate_balances_by_account(
        session,
        current_user.id,
        [account],
        today,
    )
    return _build_account_response(
        account,
        balances_by_account.get(account.name, 0.0),
        closed_period_balances.get(account.name),
    )


@router.post("/{account_id}/adjust", response_model=AccountAdjustResponse)
async def adjust_account_balance(
    account_id: uuid.UUID,
    body: AccountAdjustRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AccountAdjustResponse:
    account = await session.get(Account, account_id)
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    today = date.today()
    balances_by_account, _ = await _calculate_balances_by_account(
        session,
        current_user.id,
        [account],
        today,
    )
    calculated_balance = Decimal(str(balances_by_account.get(account.name, 0.0))).quantize(MONEY_SCALE)
    real_balance = Decimal(str(body.balance)).quantize(MONEY_SCALE)
    delta = (real_balance - calculated_balance).quantize(MONEY_SCALE)

    if delta == Decimal("0.00"):
        return AccountAdjustResponse(applied=False, delta=0.0)

    transaction_type = TransactionType.income if delta > 0 else TransactionType.expense
    adjustment_amount = abs(delta)

    transaction = Transaction(
        id=uuid.uuid4(),
        user_id=current_user.id,
        amount=adjustment_amount,
        currency=account.currency,
        type=transaction_type,
        account=account.name,
        category_id=None,
        subcategory_id=None,
        description="Ajuste de saldo",
        note=None,
        installments=None,
        account_destination=None,
        expense_date=today,
    )
    session.add(transaction)
    await session.commit()

    return AccountAdjustResponse(applied=True, delta=float(delta))
