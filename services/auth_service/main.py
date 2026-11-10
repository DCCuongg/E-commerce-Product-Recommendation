"""
services/auth_service/main.py
Microservice 1: Quản lý người dùng & Phân quyền (Port 8001).
Cung cấp các API:
- POST /api/v1/auth/register (và /register)
- POST /api/v1/auth/login (và /login)
- GET & POST /api/v1/auth/verify-token (và /verify-token)
- GET /api/v1/auth/me
- GET /api/v1/auth/users (Danh sách user mẫu phục vụ demo/debug)
"""

import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from .auth_handler import (
    create_access_token,
    decode_access_token,
    get_current_user_claims,
    hash_password,
    verify_password,
)
from .models import (
    AuthTokenResponse,
    Base,
    TokenVerifyRequest,
    User,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
    VerifyTokenResponse,
    engine,
    get_db,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] [AuthService] %(message)s"
)
logger = logging.getLogger("auth_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Đảm bảo bảng `users` đã được khởi tạo khi service khởi động."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Đã kết nối PostgreSQL và xác nhận bảng 'users' sẵn sàng.")
    except Exception as exc:
        logger.warning(f"Không thể khởi tạo bảng tự động khi startup: {exc}")
    yield


app = FastAPI(
    title="E-Commerce Auth Service API",
    description="Microservice quản lý tài khoản, xác thực JWT và phân quyền người dùng (Port 8001).",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Nén payload JSON trả về bằng Gzip (Theo Rubric Tiêu chí 3.4 - Data Compression)
app.add_middleware(GZipMiddleware, minimum_size=500)


# ------------------------------------------------------------------------------
# HEALTH CHECK
# ------------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as exc:
        db_status = f"error: {str(exc)}"

    return {
        "service": "auth_service",
        "status": "healthy" if db_status == "connected" else "degraded",
        "port": 8001,
        "database": db_status,
    }


# ------------------------------------------------------------------------------
# 1. ĐĂNG KÝ TÀI KHOẢN (/api/v1/auth/register & /register)
# ------------------------------------------------------------------------------
def _register_user_logic(payload: UserRegisterRequest, db: Session) -> AuthTokenResponse:
    existing_user = (
        db.query(User)
        .filter(
            or_(
                User.username == payload.username,
                User.email == payload.email,
            )
        )
        .first()
    )
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username hoặc Email đã tồn tại trong hệ thống.",
        )

    user_id = (
        payload.user_id.strip()
        if payload.user_id and payload.user_id.strip()
        else f"U_{uuid.uuid4().hex[:10].upper()}"
    )

    if db.query(User).filter(User.id == user_id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Mã người dùng '{user_id}' đã tồn tại.",
        )

    new_user = User(
        id=user_id,
        username=payload.username.strip(),
        email=payload.email.strip().lower(),
        hashed_password=hash_password(payload.password),
        role=payload.role or "customer",
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token_Data = create_access_token(
        user_id=new_user.id,
        username=new_user.username,
        email=new_user.email,
        role=new_user.role,
    )
    logger.info(f"Đã đăng ký người dùng mới: {new_user.username} (ID={new_user.id})")

    return AuthTokenResponse(
        access_token=token_Data["access_token"],
        token_type="bearer",
        expires_in=token_Data["expires_in"],
        user=UserResponse.model_validate(new_user),
    )


@app.post(
    "/api/v1/auth/register",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Authentication"],
)
def register_v1(payload: UserRegisterRequest, db: Session = Depends(get_db)):
    """Đăng ký tài khoản khách hàng mới và trả về JWT Token."""
    return _register_user_logic(payload, db)


@app.post(
    "/register",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Authentication"],
    include_in_schema=False,
)
def register_root(payload: UserRegisterRequest, db: Session = Depends(get_db)):
    return _register_user_logic(payload, db)


# ------------------------------------------------------------------------------
# 2. ĐĂNG NHẬP (/api/v1/auth/login & /login)
# ------------------------------------------------------------------------------
def _login_user_logic(payload: UserLoginRequest, db: Session) -> AuthTokenResponse:
    identifier = payload.username.strip()
    user = (
        db.query(User)
        .filter(
            or_(
                User.username == identifier,
                User.email == identifier.lower(),
            )
        )
        .first()
    )

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tên đăng nhập hoặc mật khẩu không chính xác.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = create_access_token(
        user_id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
    )
    logger.info(f"Người dùng đăng nhập thành công: {user.username} (ID={user.id})")

    return AuthTokenResponse(
        access_token=token_data["access_token"],
        token_type="bearer",
        expires_in=token_data["expires_in"],
        user=UserResponse.model_validate(user),
    )


@app.post(
    "/api/v1/auth/login",
    response_model=AuthTokenResponse,
    tags=["Authentication"],
)
def login_v1(payload: UserLoginRequest, db: Session = Depends(get_db)):
    """Đăng nhập bằng username hoặc email và nhận JWT Bearer Token."""
    return _login_user_logic(payload, db)


@app.post(
    "/login",
    response_model=AuthTokenResponse,
    tags=["Authentication"],
    include_in_schema=False,
)
def login_root(payload: UserLoginRequest, db: Session = Depends(get_db)):
    return _login_user_logic(payload, db)


# ------------------------------------------------------------------------------
# 3. XÁC THỰC TOKEN NỘI BỘ GIỮA CÁC MICROSERVICES (/api/v1/auth/verify-token)
# ------------------------------------------------------------------------------
def _extract_and_verify_token(
    authorization: Optional[str] = None,
    token_query: Optional[str] = None,
    body: Optional[TokenVerifyRequest] = None,
) -> VerifyTokenResponse:
    raw_token: Optional[str] = None

    if authorization and authorization.lower().startswith("bearer "):
        raw_token = authorization.split(" ", 1)[1].strip()
    elif body and body.token:
        raw_token = body.token.strip()
    elif token_query:
        raw_token = token_query.strip()

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Không tìm thấy token trong Header Authorization, Body hoặc Query.",
        )

    claims = decode_access_token(raw_token)
    return VerifyTokenResponse(
        valid=True,
        user_id=claims.get("user_id") or claims.get("sub"),
        username=claims.get("username"),
        email=claims.get("email"),
        role=claims.get("role", "customer"),
        message="Token hợp lệ.",
    )


@app.get(
    "/api/v1/auth/verify-token",
    response_model=VerifyTokenResponse,
    tags=["Internal Microservice Auth"],
)
def verify_token_get(
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),
):
    """
    Endpoint dùng cho Order Service (hoặc API Gateway) gọi sang xác thực JWT Token.
    Hỗ trợ truyền qua Header `Authorization: Bearer <token>` hoặc query `?token=...`.
    """
    return _extract_and_verify_token(authorization=authorization, token_query=token)


