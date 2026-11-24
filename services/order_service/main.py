"""
services/order_service/main.py
Microservice 2: Quản lý Sản phẩm, Giỏ hàng, Đặt hàng, Khóa tồn kho & Thanh toán Online (Port 8002).
- Giao tiếp nội bộ sang Auth Service (Port 8001) qua `/api/v1/auth/verify-token` để xác thực người dùng.
- Xử lý đặt hàng với Pessimistic Concurrency Control (`SELECT ... FOR UPDATE`).
- Hỗ trợ thanh toán COD và ONLINE (VietQR động + Webhook đối soát xác thực Secret Key & số tiền thật).
"""

import hmac
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .inventory_lock import (
    build_vietqr_info,
    calculate_expected_vnd,
    ensure_utc,
    execute_checkout_with_pessimistic_lock,
    extract_payment_code,
    release_expired_online_orders,
)
from .models import (
    AddToCartRequest,
    Base,
    BatchProductsRequest,
    CartItem,
    CartItemDetailResponse,
    CartSummaryResponse,
    CheckoutRequest,
    CreateReviewRequest,
    Order,
    OrderItemResponse,
    OrderPaymentStatusResponse,
    OrderResponse,
    PaginatedProductResponse,
    PaymentTransaction,
    PaymentWebhookRequest,
    Product,
    ProductResponse,
    Review,
    ReviewResponse,
    UpdateCartItemRequest,
    engine,
    get_db,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] [OrderService] %(message)s"
)
logger = logging.getLogger("order_service")

# Cấu hình giao tiếp với Auth Service & Bảo mật Webhook
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8001")
JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY", "ecommerce-recommender-super-secret-jwt-key-2026"
)
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
PAYMENT_WEBHOOK_SECRET = os.getenv(
    "PAYMENT_WEBHOOK_SECRET", "dev-payment-webhook-secret-2026"
)
ALLOW_DEV_X_USER_ID = os.getenv("ALLOW_DEV_X_USER_ID", "true").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Đảm bảo các bảng dữ liệu đã sẵn sàng khi khởi động."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Đã kết nối PostgreSQL và xác nhận các bảng Order/Cart/Payment sẵn sàng.")
    except Exception as exc:
        logger.warning(f"Không thể tự động khởi tạo bảng khi startup: {exc}")
    yield


app = FastAPI(
    title="E-Commerce Order, Cart, Payment & Product Service API",
    description=(
        "Microservice quản lý Danh mục Sản phẩm, Giỏ hàng, Đặt hàng, Thanh toán Online (VietQR) "
        "và Khóa bi quan tồn kho (Pessimistic Concurrency Control - Port 8002)."
    ),
    version="1.2.0",
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
# XÁC THỰC NGƯỜI DÙNG & XÁC THỰC CỔNG THANH TOÁN (WEBHOOK)
# ------------------------------------------------------------------------------
def verify_authenticated_user(
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
) -> Dict[str, Any]:
    """Xác thực người dùng qua Auth Service hoặc JWT cục bộ."""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        verify_url = f"{AUTH_SERVICE_URL.rstrip('/')}/api/v1/auth/verify-token"
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(
                    verify_url, headers={"Authorization": f"Bearer {token}"}
                )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("valid") and data.get("user_id"):
                    return data
            elif resp.status_code in (401, 403):
                try:
                    err_detail = resp.json().get(
                        "detail", "Token không hợp lệ từ Auth Service."
                    )
                except ValueError:
                    err_detail = "Token không hợp lệ từ Auth Service."
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=err_detail,
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.debug(
                f"Không kết nối được Auth Service tại {verify_url} ({exc}), fallback giải mã JWT cục bộ."
            )

        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            return {
                "valid": True,
                "user_id": payload.get("user_id") or payload.get("sub"),
                "username": payload.get("username"),
                "role": payload.get("role", "customer"),
            }
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token không hợp lệ hoặc đã hết hạn: {str(exc)}",
            )

    if ALLOW_DEV_X_USER_ID and x_user_id and x_user_id.strip():
        return {
            "valid": True,
            "user_id": x_user_id.strip(),
            "username": x_user_id.strip(),
            "role": "customer",
        }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Yêu cầu đăng nhập (Thiếu Header Authorization: Bearer <token>).",
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_payment_gateway_secret(
    authorization: Optional[str] = Header(default=None),
    x_webhook_secret: Optional[str] = Header(default=None, alias="X-Webhook-Secret"),
    secure_token: Optional[str] = Header(default=None, alias="secure-token"),
) -> None:
    """
    Chỉ cho phép ngân hàng / cổng thanh toán (SePay, Casso, PayOS...) gọi Webhook
    khi cung cấp đúng `PAYMENT_WEBHOOK_SECRET` trong `.env`.
    Hỗ trợ:
    - `Authorization: Apikey <secret>` (SePay)
    - `Authorization: Bearer <secret>`
    - `X-Webhook-Secret: <secret>`
    - `secure-token: <secret>` (Casso)
    """
    expected_secret = os.getenv("PAYMENT_WEBHOOK_SECRET", PAYMENT_WEBHOOK_SECRET).strip()
    if not expected_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server chưa cấu hình PAYMENT_WEBHOOK_SECRET.",
        )

    provided_token: Optional[str] = None
    if authorization:
        parts = authorization.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].lower() in ("apikey", "bearer"):
            provided_token = parts[1].strip()
    if not provided_token and x_webhook_secret:
        provided_token = x_webhook_secret.strip()
    if not provided_token and secure_token:
        provided_token = secure_token.strip()

    if not provided_token or not hmac.compare_digest(provided_token, expected_secret):
        logger.warning("[WEBHOOK-DENIED] Từ chối request webhook không hợp lệ chữ ký/API Key.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Chỉ cổng thanh toán/ngân hàng hợp lệ mới được phép gọi Webhook.",
        )


