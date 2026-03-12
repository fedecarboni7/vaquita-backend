from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
        select(Category.name).where(Category.user_id == current_user.id, Category.type == "expense")
    )
    expense_categories = [row[0] for row in cat_expense_result.all()]

    cat_income_result = await session.execute(
        select(Category.name).where(Category.user_id == current_user.id, Category.type == "income")
    )
    income_categories = [row[0] for row in cat_income_result.all()]

    acc_result = await session.execute(select(Account.name).where(Account.user_id == current_user.id))
    accounts = [row[0] for row in acc_result.all()]

    result = await run_agent(
        message=current_message,
        history=history,
        expense_categories=expense_categories,
        income_categories=income_categories,
        accounts=accounts,
    )

    return ChatResponse(
        response_type=result["response_type"],
        message=result["message"],
        data=result["data"],
    )
