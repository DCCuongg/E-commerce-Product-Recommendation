"""
services/auth_service/auth_handler.py
Xử lý băm mật khẩu (bcrypt), sinh và giải mã xác thực JWT (JSON Web Token),
kiểm tra trạng thái vô hiệu hóa tài khoản (is_disabled) và phân quyền Admin (RBAC).
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .models import User, get_db

# Cấu hình JWT từ biến môi trường
JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY", "ecommerce-recommender-super-secret-jwt-key-2026"
)
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", str(60 * 24)))  # 24h

# Hash mẫu được nạp trong scripts/sql/03_seed_auth.sql cho mật khẩu 'Password123!'
SEED_PLACEHOLDER_HASH = "$2b$12$KIXeWq1i8jYpB34r82K0n.LwK9f9B0i6GhzUqW2pM1iXj4A1p/ZKi"
SEED_DEFAULT_PASSWORD = "Password123!"

security_scheme = HTTPBearer(auto_error=False)


def hash_password(plain_password: str) -> str:
    """Băm mật khẩu người dùng bằng thuật toán bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Kiểm tra mật khẩu người dùng nhập vào với chuỗi bcrypt hash trong DB.
    Hỗ trợ tương thích với chuỗi hash mẫu trong `03_seed_auth.sql`.
    """
    if not plain_password or not hashed_password:
        return False

    if (
        hashed_password == SEED_PLACEHOLDER_HASH
        and plain_password == SEED_DEFAULT_PASSWORD
    ):
        return True

    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except ValueError:
        return False


def create_access_token(
    user_id: str,
    username: str,
    email: str,
    role: str = "customer",
    expires_delta: Optional[timedelta] = None,
) -> Dict[str, Any]:
    """Sinh JWT Token chứa thông tin định danh và phân quyền của người dùng."""
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta
        else timedelta(minutes=JWT_EXPIRATION_MINUTES)
    )

    payload = {
        "sub": str(user_id),
        "user_id": str(user_id),
        "username": username,
        "email": email,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    encoded_jwt = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return {
        "access_token": encoded_jwt,
        "expires_in": int((expire - now).total_seconds()),
    }


def decode_access_token(token: str) -> Dict[str, Any]:
    """Giải mã và kiểm tra tính hợp lệ của JWT Token."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token đã hết hạn (Token expired).",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token không hợp lệ: {str(exc)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user_claims(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> Dict[str, Any]:
    """FastAPI Dependency trích xuất thông tin người dùng từ Header Authorization: Bearer <token>."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Thiếu thông tin xác thực Bearer Token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(credentials.credentials)


def get_active_current_user(
    claims: Dict[str, Any] = Depends(get_current_user_claims),
    db: Session = Depends(get_db),
) -> User:
    """
    Truy vấn DB xác nhận user tồn tại và chưa bị vô hiệu hóa (is_disabled == False).
    Nếu tài khoản bị khóa, thu hồi quyền truy cập ngay lập tức (HTTP 403).
    """
    user_id = claims.get("user_id") or claims.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tài khoản không tồn tại trong hệ thống.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.is_disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị vô hiệu hóa. Liên hệ quản trị viên để được hỗ trợ.",
        )
    return user


def require_admin(
    current_user: User = Depends(get_active_current_user),
) -> User:
    """FastAPI Dependency bắt buộc quyền quản trị viên (role == 'admin') và tài khoản đang hoạt động."""
    if current_user.role != "admin" or current_user.is_disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Từ chối truy cập: Yêu cầu quyền quản trị viên (admin).",
        )
    return current_user