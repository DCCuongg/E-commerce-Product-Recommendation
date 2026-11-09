"""
services/auth_service/models.py
Định nghĩa ORM Models (SQLAlchemy) cho bảng `users` trong PostgreSQL
và các Pydantic Schemas cho Request / Response của Auth Service.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Column, DateTime, String, create_engine, func
from sqlalchemy.orm import declarative_base, sessionmaker

# Nạp biến môi trường từ thư mục gốc dự án
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=ROOT_DIR / ".env")

# ------------------------------------------------------------------------------
# 1. CẤU HÌNH KẾT NỐI DATABASE (POSTGRESQL)
# ------------------------------------------------------------------------------
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "ecommerce_shop_db")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres_admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "YourSecurePasswordHere123!")
POSTGRES_SSL_MODE = os.getenv("POSTGRES_SSL_MODE", "disable")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}?sslmode={POSTGRES_SSL_MODE}",
)

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency cung cấp database session cho mỗi request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ------------------------------------------------------------------------------
# 2. SQLALCHEMY ORM MODEL (Bảng `users` khớp với 01_init_auth_db.sql)
# ------------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(String(50), primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="customer")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ------------------------------------------------------------------------------
# 3. PYDANTIC SCHEMAS (REQUEST / RESPONSE)
# ------------------------------------------------------------------------------
class UserRegisterRequest(BaseModel):
    user_id: Optional[str] = Field(
        default=None,
        description="Tùy chọn mã user_id (VD: mã Amazon user_id để test gợi ý). Nếu bỏ trống sẽ tự sinh.",
    )
    username: str = Field(..., min_length=3, max_length=50, examples=["cuongduong"])
    email: EmailStr = Field(..., examples=["cuong@ecommerce.local"])
    password: str = Field(..., min_length=6, max_length=128, examples=["Password123!"])
    role: Optional[str] = Field(default="customer", pattern="^(customer|admin)$")


class UserLoginRequest(BaseModel):
    username: str = Field(
        ..., description="Username hoặc Email đăng nhập", examples=["cuongduong"]
    )
    password: str = Field(..., description="Mật khẩu", examples=["Password123!"])


class TokenVerifyRequest(BaseModel):
    token: str = Field(..., description="JWT Bearer token cần xác thực")


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class VerifyTokenResponse(BaseModel):
    valid: bool
    user_id: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    message: Optional[str] = None
