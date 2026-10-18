"""VYRO — auth schemas."""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,20}$")
RESERVED_USERNAMES = {
    "admin", "administrator", "support", "help", "vyro", "official", "zyra",
    "mod", "moderator", "root", "system", "me", "null", "undefined", "api",
    "security", "team", "staff", "bot",
}


class RegisterIn(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=20, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=72)
    display_name: str | None = Field(default=None, min_length=2, max_length=50)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        v = v.strip().lower()
        if not USERNAME_RE.match(v):
            raise ValueError("نام کاربری فقط حروف انگلیسی، عدد و _ (۳ تا ۲۰ کاراکتر)")
        if v in RESERVED_USERNAMES:
            raise ValueError("این نام کاربری مجاز نیست")
        return v

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("رمز عبور باید حداقل شامل یک حرف و یک عدد باشد")
        return v

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, v: str | None) -> str | None:
        return v.strip() if v else None


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)
    device: str = Field(default="", max_length=200)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=200)


class LogoutIn(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=200)


class VerifyEmailIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        import re
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("رمز عبور باید حداقل شامل یک حرف و یک عدد باشد")
        return v


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        import re
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("رمز عبور باید حداقل شامل یک حرف و یک عدد باشد")
        return v


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserAuthed(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    username: str
    display_name: str
    role: str
    is_email_verified: bool


class RegisterOut(TokenPair):
    user: UserAuthed
    dev_verification_token: str | None = None


class LoginOut(TokenPair):
    user: UserAuthed


class RefreshOut(TokenPair):
    pass


class MessageOut(BaseModel):
    message: str
    dev_reset_token: str | None = None
