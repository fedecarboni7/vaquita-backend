import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.database import get_session
from app.models.category import Category
from app.models.user import User
from app.schemas.categories import CategoryCreate, CategoryResponse, CategoryUpdate, CategoryWithSubcategoriesResponse

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryWithSubcategoriesResponse])
async def list_categories(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CategoryWithSubcategoriesResponse]:
    result = await session.execute(
        select(Category)
        .options(selectinload(Category.subcategories))
        .where(Category.user_id == current_user.id)
        .order_by(Category.name)
    )
    return result.scalars().all()


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    body: CategoryCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CategoryResponse:
    normalized_name = body.name.strip().lower()
    existing = await session.execute(
        select(Category.id).where(
            Category.user_id == current_user.id,
            Category.type == body.type,
            func.lower(func.btrim(Category.name)) == normalized_name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una categoria con ese nombre",
        )

    category = Category(
        id=uuid.uuid4(),
        user_id=current_user.id,
        name=body.name,
        type=body.type,
    )
    session.add(category)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una categoria con ese nombre",
        ) from None
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoria no encontrada")

    await session.delete(category)
    await session.commit()


@router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: uuid.UUID,
    body: CategoryUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CategoryResponse:
    category = await session.get(Category, category_id)
    if not category or category.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoria no encontrada")

    if body.name is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El nombre es requerido",
        )

    trimmed_name = body.name.strip()
    current_trimmed = category.name.strip()
    if trimmed_name == current_trimmed:
        return category

    normalized_name = trimmed_name.lower()

    existing = await session.execute(
        select(Category.id).where(
            Category.user_id == current_user.id,
            Category.id != category.id,
            Category.type == category.type,
            func.lower(func.btrim(Category.name)) == normalized_name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una categoria con ese nombre",
        )

    category.name = body.name
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una categoria con ese nombre",
        ) from None
    await session.refresh(category)
    return category
