"""
services/order_service/main.py
Microservice 2: Quản lý Sản phẩm, Giỏ hàng, Đặt hàng & Khóa tồn kho (Port 8002).
- Giao tiếp nội bộ sang Auth Service (Port 8001) qua `/api/v1/auth/verify-token` để xác thực người dùng.
- Xử lý đặt hàng với Pessimistic Concurrency Control (`SELECT ... FOR UPDATE`).
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import httpx
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from .inventory_lock import execute_checkout_with_pessimistic_lock
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
    OrderResponse,
    PaginatedProductResponse,
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

# Cấu hình giao tiếp với Auth Service (Microservice 1)
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8001")
JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY", "ecommerce-recommender-super-secret-jwt-key-2026"
)
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Đảm bảo các bảng dữ liệu (products, cart_items, orders, order_items, reviews) đã sẵn sàng."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Đã kết nối PostgreSQL và xác nhận các bảng Order/Cart sẵn sàng.")
    except Exception as exc:
        logger.warning(f"Không thể tự động khởi tạo bảng khi startup: {exc}")
    yield


app = FastAPI(
    title="E-Commerce Order, Cart & Product Service API",
    description=(
        "Microservice quản lý Danh mục Sản phẩm, Giỏ hàng, Đặt hàng và Khóa bi quan tồn kho "
        "(Pessimistic Concurrency Control - Port 8002)."
    ),
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


# ------------------------------------------------------------------------------
# GIAO TIẾP NỘI BỘ GIỮA 2 MICROSERVICES (ORDER SERVICE -> AUTH SERVICE)
# ------------------------------------------------------------------------------
def verify_authenticated_user(
    authorization: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
) -> Dict[str, Any]:
    """
    Xác thực danh tính người dùng bằng cách gọi HTTP nội bộ sang `Auth Service`:
    `GET http://auth-service:8001/api/v1/auth/verify-token`
    Nếu có Bearer Token, ưu tiên gọi Auth Service; nếu Auth Service đang tắt (chạy độc lập),
    fallback giải mã bằng JWT Secret chung.
    """
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
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=resp.json().get("detail", "Token không hợp lệ từ Auth Service."),
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.debug(
                f"Không kết nối được Auth Service tại {verify_url} ({exc}), fallback giải mã JWT cục bộ."
            )

        # Fallback giải mã trực tiếp nếu chạy đơn lẻ không bật container Auth Service
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

    # Hỗ trợ Header X-User-Id cho kịch bản test nhanh / demo nếu cần
    if x_user_id and x_user_id.strip():
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


# ------------------------------------------------------------------------------
# HEALTH CHECK
# ------------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    try:
        product_count = db.query(func.count(Product.id)).scalar() or 0
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
    """Lấy danh sách sản phẩm nhạc cụ hỗ trợ phân trang, lọc theo danh mục và tìm kiếm."""
    query = db.query(Product)

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
    """Lấy danh sách các danh mục sản phẩm kèm số lượng mặt hàng."""
    rows = (
        db.query(Product.category, func.count(Product.id).label("count"))
        .filter(Product.category.isnot(None))
        .group_by(Product.category)
        .order_by(func.count(Product.id).desc())
        .all()
    )
    return {
        "total_categories": len(rows),
        "categories": [
            {"category": r.category, "count": r.count}
            for r in rows
            if r.category
        ],
    }


@app.post(
    "/api/v1/products/batch",
    response_model=List[ProductResponse],
    tags=["Products Catalog"],
)
def get_products_batch(payload: BatchProductsRequest, db: Session = Depends(get_db)):
    """Lấy thông tin chi tiết của nhiều sản phẩm cùng lúc theo mảng `product_ids` (giữ đúng thứ tự)."""
    if not payload.product_ids:
        return []
    products = (
        db.query(Product).filter(Product.id.in_(payload.product_ids)).all()
    )
    prod_map = {p.id: ProductResponse.from_orm_product(p) for p in products}
    return [prod_map[pid] for pid in payload.product_ids if pid in prod_map]


@app.get(
    "/api/v1/products/{product_id}",
    response_model=ProductResponse,
    tags=["Products Catalog"],
)
def get_product_detail(product_id: str, db: Session = Depends(get_db)):
    """Lấy thông tin chi tiết của 1 sản phẩm và số lượng tồn kho thực tế."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy sản phẩm với mã '{product_id}'.",
        )

    # Tính điểm trung bình đánh giá nếu có trong bảng reviews
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
    rating_count = (
        int(review_stats.cnt) if review_stats and review_stats.cnt else 25
    )

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
    """Lấy danh sách sản phẩm trong giỏ hàng của người dùng hiện tại."""
    user_id = user_claims["user_id"]
    return _build_cart_summary(user_id, db)