# ------------------------------------------------------------------------------
# HELPER CHUYỂN ĐỔI ORDER ORM -> ORDER RESPONSE
# ------------------------------------------------------------------------------
def _serialize_order(o: Order) -> OrderResponse:
    items_resp: List[OrderItemResponse] = []
    for oi in o.items:
        prod = oi.product
        u_price = float(oi.unit_price)
        items_resp.append(
            OrderItemResponse(
                id=oi.id,
                product_id=oi.product_id,
                product_name=prod.name if prod else oi.product_id,
                image_url=prod.image_url if prod else None,
                thumb_url=(prod.thumb_url or prod.image_url) if prod else None,
                quantity=oi.quantity,
                unit_price=round(u_price, 2),
                subtotal=round(u_price * oi.quantity, 2),
            )
        )

    now_utc = datetime.now(timezone.utc)
    expires_at = ensure_utc(o.payment_expires_at)
    is_still_payable = (
        o.payment_method == "ONLINE"
        and o.payment_status == "PENDING"
        and o.status == "PENDING_PAYMENT"
        and (expires_at is None or now_utc <= expires_at)
    )

    return OrderResponse(
        id=o.id,
        user_id=o.user_id,
        total_amount=round(float(o.total_amount), 2),
        status=o.status,
        payment_method=o.payment_method,
        payment_status=o.payment_status,
        payment_code=o.payment_code,
        payment_expires_at=o.payment_expires_at,
        paid_at=o.paid_at,
        payment_info=build_vietqr_info(o) if is_still_payable else None,
        created_at=o.created_at,
        items=items_resp,
    )


# ------------------------------------------------------------------------------
# HEALTH CHECK
# ------------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    try:
        product_count = (
            db.query(func.count(Product.id))
            .filter(Product.is_active.is_(True))
            .scalar()
            or 0
        )
        db_status = "connected"
    except Exception as exc:
        product_count = 0
        db_status = f"error: {str(exc)}"

    return {
        "service": "order_service",
        "status": "healthy" if db_status == "connected" else "degraded",
        "port": 8002,
        "database": db_status,
        "total_products": product_count,
        "usd_to_vnd_rate": int(os.getenv("USD_TO_VND_RATE", "1000")),
        "auth_service_url": AUTH_SERVICE_URL,
    }


