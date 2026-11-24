"""
services/order_service/inventory_lock.py
Hiện thực cơ chế Pessimistic Concurrency Control (Khóa bi quan `SELECT ... FOR UPDATE`),
ACID Transaction Rollback chống vi phạm tồn kho (Anti-Overselling),
tạo thông tin thanh toán động VietQR và tự động hoàn kho cho đơn Online quá hạn.
"""

import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional
from urllib.parse import quote

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .models import (
    CartItem,
    Order,
    OrderItem,
    OrderItemInput,
    OrderItemResponse,
    OrderResponse,
    PaymentQRInfo,
    Product,
)

logger = logging.getLogger("order_service.inventory_lock")

PAYMENT_CODE_PATTERN = re.compile(r"(PAY\d{8}[A-Z0-9]{8})", re.IGNORECASE)


def get_vietqr_config() -> dict:
    """Đọc cấu hình VietQR & tỷ giá từ biến môi trường (.env)."""
    ttl_raw = os.getenv("PAYMENT_TTL_MINUTES") or os.getenv("PAYMENT_EXPIRE_MINUTES") or "15"
    return {
        "bank_id": os.getenv("VIETQR_BANK_ID", "MB").strip(),
        "account_no": os.getenv("VIETQR_ACCOUNT_NO", "0334035365").strip(),
        "account_name": os.getenv("VIETQR_ACCOUNT_NAME", "ECOMMERCE MUSIC STORE").strip(),
        "usd_to_vnd_rate": int(os.getenv("USD_TO_VND_RATE", "1000")),
        "ttl_minutes": int(ttl_raw),
    }


def extract_payment_code(
    explicit_code: Optional[str], transfer_content: Optional[str]
) -> Optional[str]:
    """Lấy trực tiếp `payment_code` hoặc trích xuất mẫu `PAYyyyymmddXXXXXXXX` từ nội dung chuyển khoản."""
    if explicit_code and explicit_code.strip():
        return explicit_code.strip().upper()
    if transfer_content:
        match = PAYMENT_CODE_PATTERN.search(transfer_content)
        if match:
            return match.group(1).upper()
    return None


def calculate_expected_vnd(total_amount_usd: Decimal | float) -> int:
    """Quy đổi giá trị đơn hàng sang VND theo cấu hình `USD_TO_VND_RATE`."""
    rate = get_vietqr_config()["usd_to_vnd_rate"]
    return max(1000, int(round(float(total_amount_usd) * rate)))


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Chuẩn hóa datetime về timezone-aware UTC để tránh lỗi so sánh naive/aware."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def build_vietqr_info(order: Order) -> Optional[PaymentQRInfo]:
    """Tạo payload & link ảnh QR động theo chuẩn VietQR."""
    if order.payment_method != "ONLINE" or not order.payment_code:
        return None

    expires_at = ensure_utc(order.payment_expires_at)
    if not expires_at:
        return None

    cfg = get_vietqr_config()
    amount_vnd = calculate_expected_vnd(order.total_amount)
    encoded_info = quote(order.payment_code)
    encoded_name = quote(cfg["account_name"])
    qr_url = (
        f"https://img.vietqr.io/image/{cfg['bank_id']}-{cfg['account_no']}-compact2.png"
        f"?amount={amount_vnd}&addInfo={encoded_info}&accountName={encoded_name}"
    )

    return PaymentQRInfo(
        provider="VIETQR",
        bank_id=cfg["bank_id"],
        account_no=cfg["account_no"],
        account_name=cfg["account_name"],
        amount_vnd=amount_vnd,
        payment_code=order.payment_code,
        qr_image_url=qr_url,
        expires_at=expires_at,
    )


class InsufficientStockError(Exception):
    """Ngoại lệ khi số lượng tồn kho không đủ đáp ứng yêu cầu đặt hàng."""

    def __init__(self, product_id: str, product_name: str, available: int, requested: int):
        self.product_id = product_id
        self.product_name = product_name
        self.available = available
        self.requested = requested
        super().__init__(
            f"Sản phẩm '{product_name}' ({product_id}) không đủ tồn kho "
            f"(Còn lại: {available}, Yêu cầu: {requested})."
        )


class SimulatedPaymentFailureError(Exception):
    """Ngoại lệ giả lập lỗi thanh toán/mạng để kiểm chứng cơ chế ROLLBACK ACID."""


def release_expired_online_orders(db: Session, user_id: Optional[str] = None) -> int:
    """
    Tận dụng partial index `idx_orders_pending_payment_expires` để thu hồi các đơn ONLINE
    đã quá hạn thanh toán nhưng chưa nhận webhook, đồng thời hoàn trả tồn kho an toàn
    bằng `FOR UPDATE SKIP LOCKED` (không gây nghẽn hay hoàn kho trùng lặp).
    """
    now_utc = datetime.now(timezone.utc)
    query = db.query(Order).filter(
        Order.payment_method == "ONLINE",
        Order.payment_status.in_(["UNPAID", "PENDING", "FAILED"]),
        Order.status.in_(["PENDING", "PENDING_PAYMENT"]),
        Order.payment_expires_at.isnot(None),
        Order.payment_expires_at < now_utc,
    )
    if user_id:
        query = query.filter(Order.user_id == user_id)

    expired_orders = query.with_for_update(of=Order, skip_locked=True).all()
    if not expired_orders:
        return 0

    released_count = 0
    for order in expired_orders:
        order.status = "CANCELLED"
        order.payment_status = "EXPIRED"

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

        released_count += 1
        logger.info(
            f"[EXPIRED-RELEASE] Tự động hủy Order #{order.id} (code={order.payment_code}) "
            f"và hoàn trả tồn kho."
        )

    db.commit()
    return released_count


