import uuid

from pydantic import BaseModel, ConfigDict, Field


class GoogleAuthRequest(BaseModel):
    credential: str


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    name: str | None = None


class EmailRequest(BaseModel):
    email: str


class LoginRequest(BaseModel):
    email: str
    password: str


class VerifyEmailRequest(BaseModel):
    token: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class SetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class DevAuthRequest(BaseModel):
    email: str = "dev@local.test"
    display_name: str | None = "Dev User"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str | None
    google_id: str | None
    has_password: bool
    email_verified: bool
