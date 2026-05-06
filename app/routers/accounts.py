import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, case, func, or_, select
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
    AccountSummaryResponse,
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
) -> tuple[dict[uuid.UUID, float], dict[uuid.UUID, float | None]]:
    del today
    windows_by_account_id: dict[uuid.UUID, tuple[date, date] | None] = {
        account.id: _build_credit_card_windows(account) for account in accounts
    }

    result = await session.execute(
        select(
            Transaction.account_id,
            Transaction.account_destination_id,
            Transaction.type,
            Transaction.amount,
            Transaction.to_amount,
            Transaction.expense_date,
        ).where(Transaction.user_id == user_id)
    )

    balances: defaultdict[uuid.UUID, Decimal] = defaultdict(lambda: Decimal("0"))
    closed_period_balances: dict[uuid.UUID, Decimal | None] = {}

    for account in accounts:
        windows = windows_by_account_id.get(account.id)
        if windows is None:
            closed_period_balances[account.id] = None
        else:
            closed_period_balances[account.id] = Decimal("0")

    def apply_delta(account_id: uuid.UUID | None, delta: Decimal, expense_date: date) -> None:
        if account_id is None:
            return

        balances[account_id] += delta

        windows = windows_by_account_id.get(account_id)
        if windows is None:
            return

        closed_period_start, closed_period_end = windows
        if closed_period_start <= expense_date <= closed_period_end:
            closed_balance = closed_period_balances.get(account_id)
            if closed_balance is not None:
                closed_period_balances[account_id] = closed_balance + delta

    for account_id, account_destination_id, transaction_type, amount, to_amount, expense_date in result.all():
        amount_decimal = Decimal(str(amount))
        to_amount_decimal = Decimal(str(to_amount)) if to_amount is not None else None

        if transaction_type == TransactionType.income:
            apply_delta(account_id, amount_decimal, expense_date)
        elif transaction_type == TransactionType.expense:
            apply_delta(account_id, -amount_decimal, expense_date)
        elif transaction_type == TransactionType.transfer:
            apply_delta(account_id, -amount_decimal, expense_date)
            dest_account = next((a for a in accounts if a.id == account_destination_id), None)
            if dest_account and dest_account.account_type == "credit_card":
                balances[account_destination_id] += to_amount_decimal or amount_decimal
            else:
                apply_delta(account_destination_id, to_amount_decimal or amount_decimal, expense_date)

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
            balances_by_account.get(account.id, 0.0),
            closed_period_balances.get(account.id),
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
        balances_by_account.get(account.id, 0.0),
        closed_period_balances.get(account.id),
    )


@router.get("/{account_id}/summary", response_model=AccountSummaryResponse)
async def get_account_summary(
    account_id: uuid.UUID,
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AccountSummaryResponse:
    if from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="'from' date must be less than or equal to 'to' date",
        )

    account_result = await session.execute(
        select(Account).where(
            Account.id == account_id,
            Account.user_id == current_user.id,
        )
    )
    account = account_result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    in_range = and_(
        Transaction.expense_date >= from_date,
        Transaction.expense_date <= to_date,
    )
    participates_in_account = or_(
        Transaction.account_id == account_id,
        Transaction.account_destination_id == account_id,
    )

    income_amount = case(
        (
            and_(
                Transaction.type == TransactionType.income,
                Transaction.account_id == account_id,
            ),
            Transaction.amount,
        ),
        (
            and_(
                Transaction.type == TransactionType.transfer,
                Transaction.account_destination_id == account_id,
            ),
            func.coalesce(Transaction.to_amount, Transaction.amount),
        ),
        else_=0,
    )
    expense_amount = case(
        (
            and_(
                Transaction.type == TransactionType.expense,
                Transaction.account_id == account_id,
            ),
            Transaction.amount,
        ),
        (
            and_(
                Transaction.type == TransactionType.transfer,
                Transaction.account_id == account_id,
            ),
            Transaction.amount,
        ),
        else_=0,
    )

    summary_result = await session.execute(
        select(
            func.coalesce(func.sum(income_amount), 0).label("total_income"),
            func.coalesce(func.sum(expense_amount), 0).label("total_expenses"),
            (func.coalesce(func.sum(income_amount), 0) - func.coalesce(func.sum(expense_amount), 0)).label(
                "net_balance"
            ),
            func.coalesce(func.count(Transaction.id), 0).label("transaction_count"),
        ).where(
            Transaction.user_id == current_user.id,
            in_range,
            participates_in_account,
        )
    )
    summary = summary_result.one()

    return AccountSummaryResponse(
        account_id=account.id,
        account_name=account.name,
        currency=account.currency,
        from_date=from_date,
        to_date=to_date,
        total_income=float(summary.total_income),
        total_expenses=float(summary.total_expenses),
        net_balance=float(summary.net_balance),
        transaction_count=int(summary.transaction_count),
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
        balances_by_account.get(account.id, 0.0),
        closed_period_balances.get(account.id),
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
        balances_by_account.get(account.id, 0.0),
        closed_period_balances.get(account.id),
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
    calculated_balance = Decimal(str(balances_by_account.get(account.id, 0.0))).quantize(MONEY_SCALE)
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
        account_id=account.id,
        category_id=None,
        subcategory_id=None,
        description="Ajuste de saldo",
        note=None,
        installments=None,
        account_destination_id=None,
        affects_balance=body.affects_balance,
        expense_date=today,
    )
    session.add(transaction)
    await session.commit()

    return AccountAdjustResponse(applied=True, delta=float(delta))
