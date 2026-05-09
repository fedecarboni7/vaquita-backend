from pydantic import BaseModel, ConfigDict

from app.models.user_api_key import ApiKeyProvider


class ApiKeyUpsertRequest(BaseModel):
    provider: ApiKeyProvider
    api_key: str


class ApiKeyStatusResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    provider: ApiKeyProvider | None = None
    has_key: bool
