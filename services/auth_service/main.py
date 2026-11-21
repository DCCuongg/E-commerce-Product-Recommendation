"""
services/auth_service/main.py
Microservice 1: Quản lý người dùng & Phân quyền RBAC (Port 8001).
Cung cấp các API:
- POST /api/v1/auth/register (và /register)
- POST /api/v1/auth/login (chặn user.is_disabled == True với HTTP 403)
- GET & POST /api/v1/auth/verify-token (kiểm tra is_disabled trong DB theo thời gian thực)
- GET /api/v1/auth/me
- GET /api/v1/auth/users
- Admin RBAC:
  - GET    /api/v1/admin/users
  - PATCH  /api/v1/admin/users/{user_id}/disable
  - PATCH  /api/v1/admin/users/{user_id}/role
  - DELETE /api/v1/admin/users/{user_id} (cấm xóa nếu đã có orders/reviews -> 409 Conflict)
"""

import logging
import math
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import inspect, or_, text
from sqlalchemy.orm import Session

from .auth_handler import (
    create_access_token,
    decode_access_token,
    get_active_current_user,
    hash_password,
    require_admin,
    verify_password,
)
from .models import (
    AdminUserListResponse,
    AdminUserResponse,
    AuthTokenResponse,
    Base,
    TokenVerifyRequest,
    UpdateUserRoleRequest,
    UpdateUserStatusRequest,
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
    description="Microservice quản lý tài khoản, xác thực JWT, Soft-Disable và phân quyền RBAC (Port 8001).",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=500)


# ------------------------------------------------------------------------------
# HELPER KIỂM TRA LỊCH SỬ GIAO DỊCH CỦA USER (ORDERS & REVIEWS)
# ------------------------------------------------------------------------------
def _get_user_transaction_counts(db: Session, user_id: str) -> Dict[str, int]:
    """Đếm số lượng đơn hàng và đánh giá của user để phục vụ chính sách không xóa cứng."""
    inspector = inspect(db.get_bind())
    existing_tables = set(inspector.get_table_names())

    order_count = 0
    review_count = 0

    if "orders" in existing_tables:
        res = db.execute(
            text("SELECT COUNT(*) FROM orders WHERE user_id = :uid"),
            {"uid": user_id},
        ).scalar()
        order_count = int(res or 0)

    if "reviews" in existing_tables:
        res = db.execute(
            text("SELECT COUNT(*) FROM reviews WHERE user_id = :uid"),
            {"uid": user_id},
        ).scalar()
        review_count = int(res or 0)

    return {"order_count": order_count, "review_count": review_count}


def _to_admin_user_response(db: Session, user: User) -> AdminUserResponse:
    counts = _get_user_transaction_counts(db, user.id)
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_disabled=bool(user.is_disabled),
        disabled_at=user.disabled_at,
        disabled_reason=user.disabled_reason,
        created_at=user.created_at,
        updated_at=user.updated_at,
        order_count=counts["order_count"],
        review_count=counts["review_count"],
    )


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
        is_disabled=False,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token_data = create_access_token(
        user_id=new_user.id,
        username=new_user.username,
        email=new_user.email,
        role=new_user.role,
    )
    logger.info(f"Đã đăng ký người dùng mới: {new_user.username} (ID={new_user.id})")

    return AuthTokenResponse(
        access_token=token_data["access_token"],
        token_type="bearer",
        expires_in=token_data["expires_in"],
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

    if user.is_disabled:
        reason_msg = f" Lý do: {user.disabled_reason}" if user.disabled_reason else ""
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tài khoản của bạn đã bị vô hiệu hóa.{reason_msg}",
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
    db: Session,
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
    user_id = claims.get("user_id") or claims.get("sub")

    # Kiểm tra trạng thái sống của tài khoản trực tiếp trên DB để thu hồi JWT ngay khi bị disable
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tài khoản không tồn tại.",
        )
    if user.is_disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị vô hiệu hóa.",
        )

    return VerifyTokenResponse(
        valid=True,
        user_id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
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
    db: Session = Depends(get_db),
):
    """Endpoint dùng cho Order Service / Recommender Service gọi sang xác thực JWT & trạng thái user."""
    return _extract_and_verify_token(db=db, authorization=authorization, token_query=token)


@app.post(
    "/api/v1/auth/verify-token",
    response_model=VerifyTokenResponse,
    tags=["Internal Microservice Auth"],
)
def verify_token_post(
    authorization: Optional[str] = Header(default=None),
    body: Optional[TokenVerifyRequest] = Body(default=None),
    db: Session = Depends(get_db),
):
    """Xác thực JWT Token qua HTTP POST."""
    return _extract_and_verify_token(db=db, authorization=authorization, body=body)