# ------------------------------------------------------------------------------
# 1. API DANH MỤC SẢN PHẨM (PRODUCTS CATALOG)
# ------------------------------------------------------------------------------
@app.get(
    "/api/v1/products",
    response_model=PaginatedProductResponse,
    tags=["Products Catalog"],
)
def list_products(
    page: int = Query(default=1, ge=1, description="Số trang (bắt đầu từ 1)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Số sản phẩm mỗi trang"),
    category: Optional[str] = Query(default=None, description="Lọc theo danh mục"),
    search: Optional[str] = Query(default=None, description="Từ khóa tìm kiếm tên/mô tả"),
    sort_by: str = Query(
        default="default",
        pattern="^(default|price_asc|price_desc|name_asc)$",
        description="Sắp xếp: default | price_asc | price_desc | name_asc",
    ),
    db: Session = Depends(get_db),
):
    query = db.query(Product).filter(Product.is_active.is_(True))

    if category and category.strip() and category.lower() != "all":
        query = query.filter(Product.category.ilike(f"%{category.strip()}%"))

    if search and search.strip():
        kw = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Product.name.ilike(kw),
                Product.description.ilike(kw),
                Product.category.ilike(kw),
                Product.id.ilike(kw),
            )
        )

    total = query.count()

    if sort_by == "price_asc":
        query = query.order_by(Product.price.asc())
    elif sort_by == "price_desc":
        query = query.order_by(Product.price.desc())
    elif sort_by == "name_asc":
        query = query.order_by(Product.name.asc())
    else:
        query = query.order_by(Product.id.asc())

    offset = (page - 1) * page_size
    products = query.offset(offset).limit(page_size).all()

    return PaginatedProductResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[ProductResponse.from_orm_product(p) for p in products],
    )


@app.get("/api/v1/products/categories", tags=["Products Catalog"])
def list_categories(db: Session = Depends(get_db)):
    rows = (
        db.query(Product.category, func.count(Product.id).label("count"))
        .filter(Product.is_active.is_(True), Product.category.isnot(None))
        .group_by(Product.category)
        .order_by(func.count(Product.id).desc())
        .all()
    )
    return {
        "total_categories": len(rows),
        "categories": [
            {"category": r.category, "count": r.count} for r in rows if r.category
        ],
    }


@app.post(
    "/api/v1/products/batch",
    response_model=List[ProductResponse],
    tags=["Products Catalog"],
)
def get_products_batch(payload: BatchProductsRequest, db: Session = Depends(get_db)):
    if not payload.product_ids:
        return []
    products = (
        db.query(Product)
        .filter(Product.id.in_(payload.product_ids), Product.is_active.is_(True))
        .all()
    )
    prod_map = {p.id: ProductResponse.from_orm_product(p) for p in products}
    return [prod_map[pid] for pid in payload.product_ids if pid in prod_map]


@app.get(
    "/api/v1/products/{product_id}",
    response_model=ProductResponse,
    tags=["Products Catalog"],
)
def get_product_detail(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy sản phẩm với mã '{product_id}'.",
        )

    review_stats = (
        db.query(
            func.avg(Review.rating).label("avg_rating"),
            func.count(Review.id).label("cnt"),
        )
        .filter(Review.product_id == product_id)
        .first()
    )
    avg_rating = (
        round(float(review_stats.avg_rating), 2)
        if review_stats and review_stats.avg_rating is not None
        else 4.6
    )
    rating_count = int(review_stats.cnt) if review_stats and review_stats.cnt else 25

    return ProductResponse.from_orm_product(
        product, rating=avg_rating, rating_count=rating_count
    )


