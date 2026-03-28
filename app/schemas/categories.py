import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    name: str
    type: Literal["expense", "income"] = "expense"


class SubcategoryCreate(BaseModel):
    name: str


class SubcategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category_id: uuid.UUID


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: str
    created_at: datetime


class CategoryWithSubcategoriesResponse(CategoryResponse):
    subcategories: list[SubcategoryResponse] = Field(default_factory=list)