@app.get(
    "/verify-token",
    response_model=VerifyTokenResponse,
    tags=["Internal Microservice Auth"],
    include_in_schema=False,
)
def verify_token_root_get(
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    return _extract_and_verify_token(db=db, authorization=authorization, token_query=token)


@app.post(
    "/verify-token",
    response_model=VerifyTokenResponse,
    tags=["Internal Microservice Auth"],
    include_in_schema=False,
)
def verify_token_root_post(
    authorization: Optional[str] = Header(default=None),
    body: Optional[TokenVerifyRequest] = Body(default=None),
    db: Session = Depends(get_db),
):
    return _extract_and_verify_token(db=db, authorization=authorization, body=body)


# ------------------------------------------------------------------------------
# 4. THÔNG TIN NGƯỜI DÙNG HIỆN TẠI & DANH SÁCH USER DEMO
# ------------------------------------------------------------------------------
@app.get("/api/v1/auth/me", response_model=UserResponse, tags=["Users"])
def get_me(
    current_user: User = Depends(get_active_current_user),
):
    """Trả về thông tin chi tiết của người dùng đang đăng nhập."""
    return UserResponse.model_validate(current_user)


@app.get("/api/v1/auth/users", response_model=List[UserResponse], tags=["Users"])
def list_users(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Liệt kê danh sách người dùng đang hoạt động (hỗ trợ debug/chuyển đổi user khi demo)."""
    users = (
        db.query(User)
        .filter(User.is_disabled.is_(False))
        .order_by(User.created_at.desc())
        .limit(limit)
        .all()
    )
    return [UserResponse.model_validate(u) for u in users]


# ------------------------------------------------------------------------------
# 5. ADMIN RBAC: QUẢN LÝ NGƯỜI DÙNG (SOFT-DISABLE, PHÂN QUYỀN, CẤM XÓA GIAO DỊCH)
# ------------------------------------------------------------------------------
@app.get(
    "/api/v1/admin/users",
    response_model=AdminUserListResponse,
    tags=["Admin Users"],
)
def admin_list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None, description="Tìm theo id, username hoặc email"),
    role: Optional[str] = Query(default=None, pattern="^(customer|admin)$"),
    is_disabled: Optional[bool] = Query(default=None),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Danh sách toàn bộ người dùng kèm trạng thái khóa và số lượng đơn hàng/đánh giá."""
    query = db.query(User)

    if search and search.strip():
        kw = f"%{search.strip()}%"
        query = query.filter(
            or_(
                User.id.ilike(kw),
                User.username.ilike(kw),
                User.email.ilike(kw),
            )
        )
    if role:
        query = query.filter(User.role == role)
    if is_disabled is not None:
        query = query.filter(User.is_disabled.is_(is_disabled))

    total = query.count()
    total_pages = max(1, math.ceil(total / page_size))
    offset = (page - 1) * page_size

    users = (
        query.order_by(User.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    return AdminUserListResponse(
        items=[_to_admin_user_response(db, u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@app.patch(
    "/api/v1/admin/users/{user_id}/disable",
    response_model=AdminUserResponse,
    tags=["Admin Users"],
)
def admin_disable_user(
    user_id: str,
    payload: UpdateUserStatusRequest,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Vô hiệu hóa hoặc mở khóa tài khoản người dùng (Soft-Disable thay cho Hard-Delete)."""
    if user_id == admin_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không thể tự vô hiệu hóa tài khoản quản trị viên đang đăng nhập.",
        )

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy người dùng '{user_id}'.",
        )

    target_user.is_disabled = payload.is_disabled
    if payload.is_disabled:
        target_user.disabled_at = datetime.now(timezone.utc)
        target_user.disabled_reason = (
            payload.reason.strip()
            if payload.reason and payload.reason.strip()
            else "Vô hiệu hóa bởi quản trị viên"
        )
    else:
        target_user.disabled_at = None
        target_user.disabled_reason = None

    db.commit()
    db.refresh(target_user)
    logger.info(
        f"Admin '{admin_user.username}' cập nhật is_disabled={target_user.is_disabled} cho user '{user_id}'."
    )
    return _to_admin_user_response(db, target_user)


@app.patch(
    "/api/v1/admin/users/{user_id}/role",
    response_model=AdminUserResponse,
    tags=["Admin Users"],
)
def admin_update_user_role(
    user_id: str,
    payload: UpdateUserRoleRequest,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Thay đổi vai trò phân quyền (customer / admin) của người dùng."""
    if user_id == admin_user.id and payload.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không thể tự hạ quyền admin của chính mình.",
        )

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy người dùng '{user_id}'.",
        )

    target_user.role = payload.role
    db.commit()
    db.refresh(target_user)
    logger.info(
        f"Admin '{admin_user.username}' đổi role user '{user_id}' thành '{target_user.role}'."
    )
    return _to_admin_user_response(db, target_user)


@app.delete(
    "/api/v1/admin/users/{user_id}",
    tags=["Admin Users"],
)
def admin_delete_user(
    user_id: str,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Chỉ cho phép xóa vật lý nếu user chưa phát sinh đơn hàng (`orders`) hoặc đánh giá (`reviews`).
    Nếu đã có giao dịch, trả về HTTP 409 Conflict yêu cầu dùng `/disable`.
    """
    if user_id == admin_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không thể tự xóa tài khoản quản trị viên đang đăng nhập.",
        )

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy người dùng '{user_id}'.",
        )

    counts = _get_user_transaction_counts(db, user_id)
    if counts["order_count"] > 0 or counts["review_count"] > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Không thể xóa cứng người dùng '{user_id}' vì đã có "
                f"{counts['order_count']} đơn hàng và {counts['review_count']} đánh giá. "
                f"Vui lòng sử dụng PATCH /api/v1/admin/users/{user_id}/disable để vô hiệu hóa."
            ),
        )

    inspector = inspect(db.get_bind())
    if "cart_items" in inspector.get_table_names():
        db.execute(text("DELETE FROM cart_items WHERE user_id = :uid"), {"uid": user_id})

    db.delete(target_user)
    db.commit()
    logger.info(f"Admin '{admin_user.username}' đã xóa vĩnh viễn user chưa phát sinh giao dịch: '{user_id}'.")
    return {
        "status": "deleted",
        "user_id": user_id,
        "message": "Đã xóa tài khoản chưa phát sinh giao dịch.",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("services.auth_service.main:app", host="0.0.0.0", port=8001, reload=True)