# ------------------------------------------------------------------------------
# 2. API GIỎ HÀNG (SHOPPING CART MANAGEMENT)
# ------------------------------------------------------------------------------
def _build_cart_summary(user_id: str, db: Session) -> CartSummaryResponse:
    cart_rows = (
        db.query(CartItem)
        .filter(CartItem.user_id == user_id)
        .order_by(CartItem.created_at.asc())
        .all()
    )
    items_detail: List[CartItemDetailResponse] = []
    total_qty = 0
    total_amt = 0.0

    for row in cart_rows:
        prod = row.product or db.query(Product).filter(Product.id == row.product_id).first()
        if not prod:
            continue
        u_price = float(prod.price)
        sub = round(u_price * row.quantity, 2)
        total_qty += row.quantity
        total_amt += sub
        items_detail.append(
            CartItemDetailResponse(
                id=row.id,
                user_id=row.user_id,
                product_id=row.product_id,
                product_name=prod.name,
                category=prod.category,
                unit_price=round(u_price, 2),
                image_url=prod.image_url,
                thumb_url=prod.thumb_url or prod.image_url,
                stock_quantity=prod.stock_quantity,
                quantity=row.quantity,
                subtotal=sub,
            )
        )

    return CartSummaryResponse(
        user_id=user_id,
        total_items=len(items_detail),
        total_quantity=total_qty,
        total_amount=round(total_amt, 2),
        items=items_detail,
    )


@app.get("/api/v1/cart", response_model=CartSummaryResponse, tags=["Shopping Cart"])
def get_cart(
    user_claims: Dict[str, Any] = Depends(verify_authenticated_user),
    db: Session = Depends(get_db),
):
    return _build_cart_summary(user_claims["user_id"], db)


@app.post("/api/v1/cart/items", response_model=CartSummaryResponse, tags=["Shopping Cart"])
def add_item_to_cart(
    payload: AddToCartRequest,
    user_claims: Dict[str, Any] = Depends(verify_authenticated_user),
    db: Session = Depends(get_db),
):
    user_id = user_claims["user_id"]
    product = (
        db.query(Product)
        .filter(Product.id == payload.product_id, Product.is_active.is_(True))
        .first()
    )
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sản phẩm '{payload.product_id}' không tồn tại hoặc đã ngừng kinh doanh.",
        )

    existing_item = (
        db.query(CartItem)
        .filter(
            CartItem.user_id == user_id,
            CartItem.product_id == payload.product_id,
        )
        .first()
    )

    new_quantity = (
        existing_item.quantity + payload.quantity
        if existing_item
        else payload.quantity
    )

    if product.stock_quantity < new_quantity:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Số lượng yêu cầu ({new_quantity}) vượt quá tồn kho hiện tại "
                f"của sản phẩm '{product.name}' (Còn {product.stock_quantity})."
            ),
        )

    if existing_item:
        existing_item.quantity = new_quantity
    else:
        db.add(
            CartItem(
                user_id=user_id,
                product_id=payload.product_id,
                quantity=payload.quantity,
            )
        )

    db.commit()
    return _build_cart_summary(user_id, db)


@app.put(
    "/api/v1/cart/items/{product_id}",
    response_model=CartSummaryResponse,
    tags=["Shopping Cart"],
)
def update_cart_item_quantity(
    product_id: str,
    payload: UpdateCartItemRequest,
    user_claims: Dict[str, Any] = Depends(verify_authenticated_user),
    db: Session = Depends(get_db),
):
    user_id = user_claims["user_id"]
    cart_item = (
        db.query(CartItem)
        .filter(CartItem.user_id == user_id, CartItem.product_id == product_id)
        .first()
    )
    if not cart_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sản phẩm '{product_id}' không có trong giỏ hàng.",
        )

    if payload.quantity <= 0:
        db.delete(cart_item)
        db.commit()
        return _build_cart_summary(user_id, db)

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product or not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sản phẩm '{product_id}' đã ngừng kinh doanh.",
        )
    if product.stock_quantity < payload.quantity:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Kho chỉ còn {product.stock_quantity} sản phẩm.",
        )

    cart_item.quantity = payload.quantity
    db.commit()
    return _build_cart_summary(user_id, db)


@app.delete(
    "/api/v1/cart/items/{product_id}",
    response_model=CartSummaryResponse,
    tags=["Shopping Cart"],
)
def remove_cart_item(
    product_id: str,
    user_claims: Dict[str, Any] = Depends(verify_authenticated_user),
    db: Session = Depends(get_db),
):
    user_id = user_claims["user_id"]
    db.query(CartItem).filter(
        CartItem.user_id == user_id, CartItem.product_id == product_id
    ).delete(synchronize_session=False)
    db.commit()
    return _build_cart_summary(user_id, db)


