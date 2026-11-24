"""
services/order_service/models.py
Định nghĩa ORM Models (SQLAlchemy) cho các bảng `products`, `cart_items`, `orders`,
`order_items`, `payment_transactions`, `reviews` và Pydantic Schemas (Port 8002).
"""

import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Literal, Optional
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# Nạp biến môi trường từ thư mục gốc dự án
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=ROOT_DIR / ".env")

# ------------------------------------------------------------------------------
# 1. CẤU HÌNH KẾT NỐI POSTGRESQL
# ------------------------------------------------------------------------------
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "ecommerce_shop_db")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres_admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "YourSecurePasswordHere123!")
POSTGRES_SSL_MODE = os.getenv("POSTGRES_SSL_MODE", "disable")

RAW_DATABASE_URL = os.getenv("DATABASE_URL")
if RAW_DATABASE_URL:
    DATABASE_URL = RAW_DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    DATABASE_URL = (
        f"postgresql+psycopg2://{quote_plus(POSTGRES_USER)}:{quote_plus(POSTGRES_PASSWORD)}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}?sslmode={POSTGRES_SSL_MODE}"
    )

engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
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
# 2. SQLALCHEMY ORM MODELS (Khớp 100% với 02_init_order_db.sql)
# ------------------------------------------------------------------------------
class Product(Base):
    __tablename__ = "products"

    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100), index=True)
    price = Column(Numeric(10, 2), nullable=False, default=0.00)
    image_url = Column(Text, nullable=True)
    hi_res_url = Column(Text, nullable=True)
    large_urls = Column(JSONB, nullable=False, default=list)
    thumb_url = Column(Text, nullable=True)
    stock_quantity = Column(
        Integer,
        CheckConstraint("stock_quantity >= 0", name="check_stock_non_negative"),
        nullable=False,
        default=100,
    )
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="unique_user_product_cart"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False)
    product_id = Column(
        String(50), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    quantity = Column(
        Integer,
        CheckConstraint("quantity > 0", name="check_cart_qty_positive"),
        nullable=False,
        default=1,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product = relationship("Product", lazy="joined")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'PENDING_PAYMENT', 'CONFIRMED', 'SHIPPED', 'DELIVERED', 'CANCELLED')",
            name="check_order_status",
        ),
        CheckConstraint(
            "payment_method IN ('COD', 'ONLINE')",
            name="check_order_payment_method",
        ),
        CheckConstraint(
            "payment_status IN ('UNPAID', 'PENDING', 'PAID', 'FAILED', 'EXPIRED', 'REFUNDED')",
            name="check_order_payment_status",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, index=True)
    total_amount = Column(
        Numeric(10, 2),
        CheckConstraint("total_amount >= 0", name="check_total_non_negative"),
        nullable=False,
    )
    status = Column(String(30), nullable=False, default="PENDING")
    payment_method = Column(String(20), nullable=False, default="COD")
    payment_status = Column(String(20), nullable=False, default="UNPAID")
    payment_code = Column(String(50), unique=True, nullable=True)
    payment_expires_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="joined",
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id = Column(
        String(50), ForeignKey("products.id"), nullable=False, index=True
    )
    quantity = Column(
        Integer,
        CheckConstraint("quantity > 0", name="check_order_item_qty_positive"),
        nullable=False,
    )
    unit_price = Column(
        Numeric(10, 2),
        CheckConstraint("unit_price >= 0", name="check_unit_price_non_negative"),
        nullable=False,
    )

    order = relationship("Order", back_populates="items")
    product = relationship("Product", lazy="joined")


