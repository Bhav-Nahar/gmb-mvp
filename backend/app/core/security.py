from datetime import datetime, timedelta
from typing import Any, Optional, Union
from jose import jwt, JWTError
from cryptography.fernet import Fernet
from app.core.config import settings

# AES-256 encryption using Fernet symmetric key
try:
    fernet = Fernet(settings.ENCRYPTION_KEY.encode())
except Exception:
    # Generate a temporary key on invalid config; log a warning
    print("WARNING: ENCRYPTION_KEY in .env is invalid. Generated a temporary key. Set a proper Fernet key in production.")
    fernet = Fernet(Fernet.generate_key())

def create_access_token(subject: Union[str, Any], token_version: int = 1, expires_delta: Optional[timedelta] = None) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {"exp": expire, "sub": str(subject), "ver": token_version}
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None

def decode_access_token_payload(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None

def encrypt_token(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    return fernet.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: Optional[str]) -> Optional[str]:
    if not encrypted_token:
        return None
    try:
        return fernet.decrypt(encrypted_token.encode()).decode()
    except Exception:
        return None