@app.delete("/api/v1/cart", response_model=CartSummaryResponse, tags=["Shopping Cart"])
def clear_user_cart(
    user_claims: Dict[str, Any] = Depends(verify_authenticated_user),
    db: Session = Depends(get_db),
):
    user_id = user_claims["user_id"]
    db.query(CartItem).filter(CartItem.user_id == user_id).delete(
        synchronize_session=False
    )
    db.commit()
    return _build_cart_summary(user_id, db)


# ------------------------------------------------------------------------------
# 3. API ĐẶT HÀNG & KHÓA ĐỒNG BỘ (ORDERS & PESSIMISTIC CONCURRENCY CHECKOUT)
# ------------------------------------------------------------------------------
@app.post(
    "/api/v1/orders/checkout",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Orders & Concurrency Checkout"],
)
def checkout_order(
    payload: Optional[CheckoutRequest] = None,
    user_claims: Dict[str, Any] = Depends(verify_authenticated_user),
    db: Session = Depends(get_db),
):
    user_id = user_claims["user_id"]
    req_items = payload.items if payload else None
    sim_fail = payload.simulate_failure if payload else False
    pay_method = payload.payment_method if payload else "COD"

    return execute_checkout_with_pessimistic_lock(
        db=db,
        user_id=user_id,
        requested_items=req_items,
        payment_method=pay_method,
        clear_cart=(req_items is None or len(req_items) == 0),
        simulate_failure=sim_fail,
    )


@app.post(
    "/api/v1/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Orders & Concurrency Checkout"],
)
def create_order_alias(
    payload: Optional[CheckoutRequest] = None,
    user_claims: Dict[str, Any] = Depends(verify_authenticated_user),
    db: Session = Depends(get_db),
):
    return checkout_order(payload=payload, user_claims=user_claims, db=db)


@app.get(
    "/api/v1/orders",
    response_model=List[OrderResponse],
    tags=["Orders & Concurrency Checkout"],
)
def list_user_orders(
    user_claims: Dict[str, Any] = Depends(verify_authenticated_user),
    db: Session = Depends(get_db),
):
    user_id = user_claims["user_id"]
    release_expired_online_orders(db, user_id=user_id)

    orders = (
        db.query(Order)
        .filter(Order.user_id == user_id)
        .order_by(Order.created_at.desc())
        .all()
    )
    return [_serialize_order(o) for o in orders]


@app.get(
    "/api/v1/orders/{order_id}",
    response_model=OrderResponse,
    tags=["Orders & Concurrency Checkout"],
)
def get_order_by_id(
    order_id: int,
    user_claims: Dict[str, Any] = Depends(verify_authenticated_user),
    db: Session = Depends(get_db),
):
    user_id = user_claims["user_id"]
    role = user_claims.get("role", "customer")
    release_expired_online_orders(db, user_id=user_id)

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy đơn hàng #{order_id}.",
        )
    if order.user_id != user_id and role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền xem đơn hàng này.",
        )

    return _serialize_order(order)


@app.get(
    "/api/v1/orders/{order_id}/payment-status",
    response_model=OrderPaymentStatusResponse,
    tags=["Online Payment"],
)
def get_order_payment_status(
    order_id: int,
    user_claims: Dict[str, Any] = Depends(verify_authenticated_user),
    db: Session = Depends(get_db),
):
    """
    Endpoint siêu nhẹ dành cho Frontend Polling mỗi 3-5 giây khi người dùng đang mở QR.
    Tự động giải phóng đơn nếu đã quá hạn `payment_expires_at`.
    """
    user_id = user_claims["user_id"]
    role = user_claims.get("role", "customer")
    release_expired_online_orders(db, user_id=user_id)

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy đơn hàng #{order_id}.",
        )
    if order.user_id != user_id and role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền xem trạng thái đơn hàng này.",
        )

    now_utc = datetime.now(timezone.utc)
    expires_at = ensure_utc(order.payment_expires_at)
    remaining = 0
    if expires_at and order.payment_status == "PENDING" and expires_at > now_utc:
        remaining = int((expires_at - now_utc).total_seconds())

    return OrderPaymentStatusResponse(
        order_id=order.id,
        status=order.status,
        payment_method=order.payment_method,
        payment_status=order.payment_status,
        payment_code=order.payment_code,
        paid_at=order.paid_at,
        payment_expires_at=order.payment_expires_at,
        remaining_seconds=remaining,
    )


