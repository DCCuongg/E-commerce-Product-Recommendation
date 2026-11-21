-- 1. Bảng danh mục sản phẩm (Hỗ trợ Soft-Archive qua is_active & Pessimistic Lock FOR UPDATE)
-- 1. Bảng danh mục sản phẩm (Hỗ trợ đa kích thước ảnh, Soft-Archive & Pessimistic Lock FOR UPDATE)
CREATE TABLE IF NOT EXISTS products (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    price NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    image_url TEXT,
    hi_res_url TEXT,
    large_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
    thumb_url TEXT,
    stock_quantity INT NOT NULL DEFAULT 100 CHECK (stock_quantity >= 0),
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_products_active_category_created ON products (category, created_at DESC)
WHERE
    is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_products_active_created ON products (created_at DESC)
WHERE
    is_active = TRUE;
-- 2. Bảng Giỏ hàng (Cart Items)
-- (Không cần index riêng cho user_id vì ràng buộc UNIQUE (user_id, product_id) đã tự tạo index đứng đầu bằng user_id)
CREATE TABLE IF NOT EXISTS cart_items (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    product_id VARCHAR(50) NOT NULL REFERENCES products (id) ON DELETE CASCADE,
    quantity INT NOT NULL DEFAULT 1 CHECK (quantity > 0),
    created_at TIMESTAMP
    WITH
        TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP
    WITH
        TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT unique_user_product_cart UNIQUE (user_id, product_id)
);

-- 3. Bảng Đơn hàng (Orders - Append-Only State Machine + Online Payment)
-- (Không cần index riêng cho payment_code vì ràng buộc UNIQUE đã tự tạo index)
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL REFERENCES users (id),
    total_amount NUMERIC(10, 2) NOT NULL CHECK (total_amount >= 0),
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING' CHECK (
        status IN (
            'PENDING',
            'PENDING_PAYMENT',
            'CONFIRMED',
            'SHIPPED',
            'DELIVERED',
            'CANCELLED'
        )
    ),
    payment_method VARCHAR(20) NOT NULL DEFAULT 'COD' CHECK (
        payment_method IN ('COD', 'ONLINE')
    ),
    payment_status VARCHAR(20) NOT NULL DEFAULT 'UNPAID' CHECK (
        payment_status IN (
            'UNPAID',
            'PENDING',
            'PAID',
            'FAILED',
            'EXPIRED',
            'REFUNDED'
        )
    ),
    payment_code VARCHAR(50) UNIQUE,
    payment_expires_at TIMESTAMP
    WITH
        TIME ZONE,
        paid_at TIMESTAMP
    WITH
        TIME ZONE,
        created_at TIMESTAMP
    WITH
        TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP
    WITH
        TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_orders_user_created ON orders (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_orders_active_status ON orders (status, created_at ASC)
WHERE
    status IN (
        'PENDING',
        'PENDING_PAYMENT',
        'CONFIRMED',
        'SHIPPED'
    );

CREATE INDEX IF NOT EXISTS idx_orders_pending_payment_expires ON orders (payment_expires_at)
WHERE
    payment_method = 'ONLINE'
    AND payment_status IN ('UNPAID', 'PENDING');

-- 4. Bảng Chi tiết đơn hàng (Order Items)
CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INT NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    product_id VARCHAR(50) NOT NULL REFERENCES products (id),
    quantity INT NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(10, 2) NOT NULL CHECK (unit_price >= 0)
);

CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items (order_id);

CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON order_items (product_id);

-- 5. Bảng Lịch sử giao dịch thanh toán (Payment Transactions - Idempotent Audit Log)
CREATE TABLE IF NOT EXISTS payment_transactions (
    id SERIAL PRIMARY KEY,
    order_id INT NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    payment_code VARCHAR(50) NOT NULL,
    provider VARCHAR(50) NOT NULL DEFAULT 'VIETQR_GATEWAY',
    provider_tx_id VARCHAR(100) UNIQUE,
    amount NUMERIC(10, 2) NOT NULL CHECK (amount >= 0),
    status VARCHAR(20) NOT NULL DEFAULT 'SUCCESS',
    raw_payload JSONB,
    created_at TIMESTAMP
    WITH
        TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_payment_tx_order_id ON payment_transactions (order_id);

CREATE INDEX IF NOT EXISTS idx_payment_tx_payment_code ON payment_transactions (payment_code);

-- 6. Bảng Đánh giá sản phẩm (Reviews - Chuẩn hóa schema & ràng buộc DB)
CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    product_id VARCHAR(50) NOT NULL REFERENCES products (id) ON DELETE CASCADE,
    rating NUMERIC(3, 2) NOT NULL CHECK (
        rating >= 1.0
        AND rating <= 5.0
    ),
    title VARCHAR(255),
    comment TEXT,
    created_at TIMESTAMP
    WITH
        TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reviews_product_created ON reviews (product_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_reviews_user_id ON reviews (user_id);