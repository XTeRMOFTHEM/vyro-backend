"""VYRO — Errors & unified error envelope.

Every error response looks like:
    {"error": {"code": "...", "message": "...", "details": {...}|null}}
"""
from __future__ import annotations


class AppError(Exception):
    status_code: int = 500
    code: str = "internal_error"
    message: str = "خطای داخلی سرور"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict | None = None,
    ):
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details
        super().__init__(self.message)


class BadRequest(AppError):
    status_code, code, message = 400, "bad_request", "درخواست نامعتبر است"


class ValidationFailed(BadRequest):
    code = "validation_failed"


class Unauthorized(AppError):
    status_code, code, message = 401, "unauthorized", "احراز هویت لازم است"


class InvalidCredentials(Unauthorized):
    code, message = "invalid_credentials", "ایمیل یا رمز عبور اشتباه است"


class TokenExpired(Unauthorized):
    code, message = "token_expired", "توکن منقضی شده است"


class Forbidden(AppError):
    status_code, code, message = 403, "forbidden", "اجازه دسترسی ندارید"


class NotFound(AppError):
    status_code, code, message = 404, "not_found", "موردی یافت نشد"


class UserNotFound(NotFound):
    code, message = "user_not_found", "کاربر یافت نشد"


class PostNotFound(NotFound):
    code, message = "post_not_found", "پست یافت نشد"


class CommentNotFound(NotFound):
    code, message = "comment_not_found", "کامنت یافت نشد"


class ConversationNotFound(NotFound):
    code, message = "conversation_not_found", "گفتگو یافت نشد"


class MessageNotFound(NotFound):
    code, message = "message_not_found", "پیام یافت نشد"


class FrameNotFound(NotFound):
    code, message = "frame_not_found", "فریم یافت نشد"


class Conflict(AppError):
    status_code, code, message = 409, "conflict", "تداخل در انجام عملیات"


class EmailTaken(Conflict):
    code, message = "email_taken", "این ایمیل قبلاً ثبت شده است"


class UsernameTaken(Conflict):
    code, message = "username_taken", "این نام کاربری قبلاً گرفته شده است"


class AlreadyExists(Conflict):
    pass


class InsufficientBalance(BadRequest):
    code, message = "insufficient_balance", "موجودی ZYRA کافی نیست"


class RateLimited(AppError):
    status_code, code, message = 429, "rate_limited", "تعداد درخواست‌ها زیاد است، کمی بعد تلاش کنید"


class PayloadTooLarge(AppError):
    status_code, code, message = 413, "payload_too_large", "حجم فایل بیش از حد مجاز است"


class UnsupportedMediaType(AppError):
    status_code, code, message = 415, "unsupported_media_type", "فرمت فایل پشتیبانی نمی‌شود"
