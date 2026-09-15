import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models.budget import Budget
from app.models.category import Category
from app.models.subcategory import Subcategory
from app.models.user import User
from app.schemas.budgets import BudgetCreate, BudgetRead, BudgetUpdate
from app.services.budget_aggregations import calculate_budget_spent

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _build_budget_response(budget: Budget, spent: Decimal) -> BudgetRead:
    remaining = budget.amount - spent
    percentage = float((spent * Decimal("100")) / budget.amount)
    return BudgetRead(
        id=budget.id,
        user_id=budget.user_id,
        category_id=budget.category_id,
        subcategory_id=budget.subcategory_id,
        amount=budget.amount,
        currency=budget.currency,
        created_at=budget.created_at,
        updated_at=budget.updated_at,
        spent=spent,
        remaining=remaining,
        percentage=percentage,
    )


async def _validate_scope(
    session: AsyncSession,
    user_id: uuid.UUID,
    category_id: uuid.UUID,
    subcategory_id: uuid.UUID | None,
) -> None:
    category = await session.execute(select(Category).where(Category.id == category_id, Category.user_id == user_id))
    category_row = category.scalar_one_or_none()
    if category_row is None or category_row.type != "expense":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La categoria no existe o no es de gastos",
        )

    if subcategory_id is None:
        return

    subcategory = await session.execute(
        select(Subcategory).where(
            Subcategory.id == subcategory_id,
            Subcategory.category_id == category_id,
            Subcategory.user_id == user_id,
        )
    )
    if subcategory.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La subcategoria no pertenece a la categoria del usuario",
        )


async def _get_owned_budget(
    session: AsyncSession,
    budget_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Budget:
    result = await session.execute(select(Budget).where(Budget.id == budget_id, Budget.user_id == user_id))
    budget = result.scalar_one_or_none()
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Presupuesto no encontrado")
    return budget


async def _commit_budget(session: AsyncSession, budget: Budget) -> None:
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un presupuesto para ese alcance y moneda",
        ) from None
    await session.refresh(budget)


@router.get("", response_model=list[BudgetRead])
async def list_budgets(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[BudgetRead]:
    result = await session.execute(select(Budget).where(Budget.user_id == current_user.id).order_by(Budget.created_at))
    budgets = list(result.scalars().all())
    spent_by_budget = await calculate_budget_spent(session, current_user.id, budgets)
    return [_build_budget_response(budget, spent_by_budget[budget.id]) for budget in budgets]


@router.post("", response_model=BudgetRead, status_code=status.HTTP_201_CREATED)
async def create_budget(
    body: BudgetCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BudgetRead:
    await _validate_scope(session, current_user.id, body.category_id, body.subcategory_id)
    budget = Budget(
        id=uuid.uuid4(),
        user_id=current_user.id,
        category_id=body.category_id,
        subcategory_id=body.subcategory_id,
        amount=body.amount,
        currency=body.currency,
    )
    session.add(budget)
    await _commit_budget(session, budget)
    spent_by_budget = await calculate_budget_spent(session, current_user.id, [budget])
    return _build_budget_response(budget, spent_by_budget[budget.id])


@router.patch("/{budget_id}", response_model=BudgetRead)
async def update_budget(
    budget_id: uuid.UUID,
    body: BudgetUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BudgetRead:
    budget = await _get_owned_budget(session, budget_id, current_user.id)
    fields_set = body.model_fields_set

    category_id = body.category_id if "category_id" in fields_set else budget.category_id
    subcategory_id = body.subcategory_id if "subcategory_id" in fields_set else budget.subcategory_id
    currency = body.currency if "currency" in fields_set else budget.currency

    if category_id is None or currency is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La categoria y la moneda son obligatorias",
        )
    await _validate_scope(session, current_user.id, category_id, subcategory_id)

    if "category_id" in fields_set:
        budget.category_id = category_id
    if "subcategory_id" in fields_set:
        budget.subcategory_id = subcategory_id
    if "amount" in fields_set:
        if body.amount is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El monto es obligatorio")
        budget.amount = body.amount
    if "currency" in fields_set:
        budget.currency = currency

    await _commit_budget(session, budget)
    spent_by_budget = await calculate_budget_spent(session, current_user.id, [budget])
    return _build_budget_response(budget, spent_by_budget[budget.id])


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(
    budget_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    budget = await _get_owned_budget(session, budget_id, current_user.id)
    await session.delete(budget)
    await session.commit()
