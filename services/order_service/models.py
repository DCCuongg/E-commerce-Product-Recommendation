"""
services/order_service/models.py
Định nghĩa ORM Models (SQLAlchemy) cho các bảng `products`, `cart_items`, `orders`, `order_items`, `reviews`
và Pydantic Schemas cho Order/Cart/Product Service (Port 8002).
"""

import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
)
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

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}?sslmode={POSTGRES_SSL_MODE}",
)

engine = create_engine(
    DATABASE_URL,
    pool_size=15,
    max_overflow=30,
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
# 2. SQLALCHEMY ORM MODELS (Khớp với 02_init_order_db.sql & etl_extractor.py)
# ------------------------------------------------------------------------------
class Product(Base):
    __tablename__ = "products"

    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100), index=True)
    price = Column(Numeric(10, 2), nullable=False, default=0.00)
    image_url = Column(Text, nullable=True)
    stock_quantity = Column(
        Integer,
        CheckConstraint("stock_quantity >= 0", name="check_stock_non_negative"),
        nullable=False,
        default=100,
    )
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="unique_user_product_cart"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, index=True)
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

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, index=True)
    total_amount = Column(
        Numeric(10, 2),
        CheckConstraint("total_amount >= 0", name="check_total_non_negative"),
        nullable=False,
    )
    status = Column(String(30), nullable=False, default="CONFIRMED")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

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
    product_id = Column(String(50), ForeignKey("products.id"), nullable=False)
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


class Review(Base):
    """Bảng `reviews` lưu đánh giá sản phẩm và cung cấp nguồn dữ liệu cho ml_pipeline/etl_extractor.py."""

    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, index=True)
    product_id = Column(
        String(50),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rating = Column(Float, nullable=False)
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
    thumbnail_url: Optional[str] = None
    stock_quantity: int
    description: Optional[str] = None
    rating: float = 4.6
    rating_count: int = 25

    @classmethod
    def from_orm_product(cls, p: Product, rating: float = 4.6, rating_count: int = 25):
        price_val = float(p.price) if isinstance(p.price, Decimal) else float(p.price or 0.0)
        return cls(
            id=p.id,
            product_id=p.id,
            name=p.name,
            category=p.category,
            price=round(price_val, 2),
            image_url=p.image_url,
            thumbnail_url=p.image_url,
            stock_quantity=p.stock_quantity,
            description=p.description,
            rating=rating,
            rating_count=rating_count,
        )


class PaginatedProductResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ProductResponse]


class BatchProductsRequest(BaseModel):
    product_ids: List[str] = Field(..., description="Danh sách mã sản phẩm cần lấy thông tin")


# --- Schemas cho Giỏ hàng (Cart) ---
class AddToCartRequest(BaseModel):
    product_id: str = Field(..., examples=["B01M4HO6RK"])
    quantity: int = Field(default=1, ge=1, le=100)


class UpdateCartItemRequest(BaseModel):
    quantity: int = Field(..., ge=0, le=100, description="Đặt bằng 0 để xóa khỏi giỏ hàng")


class CartItemDetailResponse(BaseModel):
    id: int
    user_id: str
    product_id: str
    product_name: str
    category: Optional[str] = None
    unit_price: float
    image_url: Optional[str] = None
    stock_quantity: int
    quantity: int
    subtotal: float


class CartSummaryResponse(BaseModel):
    user_id: str
    total_items: int
    total_quantity: int
    total_amount: float
    items: List[CartItemDetailResponse]


# --- Schemas cho Đặt hàng & Checkout ---
class OrderItemInput(BaseModel):
    product_id: str = Field(..., examples=["B01M4HO6RK"])
    quantity: int = Field(default=1, ge=1)


class CheckoutRequest(BaseModel):
    items: Optional[List[OrderItemInput]] = Field(
        default=None,
        description="Danh sách mặt hàng muốn thanh toán. Nếu bỏ trống sẽ lấy toàn bộ giỏ hàng hiện tại của user.",
    )
    simulate_failure: bool = Field(
        default=False,
        description="Cờ kiểm thử: Nếu True, giả lập sự cố sau khi trừ kho để chứng minh ROLLBACK tự động hoàn trả tồn kho.",
    )


class OrderItemResponse(BaseModel):
    id: int
    product_id: str
    product_name: Optional[str] = None
    image_url: Optional[str] = None
    quantity: int
    unit_price: float
    subtotal: float


class OrderResponse(BaseModel):
    id: int
    user_id: str
    total_amount: float
    status: str
    created_at: Optional[datetime] = None
    items: List[OrderItemResponse]


# --- Schemas cho Đánh giá (Reviews) ---
class CreateReviewRequest(BaseModel):
    rating: float = Field(..., ge=1.0, le=5.0, examples=[5.0])
    title: Optional[str] = Field(default="", max_length=255)
    comment: Optional[str] = Field(default="")


class ReviewResponse(BaseModel):
    id: int
    user_id: str
    product_id: str
    rating: float
    title: Optional[str] = None
    comment: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
