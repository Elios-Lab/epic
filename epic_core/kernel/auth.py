"""Password hashing and JWT helpers."""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from epic_core.kernel.config import Settings
from epic_core.kernel.exceptions import InvalidCredentialsError

_password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _password_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _password_context.verify(plain, hashed)


def create_access_token(data: dict, settings: Settings) -> str:
    payload = data.copy()
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload["exp"] = expires_at
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str, settings: Settings) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise InvalidCredentialsError("Invalid or expired access token") from exc

