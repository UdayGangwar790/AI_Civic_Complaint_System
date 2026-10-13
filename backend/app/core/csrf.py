import hashlib
import hmac
import secrets

from app.core.config import settings


def create_csrf_token(auth_token: str) -> str:
    nonce = secrets.token_urlsafe(32)
    message = f"{nonce}.{auth_token}".encode("utf-8")
    signature = hmac.new(settings.JWT_SECRET.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return f"{nonce}.{signature}"


def verify_csrf_token(auth_token: str, csrf_token: str) -> bool:
    try:
        nonce, signature = csrf_token.rsplit(".", 1)
    except ValueError:
        return False
    message = f"{nonce}.{auth_token}".encode("utf-8")
    expected = hmac.new(settings.JWT_SECRET.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)