@app.post(
    "/api/v1/orders/{order_id}/cancel",
    response_model=OrderResponse,
    tags=["Orders & Concurrency Checkout"],
)
def cancel_user_order(
    order_id: int,
    user_claims: Dict[str, Any] = Depends(verify_authenticated_user),
    db: Session = Depends(get_db),
):
    user_id = user_claims["user_id"]
    role = user_claims.get("role", "customer")

    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .with_for_update(of=Order)
        .first()
    )
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy đơn hàng #{order_id}.",
        )
    if order.user_id != user_id and role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền hủy đơn hàng này.",
        )

    if order.status == "CANCELLED":
        return _serialize_order(order)

    if order.status not in ("PENDING", "PENDING_PAYMENT", "CONFIRMED"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Không thể hủy đơn hàng đang ở trạng thái '{order.status}'.",
        )

    sorted_items = sorted(order.items, key=lambda item: item.product_id)
    for oi in sorted_items:
        prod = (
            db.query(Product)
            .filter(Product.id == oi.product_id)
            .with_for_update()
            .first()
        )
        if prod:
            prod.stock_quantity += oi.quantity

    order.status = "CANCELLED"
    if order.payment_status == "PAID":
        order.payment_status = "REFUNDED"
    elif order.payment_status == "PENDING":
        order.payment_status = "EXPIRED"

    db.commit()
    db.refresh(order)
    return _serialize_order(order)


