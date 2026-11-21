
# TÀI LIỆU HƯỚNG DẪN CHẠY BACKEND, DATABASE & DANH SÁCH API (BÀN GIAO FRONTEND)

Tài liệu hướng dẫn khởi chạy hạ tầng Docker (PostgreSQL, Azurite, Azure Cosmos DB Emulator), chạy toàn bộ 4 dịch vụ Backend và đặc tả REST API (bao gồm ảnh đa độ phân giải, thanh toán Online VietQR và phân quyền Admin RBAC) để đội ngũ Frontend tích hợp[cite: 1].

---

## 1. Tổng quan Hạ tầng & Cổng dịch vụ (Ports)

### 1.1. Hạ tầng Database & Storage Emulators (Docker)

| Container Name | Dịch vụ | Port | Thông tin kết nối / Ghi chú |
| --- | --- | --- | --- |
| `ecommerce_postgres_dev` | PostgreSQL 16 | `5432` | DB: `ecommerce_shop_db` \| User: `postgres_admin` \| Pass: `YourSecurePasswordHere123!`[cite: 1] |
| `ecommerce_azurite_dev` | Azure Blob Storage Emulator | `10000` | Containers: `raw-data`, `processed-data`, `model-artifacts`, `interaction-logs`[cite: 1] |
| `ecommerce_cosmos_dev` | Azure Cosmos DB NoSQL Emulator | `8081` | DB: `ecommerce_recommender_db` (`system_metadata`, `user_recommendations`, `item_recommendations`)[cite: 1] |

### 1.2. Các Microservices & FaaS Backend

| Dịch vụ | Mã nguồn | Base URL | Swagger UI | Chức năng chính |
| --- | --- | --- | --- | --- |
| **Auth Service** | `services/auth_service/` | `http://localhost:8001` | `http://localhost:8001/docs` | Đăng ký, đăng nhập, JWT, Soft-Disable & Admin Users RBAC[cite: 1] |
| **Order & Cart Service** | `services/order_service/` | `http://localhost:8002` | `http://localhost:8002/docs` | Danh mục 1.000 SP (ảnh đa độ phân giải), Giỏ hàng, Đặt hàng (`FOR UPDATE`), Thanh toán Online VietQR/Webhook, Đánh giá & Admin Shop[cite: 1] |
| **Recommender Service** | `services/recommender_service/` | `http://localhost:8003` | `http://localhost:8003/docs` | Gợi ý cá nhân hóa (SVD), Cold-Start Trending, Mua kèm (Bundle)[cite: 1] |
| **Log Interaction (FaaS)** | `azure_functions/LogInteractionFunction/` | `http://localhost:7071` | `http://localhost:7071/docs` | Ghi nhận hành vi click/xem/thêm giỏ/mua hàng/đánh giá vào Append Blob[cite: 1] |

---

## 2. Hướng dẫn Khởi chạy Hệ thống Local

### Bước 1: Kích hoạt môi trường ảo (`.venv`) & Cấu hình `.env`
```bash
source .venv/Scripts/activate        # Git Bash (Windows)
# .venv\Scripts\Activate.ps1         # PowerShell

cp .env.example .env
# Đảm bảo .env có các biến Payment & Policy v2:
# PAYMENT_WEBHOOK_SECRET="dev-payment-webhook-secret-2026"
# PAYMENT_EXPIRE_MINUTES=15
# ALLOW_DEV_X_USER_ID="true"

```

### Bước 2: Khởi động Docker Containers

(Dùng `docker compose down -v` trước nếu cần làm sạch volume DB cũ để nạp schema mới).

```bash
docker compose up -d

```

### Bước 3: Khởi tạo Schema & Nạp dữ liệu mẫu (Chạy 1 lần đầu hoặc khi reset DB)

```bash
python scripts/init_local_dev.py

```

Tự động đồng bộ dataset từ Hugging Face (`cuongduongok/amazon-musical-instruments-clean`), tạo container trên Azurite/Cosmos và nạp **1.000 sản phẩm nhạc cụ** (kèm ảnh `hi_res_url`, `large_urls`, `thumb_url`) + **3 tài khoản mẫu** vào PostgreSQL.

### Bước 4: Khởi chạy toàn bộ 4 dịch vụ Backend

```bash
python scripts/run_backend_services.py

```

Mở đồng thời 4 cổng `8001`, `8002`, `8003`, `7071`. Nhấn `Ctrl + C` để dừng Backend; chạy `docker compose down` để tắt Docker khi nghỉ làm việc.

### Bước 5: Kiểm thử tự động toàn bộ luồng API (Tùy chọn)

```bash
python scripts/test_backend_apis.py

```

---

## 3. Cơ chế Xác thực & Tài khoản Demo

### 3.1. Tài khoản mẫu trong Database

| Username | Email | Password | User ID | Role | Trạng thái |
| --- | --- | --- | --- | --- | --- |
| `cuongduong` | `cuong@ecommerce.local` | `Password123!` | `U_TEST_01` | `customer` | Hoạt động (`is_disabled = false`)

 |