class PaymentTransaction(Base):
    """Bảng `payment_transactions` lưu lịch sử đối soát thanh toán (Idempotent Audit Log)."""

    __tablename__ = "payment_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_code = Column(String(50), nullable=False, index=True)
    provider = Column(String(50), nullable=False, default="VIETQR_GATEWAY")
    provider_tx_id = Column(String(100), unique=True, nullable=True)
    amount = Column(
        Numeric(10, 2),
        CheckConstraint("amount >= 0", name="check_payment_tx_amount_non_negative"),
        nullable=False,
    )
    status = Column(String(20), nullable=False, default="SUCCESS")
    raw_payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Review(Base):
    """Bảng `reviews` lưu đánh giá sản phẩm và cung cấp nguồn dữ liệu cho ml_pipeline."""

    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, index=True)
    product_id = Column(
        String(50),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rating = Column(
        Numeric(3, 2),
        CheckConstraint("rating >= 1.0 AND rating <= 5.0", name="check_review_rating"),
        nullable=False,
    )
    title = Column(String(255), nullable=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ------------------------------------------------------------------------------
# 3. PYDANTIC SCHEMAS (REQUEST / RESPONSE)
# ------------------------------------------------------------------------------
class ProductResponse(BaseModel):
    id: str
    product_id: str
    name: str
    category: Optional[str] = None
    price: float
    image_url: Optional[str] = None
    hi_res_url: Optional[str] = None
    large_urls: List[str] = Field(default_factory=list)
    thumb_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    stock_quantity: int
    description: Optional[str] = None
    is_active: bool = True
    rating: float = 4.6
    rating_count: int = 25

    @classmethod
    def from_orm_product(cls, p: Product, rating: float = 4.6, rating_count: int = 25):
        price_val = (
            float(p.price) if isinstance(p.price, Decimal) else float(p.price or 0.0)
        )
        large_list = [u for u in (p.large_urls or []) if u][:3]
        hi_res = p.hi_res_url or (large_list[0] if large_list else p.image_url)
        thumb = p.thumb_url or (large_list[0] if large_list else p.image_url)
        primary_img = p.image_url or hi_res

        return cls(
            id=p.id,
            product_id=p.id,
            name=p.name,
            category=p.category,
            price=round(price_val, 2),
            image_url=primary_img,
            hi_res_url=hi_res,
            large_urls=large_list,
            thumb_url=thumb,
            thumbnail_url=thumb,
            stock_quantity=p.stock_quantity,
            description=p.description,
            is_active=bool(p.is_active) if p.is_active is not None else True,
            rating=rating,
            rating_count=rating_count,
        )


class PaginatedProductResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ProductResponse]


class BatchProductsRequest(BaseModel):
    product_ids: List[str] = Field(
        ..., description="Danh sách mã sản phẩm cần lấy thông tin"
    )


# --- Schemas cho Giỏ hàng (Cart) ---
class AddToCartRequest(BaseModel):
    product_id: str = Field(..., examples=["B01M4HO6RK"])
    quantity: int = Field(default=1, ge=1, le=100)


class UpdateCartItemRequest(BaseModel):
    quantity: int = Field(
        ..., ge=0, le=100, description="Đặt bằng 0 để xóa khỏi giỏ hàng"
    )


class CartItemDetailResponse(BaseModel):
    id: int
    user_id: str
    product_id: str
    product_name: str
    category: Optional[str] = None
    unit_price: float
    image_url: Optional[str] = None
    thumb_url: Optional[str] = None
    stock_quantity: int
    quantity: int
    subtotal: float


class CartSummaryResponse(BaseModel):
    user_id: str
    total_items: int
    total_quantity: int
    total_amount: float
    items: List[CartItemDetailResponse]


# --- Schemas cho Đặt hàng, Checkout & Thanh toán Online ---
class OrderItemInput(BaseModel):
    product_id: str = Field(..., examples=["B01M4HO6RK"])
    quantity: int = Field(default=1, ge=1)


class CheckoutRequest(BaseModel):
    items: Optional[List[OrderItemInput]] = Field(
        default=None,
        description="Danh sách mặt hàng muốn thanh toán. Nếu bỏ trống sẽ lấy toàn bộ giỏ hàng hiện tại của user.",
    )
    payment_method: Literal["COD", "ONLINE"] = Field(
        default="COD",
        description="Phương thức thanh toán: COD hoặc ONLINE (VietQR).",
    )
    simulate_failure: bool = Field(
        default=False,
        description="Cờ kiểm thử: Nếu True, giả lập sự cố sau khi trừ kho để chứng minh ROLLBACK tự động.",
    )


class PaymentQRInfo(BaseModel):
    provider: str = "VIETQR"
    bank_id: str
    account_no: str
    account_name: str
    amount_vnd: int
    payment_code: str
    qr_image_url: str
    expires_at: datetime


class OrderItemResponse(BaseModel):
    id: int
    product_id: str
    product_name: Optional[str] = None
    image_url: Optional[str] = None
    thumb_url: Optional[str] = None
    quantity: int
    unit_price: float
    subtotal: float


class OrderResponse(BaseModel):
    id: int
    user_id: str
    total_amount: float
    status: str
    payment_method: str
    payment_status: str
    payment_code: Optional[str] = None
    payment_expires_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    payment_info: Optional[PaymentQRInfo] = None
    created_at: Optional[datetime] = None
    items: List[OrderItemResponse]


class OrderPaymentStatusResponse(BaseModel):
    """Response gọn nhẹ phục vụ UI Polling mỗi 3-5 giây khi mở màn hình QR."""

    order_id: int
    status: str
    payment_method: str
    payment_status: str
    payment_code: Optional[str] = None
    paid_at: Optional[datetime] = None
    payment_expires_at: Optional[datetime] = None
    remaining_seconds: int = 0


class PaymentWebhookRequest(BaseModel):
    """
    Hỗ trợ đồng thời định dạng chuẩn nội bộ và payload thực tế từ cổng ngân hàng (SePay / Casso).
    """

    payment_code: Optional[str] = Field(default=None, examples=["PAY20261125ABCD1234"])
    content: Optional[str] = Field(
        default=None,
        description="Nội dung chuyển khoản ngân hàng (tự động trích xuất mã PAY... nếu có).",
    )
    provider: str = Field(default="VIETQR_GATEWAY")
    provider_tx_id: Optional[str] = Field(default=None, examples=["FT2632899123"])
    referenceCode: Optional[str] = Field(default=None, description="Mã tham chiếu SePay")
    id: Optional[int | str] = Field(default=None, description="ID giao dịch từ cổng thanh toán")
    amount: Optional[float] = Field(default=None, description="Số tiền thực nhận (VND)")
    transferAmount: Optional[float] = Field(default=None, description="Số tiền chuyển khoản (SePay VND)")
    transferType: Optional[Literal["in", "out"]] = Field(default="in")
    status: Literal["SUCCESS", "FAILED"] = "SUCCESS"


# --- Schemas cho Đánh giá (Reviews) ---
class CreateReviewRequest(BaseModel):
    rating: float = Field(..., ge=1.0, le=5.0, examples=[5.0])
    title: Optional[str] = Field(default="", max_length=255)
    comment: Optional[str] = Field(default="")


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    product_id: str
    rating: float
    title: Optional[str] = None
    comment: Optional[str] = None
    created_at: Optional[datetime] = None