@app.post("/api/v1/cart/items", response_model=CartSummaryResponse, tags=["Shopping Cart"])
def add_item_to_cart(
    payload: AddToCartRequest,
    user_claims: Dict[str, Any] = Depends(verify_authenticated_user),
    db: Session = Depends(get_db),
):
    """Thêm sản phẩm vào giỏ hàng (Kiểm tra nhanh tồn kho trước khi thêm)."""
    user_id = user_claims["user_id"]

    product = db.query(Product).filter(Product.id == payload.product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sản phẩm '{payload.product_id}' không tồn tại.",
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
    """Cập nhật số lượng của một sản phẩm trong giỏ hàng (nếu quantity == 0 sẽ xóa khỏi giỏ)."""
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
    if product and product.stock_quantity < payload.quantity:
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
    """Xóa một mặt hàng khỏi giỏ hàng."""
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
    """Xóa toàn bộ giỏ hàng của người dùng."""
    user_id = user_claims["user_id"]
    db.query(CartItem).filter(CartItem.user_id == user_id).delete(
        synchronize_session=False
    )
    db.commit()
    return _build_cart_summary(user_id, db)


# ------------------------------------------------------------------------------
# 3. API ĐẶT HÀNG & THANH TOÁN VỚI KHÓA ĐỒNG BỘ (ORDERS & CONCURRENCY LOCK)
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
    """
    Thực hiện đặt hàng (Checkout) có áp dụng khóa bi quan `SELECT ... FOR UPDATE`:
    - Nếu truyền `items` trong body: đặt trực tiếp danh sách sản phẩm đó.
    - Nếu không truyền `items`: lấy toàn bộ sản phẩm trong giỏ hàng hiện tại của user.
    - Nếu có lỗi hoặc hết hàng: tự động `ROLLBACK` hoàn trả kho nguyên vẹn.
    """
    user_id = user_claims["user_id"]
    req_items = payload.items if payload else None
    sim_fail = payload.simulate_failure if payload else False

    return execute_checkout_with_pessimistic_lock(
        db=db,
        user_id=user_id,
        requested_items=req_items,
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
    """Endpoint tương đương `/api/v1/orders/checkout`."""
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
    """Lấy lịch sử đơn hàng của người dùng hiện tại."""
    user_id = user_claims["user_id"]
    orders = (
        db.query(Order)
        .filter(Order.user_id == user_id)
        .order_by(Order.created_at.desc())
        .all()
    )
    result: List[OrderResponse] = []
    for o in orders:
        items_resp = []
        for oi in o.items:
            prod = oi.product
            u_price = float(oi.unit_price)
            items_resp.append(
                OrderItemResponse(
                    id=oi.id,
                    product_id=oi.product_id,
                    product_name=prod.name if prod else oi.product_id,
                    image_url=prod.image_url if prod else None,
                    quantity=oi.quantity,
                    unit_price=round(u_price, 2),
                    subtotal=round(u_price * oi.quantity, 2),
                )
            )
        result.append(
            OrderResponse(
                id=o.id,
                user_id=o.user_id,
                total_amount=round(float(o.total_amount), 2),
                status=o.status,
                created_at=o.created_at,
                items=items_resp,
            )
        )
    return result


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
    """Xem chi tiết một đơn hàng cụ thể."""
    user_id = user_claims["user_id"]
    role = user_claims.get("role", "customer")
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

    items_resp = []
    for oi in order.items:
        prod = oi.product
        u_price = float(oi.unit_price)
        items_resp.append(
            OrderItemResponse(
                id=oi.id,
                product_id=oi.product_id,
                product_name=prod.name if prod else oi.product_id,
                image_url=prod.image_url if prod else None,
                quantity=oi.quantity,
                unit_price=round(u_price, 2),
                subtotal=round(u_price * oi.quantity, 2),
            )
        )

    return OrderResponse(
        id=order.id,
        user_id=order.user_id,
        total_amount=round(float(order.total_amount), 2),
        status=order.status,
        created_at=order.created_at,
        items=items_resp,
    )


# ------------------------------------------------------------------------------
# 4. API ĐÁNH GIÁ SẢN PHẨM (PRODUCT REVIEWS)
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
    """Gửi đánh giá sao và nhận xét cho sản phẩm (Lưu vào bảng `reviews` phục vụ Retraining)."""
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
    """Lấy danh sách đánh giá của một sản phẩm."""
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