| `testuser` | `test@ecommerce.local` | `Password123!` | `U_TEST_02` | `customer` | Hoạt động (`is_disabled = false`)

 |
| `admin` | `admin@ecommerce.local` | `Password123!` | `U_ADMIN_01` | `admin` | Quản trị viên (`role = admin`)

 |

### 3.2. Cách truyền Token từ Frontend

```http
Authorization: Bearer <access_token>

```

(Môi trường dev có thể truyền nhanh `X-User-Id: U_TEST_01` khi `ALLOW_DEV_X_USER_ID="true"`).

---

## 4. Danh sách Chi tiết API theo Từng Microservice

### 4.1. Auth Service (`http://localhost:8001`)

| Method | Endpoint | Auth | Mô tả |
| --- | --- | --- | --- |
| `GET` | `/health` | Không | Kiểm tra trạng thái service và kết nối PostgreSQL

 |
| `POST` | `/api/v1/auth/register` | Không | Đăng ký tài khoản mới (`username`, `email`, `password`, tùy chọn `user_id`)

 |
| `POST` | `/api/v1/auth/login` | Không | Đăng nhập bằng `username` hoặc `email` (chặn tài khoản `is_disabled = true`)

 |
| `GET` / `POST` | `/api/v1/auth/verify-token` | Bearer | Xác thực JWT & trạng thái `is_disabled` theo thời gian thực

 |
| `GET` | `/api/v1/auth/me` | Bearer | Lấy thông tin user đang đăng nhập

 |
| `GET` | `/api/v1/auth/users` | Không | Lấy danh sách user (`?limit=20`) để chuyển đổi nhanh khi demo

 |
| `GET` / `PATCH` | `/api/v1/admin/users` & `/{user_id}` | Admin | Quản lý người dùng: phân quyền `role` (`customer`/`admin`), khóa/mở khóa tài khoản (`is_disabled`, `disabled_reason`)

 |

---

### 4.2. Order, Cart, Product & Payment Service (`http://localhost:8002`)

#### A. Danh mục Sản phẩm (Public — chỉ trả về sản phẩm `is_active = TRUE`)

| Method | Endpoint | Mô tả & Query Parameters |
| --- | --- | --- |
| `GET` | `/health` | Kiểm tra trạng thái service và tổng số sản phẩm

 |
| `GET` | `/api/v1/products` | Danh sách sản phẩm phân trang (`page`, `page_size`, `category`, `search`, `sort_by`: `default` | `price_asc` | `price_desc` | `name_asc`)

 |
| `GET` | `/api/v1/products/categories` | Danh sách toàn bộ danh mục kèm số lượng sản phẩm

 |
| `POST` | `/api/v1/products/batch` | Lấy chi tiết nhiều sản phẩm theo danh sách ID: `{"product_ids": ["B01M4HO6RK", "B0002E1G5C"]}`

 |
| `GET` | `/api/v1/products/{product_id}` | Chi tiết 1 sản phẩm, tồn kho (`stock_quantity`), điểm đánh giá trung bình & bộ ảnh đa độ phân giải

 |

> **Cấu trúc trường ảnh trong Object Sản phẩm:**
> * `thumb_url` *(string)*: Ảnh thu nhỏ hiển thị trên Product Card / Danh sách / Giỏ hàng.
> 
> 
> * `large_urls` *(array of up to 3 strings)*: Bộ sưu tập ảnh chi tiết hiển thị trên Gallery trang sản phẩm.
> 
> 
> * `hi_res_url` *(string)*: Ảnh độ phân giải cao dùng khi phóng to (Zoom).
> 
> 
> * `image_url` *(string)*: Trường tương thích ngược (ưu tiên `hi_res_url`).
> 
> 
> 
> 

#### B. Quản lý Giỏ hàng (Yêu cầu Bearer Token)

| Method | Endpoint | Mô tả & Body |
| --- | --- | --- |
| `GET` | `/api/v1/cart` | Lấy giỏ hàng (`items`, `total_items`, `total_quantity`, `total_amount`)

 |
| `POST` | `/api/v1/cart/items` | Thêm vào giỏ: `{"product_id": "B01M4HO6RK", "quantity": 1}`

 |
| `PUT` | `/api/v1/cart/items/{product_id}` | Cập nhật số lượng (`0` để xóa): `{"quantity": 3}`

 |
| `DELETE` | `/api/v1/cart/items/{product_id}` | Xóa 1 sản phẩm khỏi giỏ

 |
| `DELETE` | `/api/v1/cart` | Xóa sạch giỏ hàng

 |

#### C. Đặt hàng, Thanh toán Online (VietQR) & Đánh giá (Yêu cầu Bearer Token)

| Method | Endpoint | Mô tả & Body |
| --- | --- | --- |
| `POST` | `/api/v1/orders/checkout` *(hoặc `/api/v1/orders`)* | Tạo đơn hàng & giữ kho (`SELECT ... FOR UPDATE`). |



