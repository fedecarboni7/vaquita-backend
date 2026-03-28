import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models.category import Category
from app.models.subcategory import Subcategory
from app.models.user import User
from app.schemas.categories import SubcategoryCreate, SubcategoryResponse

router = APIRouter(prefix="/categories", tags=["categories"])


@router.post("/{category_id}/subcategories", response_model=SubcategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_subcategory(
    category_id: uuid.UUID,
    body: SubcategoryCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SubcategoryResponse:
    category = await session.get(Category, category_id)
    if not category or category.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    existing = await session.execute(
        select(Subcategory).where(
            Subcategory.user_id == current_user.id,
            Subcategory.category_id == category_id,
            Subcategory.name == body.name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Subcategory already exists")

    subcategory = Subcategory(
        id=uuid.uuid4(),
        name=body.name,
        category_id=category_id,
        user_id=current_user.id,
    )
    session.add(subcategory)
    await session.commit()
    await session.refresh(subcategory)
    return subcategory


@router.delete("/{category_id}/subcategories/{subcategory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subcategory(
    category_id: uuid.UUID,
    subcategory_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    subcategory = await session.get(Subcategory, subcategory_id)
    if not subcategory or subcategory.user_id != current_user.id or subcategory.category_id != category_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subcategory not found")

    await session.delete(subcategory)
    await session.commit()
