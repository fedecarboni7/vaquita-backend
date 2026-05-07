import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_session
from app.models.category import Category
from app.models.subcategory import Subcategory
from app.models.user import User
from app.schemas.categories import SubcategoryCreate, SubcategoryResponse, SubcategoryUpdate

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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoria no encontrada")

    normalized_name = body.name.strip().lower()
    existing = await session.execute(
        select(Subcategory.id).where(
            Subcategory.user_id == current_user.id,
            Subcategory.category_id == category_id,
            func.lower(func.btrim(Subcategory.name)) == normalized_name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una subcategoria con ese nombre",
        )

    subcategory = Subcategory(
        id=uuid.uuid4(),
        name=body.name,
        category_id=category_id,
        user_id=current_user.id,
    )
    session.add(subcategory)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una subcategoria con ese nombre",
        ) from None
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subcategoria no encontrada")

    await session.delete(subcategory)
    await session.commit()


@router.patch("/{category_id}/subcategories/{subcategory_id}", response_model=SubcategoryResponse)
async def update_subcategory(
    category_id: uuid.UUID,
    subcategory_id: uuid.UUID,
    body: SubcategoryUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SubcategoryResponse:
    category = await session.get(Category, category_id)
    if not category or category.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoria no encontrada")

    subcategory = await session.get(Subcategory, subcategory_id)
    if not subcategory or subcategory.user_id != current_user.id or subcategory.category_id != category_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subcategoria no encontrada")

    if body.name is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El nombre es requerido",
        )

    trimmed = body.name.strip()
    if trimmed == subcategory.name.strip():
        return subcategory

    normalized_name = trimmed.lower()

    existing = await session.execute(
        select(Subcategory.id).where(
            Subcategory.user_id == current_user.id,
            Subcategory.category_id == category_id,
            Subcategory.id != subcategory.id,
            func.lower(func.btrim(Subcategory.name)) == normalized_name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una subcategoria con ese nombre",
        )

    subcategory.name = body.name
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una subcategoria con ese nombre",
        ) from None
    await session.refresh(subcategory)
    return subcategory
