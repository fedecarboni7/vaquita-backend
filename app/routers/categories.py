import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models.category import Category
from app.models.user import User
from app.schemas.categories import CategoryCreate, CategoryResponse

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
async def list_categories(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CategoryResponse]:
    result = await session.execute(select(Category).where(Category.user_id == current_user.id).order_by(Category.name))
    return result.scalars().all()


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    body: CategoryCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CategoryResponse:
    category = Category(
        id=uuid.uuid4(),
        user_id=current_user.id,
        name=body.name,
    )
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    category = await session.get(Category, category_id)
    if not category or category.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    await session.delete(category)
    await session.commit()