# ------------------------------------------------------------------------------
# 4. API THANH TOÁN ONLINE & WEBHOOK ĐỐI SOÁT THẬT (BẢO VỆ BẰNG WEBHOOK SECRET)
# ------------------------------------------------------------------------------
@app.post(
    "/api/v1/payments/webhook",
    response_model=OrderResponse,
    tags=["Online Payment"],
    dependencies=[Depends(verify_payment_gateway_secret)],
)
def handle_payment_webhook(
    payload: PaymentWebhookRequest,
    db: Session = Depends(get_db),
):
    """
    Chỉ nhận callback từ cổng thanh toán/ngân hàng có gửi kèm `PAYMENT_WEBHOOK_SECRET`.
    - Hỗ trợ tự động trích xuất `payment_code` từ nội dung chuyển khoản (`content`).
    - Đối soát chặt số tiền thực nhận (`transferAmount` / `amount` >= số tiền VND của đơn).
    - Chống trùng lặp giao dịch qua `provider_tx_id` (Idempotent).
    """
    # 1. Bỏ qua các giao dịch tiền ra khỏi tài khoản (nếu dùng webhook biến động số dư)
    if payload.transferType and payload.transferType.lower() == "out":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bỏ qua giao dịch tiền ra (transferType='out').",
        )

    # 2. Trích xuất mã thanh toán PAY...
    resolved_code = extract_payment_code(payload.payment_code, payload.content)
    if not resolved_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không tìm thấy mã thanh toán hợp lệ (PAY...) trong payload hoặc nội dung chuyển khoản.",
        )

    # 3. Xác định mã giao dịch ngân hàng để đảm bảo Idempotency
    raw_tx_id = (
        payload.provider_tx_id
        or payload.referenceCode
        or (str(payload.id) if payload.id is not None else None)
    )
    if not raw_tx_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Thiếu mã giao dịch từ ngân hàng/cổng thanh toán (provider_tx_id / referenceCode / id).",
        )

    existing_tx = (
        db.query(PaymentTransaction)
        .filter(PaymentTransaction.provider_tx_id == raw_tx_id)
        .first()
    )
    if existing_tx:
        order = db.query(Order).filter(Order.id == existing_tx.order_id).first()
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy đơn hàng liên kết với giao dịch.",
            )
        return _serialize_order(order)

    # 4. Khóa dòng Order để cập nhật trạng thái an toàn
    order = (
        db.query(Order)
        .filter(Order.payment_code == resolved_code)
        .with_for_update(of=Order)
        .first()
    )
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy đơn hàng với mã thanh toán '{resolved_code}'.",
        )

    if order.payment_status == "PAID":
        return _serialize_order(order)

    if order.status == "CANCELLED" or order.payment_status == "EXPIRED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Đơn hàng đã hủy hoặc hết hạn thanh toán.",
        )

    now_utc = datetime.now(timezone.utc)
    expires_at = ensure_utc(order.payment_expires_at)
    if expires_at and now_utc > expires_at:
        order.payment_status = "EXPIRED"
        order.status = "CANCELLED"
        sorted_items = sorted(order.items, key=lambda item: item.product_id)
        for oi in sorted_items:
            prod = (
                db.query(Product)
                .filter(Product.id == oi.product_id)
                .with_for_update()
                .first()
            )
            if prod:
                prod.stock_quantity += oi.quantity
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Mã QR đã hết hạn thanh toán. Tồn kho đã được hoàn trả.",
        )

    # 5. Đối soát số tiền thực nhận từ ngân hàng (VND)
    received_vnd = (
        payload.transferAmount
        if payload.transferAmount is not None
        else payload.amount
    )
    if received_vnd is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Thiếu số tiền thực nhận (transferAmount hoặc amount) từ cổng thanh toán.",
        )

    expected_vnd = calculate_expected_vnd(order.total_amount)
    if payload.status == "SUCCESS" and float(received_vnd) < float(expected_vnd):
        logger.warning(
            f"[UNDERPAID] Order #{order.id} ({resolved_code}): "
            f"Nhận {received_vnd} VND < Yêu cầu {expected_vnd} VND"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Số tiền thanh toán ({int(received_vnd):,} VND) nhỏ hơn giá trị đơn hàng "
                f"({expected_vnd:,} VND)."
            ),
        )

    # 6. Lưu audit log & xác nhận đơn hàng
    tx = PaymentTransaction(
        order_id=order.id,
        payment_code=order.payment_code,
        provider=payload.provider,
        provider_tx_id=raw_tx_id,
        amount=round(float(received_vnd), 2),
        status=payload.status,
        raw_payload=payload.model_dump(),
    )
    db.add(tx)

    if payload.status == "SUCCESS":
        order.payment_status = "PAID"
        order.status = "CONFIRMED"
        order.paid_at = now_utc
        logger.info(
            f"[PAYMENT-SUCCESS] Order #{order.id} ({resolved_code}) đã thanh toán {int(received_vnd):,} VND (tx={raw_tx_id})."
        )
    else:
        order.payment_status = "FAILED"

    db.commit()
    db.refresh(order)
    return _serialize_order(order)


# ------------------------------------------------------------------------------
# 5. API ĐÁNH GIÁ SẢN PHẨM (PRODUCT REVIEWS)
# ------------------------------------------------------------------------------
@app.post(
    "/api/v1/products/{product_id}/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Product Reviews"],
)
def create_product_review(
    product_id: str,
    payload: CreateReviewRequest,
    user_claims: Dict[str, Any] = Depends(verify_authenticated_user),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sản phẩm '{product_id}' không tồn tại.",
        )

    review = Review(
        user_id=user_claims["user_id"],
        product_id=product_id,
        rating=payload.rating,
        title=payload.title,
        comment=payload.comment,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return ReviewResponse.model_validate(review)


@app.get(
    "/api/v1/products/{product_id}/reviews",
    response_model=List[ReviewResponse],
    tags=["Product Reviews"],
)
def list_product_reviews(
    product_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    reviews = (
        db.query(Review)
        .filter(Review.product_id == product_id)
        .order_by(Review.created_at.desc())
        .limit(limit)
        .all()
    )
    return [ReviewResponse.model_validate(r) for r in reviews]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("services.order_service.main:app", host="0.0.0.0", port=8002, reload=True)