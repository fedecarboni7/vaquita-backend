import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CategoryCreate(BaseModel):
    name: str
    type: Literal["expense", "income"] = "expense"

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("El nombre no puede estar vacio")
        if len(trimmed) > 100:
            raise ValueError("El nombre no puede superar 100 caracteres")
        return trimmed


class SubcategoryCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("El nombre no puede estar vacio")
        if len(trimmed) > 100:
            raise ValueError("El nombre no puede superar 100 caracteres")
        return trimmed


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("El nombre no puede estar vacio")
        if len(trimmed) > 100:
            raise ValueError("El nombre no puede superar 100 caracteres")
        return trimmed


class SubcategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("El nombre no puede estar vacio")
        if len(trimmed) > 100:
            raise ValueError("El nombre no puede superar 100 caracteres")
        return trimmed


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
