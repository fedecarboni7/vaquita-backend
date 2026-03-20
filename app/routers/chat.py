from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.graph import run_agent
from app.auth import get_current_user
from app.database import get_session
from app.models.account import Account
from app.models.category import Category
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    """Run the user message through the AI agent."""
    current_message = body.messages[-1].content
    history = [msg.model_dump() for msg in body.messages[:-1]] if len(body.messages) > 1 else None

    cat_expense_result = await session.execute(
        select(Category)
        .options(selectinload(Category.subcategories))
        .where(Category.user_id == current_user.id, Category.type == "expense")
    )
    expense_category_rows = cat_expense_result.scalars().all()
    expense_categories = [category.name for category in expense_category_rows]
    expense_category_tree: list[dict] = []
    expense_subcategory_index: dict[str, dict[str, str]] = {}
    for category in expense_category_rows:
        subcategories = [subcategory.name for subcategory in category.subcategories]
        expense_category_tree.append({"category": category.name, "subcategories": subcategories})
        expense_subcategory_index[category.name] = {
            subcategory.name: str(subcategory.id) for subcategory in category.subcategories
        }

    cat_income_result = await session.execute(
        select(Category)
        .options(selectinload(Category.subcategories))
        .where(Category.user_id == current_user.id, Category.type == "income")
    )
    income_category_rows = cat_income_result.scalars().all()
    income_categories = [category.name for category in income_category_rows]
    income_category_tree: list[dict] = []
    income_subcategory_index: dict[str, dict[str, str]] = {}
    for category in income_category_rows:
        subcategories = [subcategory.name for subcategory in category.subcategories]
        income_category_tree.append({"category": category.name, "subcategories": subcategories})
        income_subcategory_index[category.name] = {
            subcategory.name: str(subcategory.id) for subcategory in category.subcategories
        }

    acc_result = await session.execute(select(Account.name).where(Account.user_id == current_user.id))
    accounts = [row[0] for row in acc_result.all()]

    result = await run_agent(
        message=current_message,
        history=history,
        expense_categories=expense_categories,
        income_categories=income_categories,
        expense_category_tree=expense_category_tree,
        income_category_tree=income_category_tree,
        expense_subcategory_index=expense_subcategory_index,
        income_subcategory_index=income_subcategory_index,
        accounts=accounts,
    )

    return ChatResponse(
        response_type=result["response_type"],
        message=result["message"],
        data=result["data"],
    )
