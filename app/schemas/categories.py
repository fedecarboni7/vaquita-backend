import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class CategoryCreate(BaseModel):
    name: str
    type: Literal["expense", "income"] = "expense"


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: str
    created_at: datetime