@app.post(
    "/api/v1/auth/verify-token",
    response_model=VerifyTokenResponse,
    tags=["Internal Microservice Auth"],
)
def verify_token_post(
    authorization: Optional[str] = Header(default=None),
    body: Optional[TokenVerifyRequest] = Body(default=None),
):
    """Xác thực JWT Token qua HTTP POST."""
    return _extract_and_verify_token(authorization=authorization, body=body)


@app.get(
    "/verify-token",
    response_model=VerifyTokenResponse,
    tags=["Internal Microservice Auth"],
    include_in_schema=False,
)
def verify_token_root_get(
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),
):
    return _extract_and_verify_token(authorization=authorization, token_query=token)


@app.post(
    "/verify-token",
    response_model=VerifyTokenResponse,
    tags=["Internal Microservice Auth"],
    include_in_schema=False,
)
def verify_token_root_post(
    authorization: Optional[str] = Header(default=None),
    body: Optional[TokenVerifyRequest] = Body(default=None),
):
    return _extract_and_verify_token(authorization=authorization, body=body)


# ------------------------------------------------------------------------------
# 4. THÔNG TIN NGƯỜI DÙNG HIỆN TẠI & DANH SÁCH USER DEMO
# ------------------------------------------------------------------------------
@app.get("/api/v1/auth/me", response_model=UserResponse, tags=["Users"])
def get_me(
    claims: Dict[str, Any] = Depends(get_current_user_claims),
    db: Session = Depends(get_db),
):
    """Trả về thông tin chi tiết của người dùng đang đăng nhập."""
    user_id = claims.get("user_id") or claims.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy người dùng trong cơ sở dữ liệu.",
        )
    return UserResponse.model_validate(user)


@app.get("/api/v1/auth/users", response_model=List[UserResponse], tags=["Users"])
def list_users(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Liệt kê danh sách người dùng trong hệ thống (hỗ trợ debug/chuyển đổi user khi demo)."""
    users = db.query(User).order_by(User.created_at.desc()).limit(limit).all()
    return [UserResponse.model_validate(u) for u in users]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("services.auth_service.main:app", host="0.0.0.0", port=8001, reload=True)
