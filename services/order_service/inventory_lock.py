"""
services/order_service/inventory_lock.py
Hiện thực cơ chế Pessimistic Concurrency Control (Khóa bi quan `SELECT ... FOR UPDATE`)
và ACID Transaction Rollback chống vi phạm tồn kho (Anti-Overselling) khi nhiều người dùng
mua cùng một sản phẩm tại cùng một thời điểm.
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from .models import CartItem, Order, OrderItem, OrderItemInput, OrderItemResponse, OrderResponse, Product

logger = logging.getLogger("order_service.inventory_lock")


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


def execute_checkout_with_pessimistic_lock(
    db: Session,
    user_id: str,
    requested_items: Optional[List[OrderItemInput]] = None,
    clear_cart: bool = True,
    simulate_failure: bool = False,
) -> OrderResponse:
    """
    Thực thi giao dịch đặt hàng với khóa hàng bi quan (Pessimistic Row-Level Lock):
    ```sql
    BEGIN;
    SELECT id, name, price, stock_quantity FROM products WHERE id = :product_id FOR UPDATE;
    -- Kiểm tra: Nếu stock_quantity < requested_quantity => ROLLBACK và báo lỗi hết hàng
    UPDATE products SET stock_quantity = stock_quantity - :requested_quantity WHERE id = :product_id;
    INSERT INTO orders (user_id, total_amount, status) VALUES (...);
    COMMIT;
    ```
    """
    try:
        # 1. Xác định danh sách mặt hàng cần đặt (từ payload trực tiếp hoặc từ giỏ hàng của user)
        items_map: Dict[str, int] = {}
        if requested_items and len(requested_items) > 0:
            for item in requested_items:
                items_map[item.product_id] = items_map.get(item.product_id, 0) + int(item.quantity)
        else:
            cart_rows = (
                db.query(CartItem)
                .filter(CartItem.user_id == user_id)
                .all()
            )
            if not cart_rows:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Giỏ hàng trống. Vui lòng thêm sản phẩm trước khi đặt hàng.",
                )
            for c_item in cart_rows:
                items_map[c_item.product_id] = items_map.get(c_item.product_id, 0) + int(c_item.quantity)

        # Sắp xếp danh sách product_id theo thứ tự từ điển để phòng chống Deadlock
        # khi nhiều giao dịch khóa nhiều sản phẩm cùng lúc.
        sorted_product_ids = sorted(items_map.keys())

        locked_products: Dict[str, Product] = {}
        total_amount = Decimal("0.00")

        # 2. Thực thi câu lệnh khóa bi quan `SELECT ... FOR UPDATE` trên từng dòng sản phẩm
        for pid in sorted_product_ids:
            req_qty = items_map[pid]

            # Khóa trực tiếp dòng dữ liệu trong bảng products cho tới khi transaction COMMIT/ROLLBACK
            product_row = (
                db.query(Product)
                .filter(Product.id == pid)
                .with_for_update()
                .first()
            )

            if not product_row:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Sản phẩm có mã '{pid}' không tồn tại.",
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

            # 3. Trừ số lượng tồn kho
            product_row.stock_quantity = product_row.stock_quantity - req_qty
            locked_products[pid] = product_row

            unit_price = Decimal(str(product_row.price))
            total_amount += unit_price * Decimal(req_qty)

        # 4. Tạo bản ghi Đơn hàng (orders) và Chi tiết đơn hàng (order_items)
        new_order = Order(
            user_id=user_id,
            total_amount=total_amount,
            status="CONFIRMED",
        )
        db.add(new_order)
        db.flush()  # Lấy new_order.id trước khi commit

        order_item_objects: List[OrderItem] = []
        for pid in sorted_product_ids:
            prod = locked_products[pid]
            qty = items_map[pid]
            oi = OrderItem(
                order_id=new_order.id,
                product_id=pid,
                quantity=qty,
                unit_price=prod.price,
            )
            db.add(oi)
            order_item_objects.append(oi)

        # 5. Xóa giỏ hàng của người dùng sau khi tạo đơn
        if clear_cart:
            db.query(CartItem).filter(CartItem.user_id == user_id).delete(
                synchronize_session=False
            )

        # 6. Kiểm thử lỗi giả lập (nếu client bật simulate_failure=True)
        if simulate_failure:
            raise SimulatedPaymentFailureError(
                "Giả lập lỗi cổng thanh toán sau khi đã trừ tồn kho -> Kích hoạt ROLLBACK tự động!"
            )

        # 7. Hoàn tất giao dịch ACID
        db.commit()
        db.refresh(new_order)

        logger.info(
            f"[COMMIT] Đặt hàng thành công Order #{new_order.id} cho User={user_id} | Tổng tiền=${total_amount}"
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
        logger.error(f"[ROLLBACK] Lỗi không xác định khi xử lý đơn hàng: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Giao dịch thất bại và đã được ROLLBACK an toàn: {str(exc)}",
        )