def execute_checkout_with_pessimistic_lock(
    db: Session,
    user_id: str,
    requested_items: Optional[List[OrderItemInput]] = None,
    payment_method: str = "COD",
    clear_cart: bool = True,
    simulate_failure: bool = False,
) -> OrderResponse:
    """
    Thực thi giao dịch đặt hàng với khóa hàng bi quan (Pessimistic Row-Level Lock).
    """
    try:
        items_map: Dict[str, int] = {}
        if requested_items and len(requested_items) > 0:
            for item in requested_items:
                if int(item.quantity) <= 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Số lượng đặt hàng cho '{item.product_id}' phải lớn hơn 0.",
                    )
                items_map[item.product_id] = items_map.get(item.product_id, 0) + int(
                    item.quantity
                )
        else:
            cart_rows = db.query(CartItem).filter(CartItem.user_id == user_id).all()
            if not cart_rows:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Giỏ hàng trống. Vui lòng thêm sản phẩm trước khi đặt hàng.",
                )
            for c_item in cart_rows:
                items_map[c_item.product_id] = items_map.get(c_item.product_id, 0) + int(
                    c_item.quantity
                )

        # Sắp xếp product_id tăng dần để chống Deadlock
        sorted_product_ids = sorted(items_map.keys())
        locked_products: Dict[str, Product] = {}
        total_amount = Decimal("0.00")

        for pid in sorted_product_ids:
            req_qty = items_map[pid]
            product_row = (
                db.query(Product)
                .filter(Product.id == pid)
                .with_for_update()
                .first()
            )

            if not product_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Sản phẩm có mã '{pid}' không tồn tại.",
                )

            if not product_row.is_active:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Sản phẩm '{product_row.name}' ({pid}) đã ngừng kinh doanh.",
                )

            if product_row.stock_quantity < req_qty:
                logger.warning(
                    f"[ROLLBACK] Hết hàng/Không đủ kho cho SP {pid}: "
                    f"Tồn kho={product_row.stock_quantity}, Yêu cầu={req_qty}"
                )
                raise InsufficientStockError(
                    product_id=pid,
                    product_name=product_row.name,
                    available=product_row.stock_quantity,
                    requested=req_qty,
                )

            product_row.stock_quantity = product_row.stock_quantity - req_qty
            locked_products[pid] = product_row

            unit_price = Decimal(str(product_row.price))
            total_amount += unit_price * Decimal(req_qty)

        now_utc = datetime.now(timezone.utc)
        ttl_minutes = get_vietqr_config()["ttl_minutes"]
        if payment_method == "ONLINE":
            order_status = "PENDING_PAYMENT"
            payment_status = "PENDING"
            payment_code = (
                f"PAY{now_utc.strftime('%Y%m%d')}{uuid.uuid4().hex[:8].upper()}"
            )
            payment_expires_at = now_utc + timedelta(minutes=ttl_minutes)
        else:
            order_status = "CONFIRMED"
            payment_status = "UNPAID"
            payment_code = None
            payment_expires_at = None

        new_order = Order(
            user_id=user_id,
            total_amount=total_amount,
            status=order_status,
            payment_method=payment_method,
            payment_status=payment_status,
            payment_code=payment_code,
            payment_expires_at=payment_expires_at,
        )
        db.add(new_order)
        db.flush()

        for pid in sorted_product_ids:
            prod = locked_products[pid]
            qty = items_map[pid]
            db.add(
                OrderItem(
                    order_id=new_order.id,
                    product_id=pid,
                    quantity=qty,
                    unit_price=prod.price,
                )
            )

        if clear_cart:
            db.query(CartItem).filter(CartItem.user_id == user_id).delete(
                synchronize_session=False
            )

        if simulate_failure:
            raise SimulatedPaymentFailureError(
                "Giả lập lỗi cổng thanh toán sau khi đã trừ tồn kho -> Kích hoạt ROLLBACK tự động!"
            )

        db.commit()
        db.refresh(new_order)

        logger.info(
            f"[COMMIT] Đặt hàng thành công Order #{new_order.id} ({payment_method}) "
            f"cho User={user_id} | Tổng tiền=${total_amount}"
        )

        response_items: List[OrderItemResponse] = []
        for oi in new_order.items:
            prod = locked_products.get(oi.product_id) or oi.product
            u_price = float(oi.unit_price)
            response_items.append(
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

        return OrderResponse(
            id=new_order.id,
            user_id=new_order.user_id,
            total_amount=round(float(new_order.total_amount), 2),
            status=new_order.status,
            payment_method=new_order.payment_method,
            payment_status=new_order.payment_status,
            payment_code=new_order.payment_code,
            payment_expires_at=new_order.payment_expires_at,
            paid_at=new_order.paid_at,
            payment_info=(
                build_vietqr_info(new_order)
                if new_order.payment_status == "PENDING"
                else None
            ),
            created_at=new_order.created_at,
            items=response_items,
        )

    except InsufficientStockError as stock_err:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "INSUFFICIENT_STOCK",
                "message": str(stock_err),
                "product_id": stock_err.product_id,
                "available_stock": stock_err.available,
                "requested_quantity": stock_err.requested,
            },
        )
    except SimulatedPaymentFailureError as sim_err:
        db.rollback()
        logger.warning(f"[ROLLBACK] Đã hoàn trả nguyên vẹn số lượng tồn kho: {sim_err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "PAYMENT_FAILED_ROLLED_BACK",
                "message": str(sim_err),
                "rolled_back": True,
            },
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.error(
            f"[ROLLBACK] Lỗi không xác định khi xử lý đơn hàng: {exc}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Giao dịch thất bại và đã được ROLLBACK an toàn: {str(exc)}",
        )