Body: `{"items": [{"product_id": "B01M4HO6RK", "quantity": 1}], "payment_method": "COD" \| "ONLINE"}` *(bỏ trống `items` để checkout toàn bộ giỏ hàng)*. |
| `GET` | `/api/v1/orders` & `/{order_id}` | Lấy lịch sử đơn hàng / chi tiết 1 đơn hàng (`status`, `payment_method`, `payment_status`, `payment_code`, `payment_expires_at`) |
| `POST` | `/api/v1/orders/{order_id}/cancel` | Khách tự hủy đơn khi đang `PENDING` hoặc `PENDING_PAYMENT` (tự động hoàn trả tồn kho) |
| `GET` | `/api/v1/payments/{order_id}` | Lấy thông tin thanh toán Online (mã `PAY-xxxxxx`, URL ảnh VietQR, thời gian hết hạn 15 phút) |
| `POST` | `/api/v1/payments/webhook` | Webhook đối soát thanh toán tự động (xác thực header `X-Payment-Signature` HMAC-SHA256) |
| `POST` | `/api/v1/payments/{order_id}/simulate-confirm` | Endpoint giả lập xác nhận thanh toán thành công trên môi trường Dev/Demo |
| `GET` / `POST` | `/api/v1/products/{product_id}/reviews` | Xem danh sách đánh giá (Public) / Gửi đánh giá mới (Bearer): `{"rating": 5, "title": "Rất tốt", "comment": "..."}` |

#### D. Quản trị Cửa hàng Admin RBAC (`role == 'admin'`)

| Method | Endpoint | Mô tả |
| --- | --- | --- |
| `GET` / `POST` / `PUT` / `DELETE` | `/api/v1/admin/products` & `/{product_id}` | Thêm, sửa, cập nhật tồn kho, ẩn/hiện sản phẩm (`is_active = false` nếu đã phát sinh đơn hàng)

 |
| `GET` / `PATCH` | `/api/v1/admin/orders` & `/{order_id}/status` | Xem toàn bộ đơn hàng và cập nhật trạng thái theo State Machine (`CONFIRMED` $\rightarrow$ `SHIPPED` $\rightarrow$ `DELIVERED` hoặc `CANCELLED` hoàn kho)

 |
| `GET` / `DELETE` | `/api/v1/admin/reviews` & `/{review_id}` | Kiểm duyệt và xóa đánh giá vi phạm

 |

---

### 4.3. Recommender Service (`http://localhost:8003`)

| Method | Endpoint | Mô tả & Query Parameters |
| --- | --- | --- |
| `GET` | `/health` | Trạng thái model, `deployment_slot` (`blue`/`green`), `model_version`

 |
| `GET` | `/api/v1/recommendations/{user_id}` | Top-K gợi ý cá nhân hóa cho Trang chủ (`?top_k=10`), tự fallback sang `cold_start_popular` nếu user mới

 |
| `GET` | `/api/v1/recommendations/popular/trending` | Top-K sản phẩm thịnh hành cho khách vãng lai (`?top_k=10`)

 |
| `GET` | `/api/v1/products/{product_id}/frequently-bought-together` | Top-K sản phẩm thường mua cùng (`?top_k=5`) cho Trang chi tiết sản phẩm

 |
| `POST` | `/api/v1/recommendations/reload` | Nạp lại model artifacts và xóa cache RAM

 |

---

### 4.4. Azure Function FaaS (`http://localhost:7071`)

| Method | Endpoint | Auth | Mô tả |
| --- | --- | --- | --- |
| `POST` | `/api/LogInteractionFunction` | Không | Ghi nhận sự kiện tương tác: `{"user_id": "U_TEST_01", "product_id": "B01M4HO6RK", "action": "view", "value": null}`

 |

* **Các `action` hợp lệ:** `"view"` (`1.0`), `"click"` (`2.0`), `"add_to_cart"` (`3.5`), `"checkout"` (`4.5`), `"purchase"` (`5.0`), `"rating"` (kèm `"value"` từ `1.0` đến `5.0`).



---

## 5. Lưu ý Tích hợp dành cho Frontend

1. **Biến môi trường `.env` tại Frontend:**

```env
VITE_AUTH_API_URL=http://localhost:8001
VITE_ORDER_API_URL=http://localhost:8002
VITE_RECOMMENDER_API_URL=http://localhost:8003
VITE_FAAS_API_URL=http://localhost:7071

```

2. **CORS & Nén dữ liệu:** Tất cả các service đã bật `CORSMiddleware` (`allow_origins=["*"]`) và `GZipMiddleware` (`minimum_size=500`).


3. **Xử lý mã lỗi HTTP tập trung (Axios Interceptor):**
* `401 Unauthorized`: Token hết hạn hoặc tài khoản đã bị vô hiệu hóa (`is_disabled = true`) $\rightarrow$ xóa token và chuyển về trang đăng nhập.


* `403 Forbidden`: Không đủ quyền (truy cập trang Admin bằng tài khoản `customer` hoặc xem đơn của người khác).


* `404 Not Found`: Không tìm thấy `product_id` hoặc `order_id`.


* `409 Conflict`: Trùng username/email, vượt quá tồn kho (`stock_quantity`), hoặc chuyển trạng thái đơn hàng không hợp lệ.

