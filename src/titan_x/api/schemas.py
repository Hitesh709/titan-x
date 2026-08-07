from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, EmailStr, Field

T = TypeVar("T")


class LivenessResponse(BaseModel):
    status: Literal["alive"]


class ReadinessResponse(BaseModel):
    status: Literal["ready", "unavailable"]
    database: Literal["available", "unavailable"]
    redis: Literal["available", "unavailable"]


class VersionResponse(BaseModel):
    version: str
    build_date: str
    environment: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RegisterResponse(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    is_verified: bool


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LogoutRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str
    reset_url: str | None = None


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    token: str


class SendVerificationRequest(BaseModel):
    email: EmailStr


class SendVerificationResponse(BaseModel):
    message: str
    verification_url: str | None = None


class MessageResponse(BaseModel):
    message: str


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    skip: int
    limit: int


class UserResponse(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    is_verified: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime


class BrokerConnectionResponse(BaseModel):
    """Broker connection summary that never exposes credentials or tokens."""

    id: int
    broker_name: str
    label: str
    is_active: bool
    has_api_key: bool = False
    has_api_secret: bool = False
    token_expires_at: datetime | None = None
    created_at: datetime | None = None


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="normal", pattern=r"^(normal|premium|analyst|admin)$")
    is_active: bool = True
    is_superuser: bool = False
    is_verified: bool = False


class UserUpdateRequest(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: str | None = Field(default=None, pattern=r"^(normal|premium|analyst|admin)$")
    is_active: bool | None = None
    is_superuser: bool | None = None
    is_verified: bool | None = None
