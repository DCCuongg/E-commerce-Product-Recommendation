# TÀI LIỆU HƯỚNG DẪN CHẠY BACKEND, DATABASE & DANH SÁCH API (BÀN GIAO FRONTEND)

Tài liệu hướng dẫn chi tiết cách khởi chạy hạ tầng Docker (PostgreSQL, Azurite, Azure Cosmos DB Emulator), chạy toàn bộ 4 dịch vụ Backend và đặc tả các REST API để đội ngũ Frontend tích hợp.

---

## 1. Tổng quan Hạ tầng & Cổng dịch vụ (Ports)

### 1.1. Hạ tầng Database & Storage Emulators (Docker)

| Container Name | Dịch vụ | Port | Thông tin kết nối / Ghi chú |
| --- | --- | --- | --- |
| `ecommerce_postgres_dev` | PostgreSQL 16 | `5432` | DB: `ecommerce_shop_db` | User: `postgres_admin` | Pass: `YourSecurePasswordHere123!` |
| `ecommerce_azurite_dev` | Azure Blob Storage Emulator | `10000` | Chứa các container: `raw-data`, `processed-data`, `model-artifacts`, `interaction-logs` |
| `ecommerce_cosmos_dev` | Azure Cosmos DB NoSQL Emulator | `8081` | DB: `ecommerce_recommender_db` (`system_metadata`, `user_recommendations`, `item_recommendations`) |

### 1.2. Các Microservices & FaaS Backend

| Dịch vụ | Mã nguồn | Base URL | Swagger UI (Test trực tiếp) | Chức năng chính |
| --- | --- | --- | --- | --- |
| **Auth Service** | `services/auth_service/` | `http://localhost:8001` | `http://localhost:8001/docs` | Đăng ký, đăng nhập, cấp & xác thực JWT Token |
| **Order & Cart Service** | `services/order_service/` | `http://localhost:8002` | `http://localhost:8002/docs` | Danh mục 1.000 sản phẩm, Giỏ hàng, Đặt hàng (khóa tồn kho), Đánh giá |
| **Recommender Service** | `services/recommender_service/` | `http://localhost:8003` | `http://localhost:8003/docs` | Gợi ý sản phẩm cá nhân hóa (SVD), Cold-Start Trending, Mua kèm (Bundle) |
| **Log Interaction (FaaS)** | `azure_functions/LogInteractionFunction/` | `http://localhost:7071` | `http://localhost:7071/docs` | Ghi nhận hành vi click/xem/thêm giỏ/mua hàng |

---

## 2. Hướng dẫn Khởi chạy Hệ thống Local

### Yêu cầu tiên quyết

* Đã cài đặt **Docker Desktop** (đang mở và chạy ổn định).
* Đã cài đặt **Python 3.11+** và thư mục môi trường ảo `.venv` ở thư mục gốc dự án.

### Bước 1: Mở Terminal tại thư mục gốc dự án & Kích hoạt môi trường ảo (`.venv`)

* **Git Bash (MINGW64):**
```bash
source .venv/Scripts/activate

```


* **PowerShell:**
```powershell
.\.venv\Scripts\Activate.ps1

```


* **Command Prompt (CMD):**
```cmd
.venv\Scripts\activate.bat

```



*(Khi đầu dòng lệnh xuất hiện tiền tố `(.venv)` là thành công).*

### Bước 2: Khởi động các Container Database & Emulator bằng Docker Compose

```bash
docker compose up -d

```

* Kiểm tra các container đã lên đầy đủ:
```bash
docker ps

```


*(Đảm bảo thấy đủ 3 container: `ecommerce_postgres_dev`, `ecommerce_azurite_dev`, `ecommerce_cosmos_dev`).*

### Bước 3: Khởi tạo Schema & Nạp dữ liệu mẫu (Chạy 1 lần đầu hoặc khi reset DB)

```bash
python scripts/init_local_dev.py

```

Lệnh này tự động thực hiện 4 tác vụ:

1. Đồng bộ 3 file dataset chuẩn từ Hugging Face (`cuongduongok/amazon-musical-instruments-clean`).
2. Tạo các container Blob trên Azurite và đẩy dữ liệu parquet lên `processed-data`.
3. Tạo database `ecommerce_recommender_db` và nạp dữ liệu Cold-Start vào Cosmos DB Emulator.
4. Chạy các file SQL trong `scripts/sql/` để tạo bảng và nạp sẵn **1.000 sản phẩm nhạc cụ** cùng **3 tài khoản mẫu** vào PostgreSQL.

### Bước 4: Khởi chạy toàn bộ 4 dịch vụ Backend

```bash
python scripts/run_backend_services.py

```

Khi màn hình hiển thị cả 4 cổng `8001`, `8002`, `8003`, `7071` đang chạy (`Uvicorn running on [http://0.0.0.0](http://0.0.0.0):...`), hệ thống đã sẵn sàng nhận request từ Frontend.

* Để dừng toàn bộ Backend: nhấn `Ctrl + C` tại cửa sổ Terminal.
* Để dừng Docker khi nghỉ làm việc (vẫn giữ nguyên dữ liệu): `docker compose down`.

### Bước 5: Kiểm tra nhanh toàn bộ API (Tùy chọn)

Mở một tab Terminal mới (đã kích hoạt `.venv`) và chạy:

```bash
python scripts/test_backend_apis.py

```

---

## 3. Cơ chế Xác thực & Tài khoản Demo có sẵn

### 3.1. Tài khoản mẫu đã nạp sẵn trong Database

| Username | Email | Password | User ID | Role | Ghi chú |
| --- | --- | --- | --- | --- | --- |
| `cuongduong` | `cuong@ecommerce.local` | `Password123!` | `U_TEST_01` | `customer` | Khách hàng mẫu 1 |
| `testuser` | `testuser@ecommerce.local` | `Password123!` | `U_TEST_02` | `customer` | Khách hàng mẫu 2 |
| `admin` | `admin@ecommerce.local` | `Password123!` | `U_ADMIN_01` | `admin` | Quản trị viên |

### 3.2. Cách truyền Token từ Frontend

Với các API yêu cầu đăng nhập (Giỏ hàng, Đặt hàng, Gửi đánh giá, Xem thông tin cá nhân), Frontend đính kèm Header:

```http
Authorization: Bearer <access_token>

```

*(Ngoài ra, Order Service có hỗ trợ truyền nhanh header `X-User-Id: U_TEST_01` để test nhanh luồng không cần JWT nếu cần).*

---

## 4. Danh sách Chi tiết API theo Từng Microservice

### 4.1. Auth Service (`http://localhost:8001`)

| Method | Endpoint | Auth | Mô tả |
| --- | --- | --- | --- |
| `GET` | `/health` | Không | Kiểm tra trạng thái service và kết nối PostgreSQL |
| `POST` | `/api/v1/auth/register` | Không | Đăng ký tài khoản mới và nhận `access_token` |
| `POST` | `/api/v1/auth/login` | Không | Đăng nhập bằng `username` hoặc `email` |
| `GET` / `POST` | `/api/v1/auth/verify-token` | Bearer | Xác thực tính hợp lệ của JWT Token |
| `GET` | `/api/v1/auth/me` | Bearer | Lấy thông tin chi tiết user đang đăng nhập |
| `GET` | `/api/v1/auth/users` | Không | Lấy danh sách user trong hệ thống (`?limit=20`) phục vụ chuyển đổi user nhanh khi demo |

**Chi tiết Request / Response tiêu biểu:**

* **`POST /api/v1/auth/login`**
```json
// Request Body
{
  "username": "cuongduong",
  "password": "Password123!"
}

// Response 200 OK
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "id": "U_TEST_01",
    "username": "cuongduong",
    "email": "cuong@ecommerce.local",
    "role": "customer"
  }
}

```


* **`POST /api/v1/auth/register`**
```json
// Request Body (user_id là tùy chọn, bỏ trống hệ thống tự sinh U_XXXXXXXXXX)
{
  "username": "khachhang01",
  "email": "khachhang01@gmail.com",
  "password": "Password123!",
  "user_id": "A3V6Z4R53JWSKV"
}

```



---

### 4.2. Order, Cart & Product Service (`http://localhost:8002`)

#### A. Danh mục Sản phẩm (Public)

| Method | Endpoint | Mô tả & Query Parameters |
| --- | --- | --- |
| `GET` | `/health` | Kiểm tra trạng thái service và tổng số sản phẩm trong DB |
| `GET` | `/api/v1/products` | Danh sách sản phẩm phân trang: |



• `page` (int, mặc định `1`)



• `page_size` (int, `1–100`, mặc định `20`)



• `category` (string, lọc theo danh mục)



• `search` (string, tìm theo tên, mô tả, danh mục hoặc mã SP)



• `sort_by` (`default` | `price_asc` | `price_desc` | `name_asc`) |
| `GET` | `/api/v1/products/categories` | Lấy danh sách toàn bộ danh mục kèm số lượng sản phẩm từng mục |
| `POST` | `/api/v1/products/batch` | Lấy chi tiết nhiều sản phẩm theo danh sách ID (giữ nguyên thứ tự truyền vào).



Body: `{"product_ids": ["B01M4HO6RK", "B0002E1G5C"]}` |
| `GET` | `/api/v1/products/{product_id}` | Chi tiết 1 sản phẩm, số lượng tồn kho (`stock_quantity`), điểm đánh giá trung bình |

#### B. Quản lý Giỏ hàng (Yêu cầu Bearer Token)

| Method | Endpoint | Mô tả & Body |
| --- | --- | --- |
| `GET` | `/api/v1/cart` | Lấy toàn bộ sản phẩm trong giỏ, `total_items`, `total_quantity`, `total_amount` |
| `POST` | `/api/v1/cart/items` | Thêm sản phẩm vào giỏ (tự cộng dồn nếu đã có, kiểm tra tồn kho). |



Body: `{"product_id": "B01M4HO6RK", "quantity": 1}` |
| `PUT` | `/api/v1/cart/items/{product_id}` | Cập nhật số lượng sản phẩm trong giỏ (truyền `0` để xóa mặt hàng).



Body: `{"quantity": 3}` |
| `DELETE` | `/api/v1/cart/items/{product_id}` | Xóa 1 sản phẩm khỏi giỏ hàng |
| `DELETE` | `/api/v1/cart` | Xóa sạch toàn bộ giỏ hàng của người dùng |

#### C. Đặt hàng & Thanh toán (Yêu cầu Bearer Token)

| Method | Endpoint | Mô tả & Body |
| --- | --- | --- |
| `POST` | `/api/v1/orders/checkout` *(hoặc `/api/v1/orders`)* | Tạo đơn hàng & trừ tồn kho bằng khóa bi quan `SELECT ... FOR UPDATE`. |



• Nếu bỏ trống body hoặc `items: null`: tự động thanh toán toàn bộ giỏ hàng hiện tại.



• Nếu truyền `items`: đặt mua trực tiếp danh sách sản phẩm đó. |
| `GET` | `/api/v1/orders` | Lấy danh sách lịch sử đơn hàng của người dùng hiện tại (sắp xếp mới nhất trước) |
| `GET` | `/api/v1/orders/{order_id}` | Xem chi tiết 1 đơn hàng cụ thể (chỉ chủ đơn hoặc `admin` được xem) |

**Payload mẫu cho `POST /api/v1/orders/checkout`:**

```json
// Đặt trực tiếp sản phẩm (hoặc gửi {} để checkout toàn bộ giỏ hàng)
{
  "items": [
    { "product_id": "B01M4HO6RK", "quantity": 1 }
  ],
  "simulate_failure": false
}

```

> **Lưu ý xử lý lỗi ở FE:** Nếu sản phẩm hết hàng hoặc có 2 người cùng mua món cuối cùng cùng lúc, API trả về mã **`409 Conflict`**. FE cần bắt lỗi `409` và hiển thị thông báo hết hàng / cập nhật lại tồn kho.

#### D. Đánh giá Sản phẩm (Reviews)

| Method | Endpoint | Auth | Mô tả & Body |
| --- | --- | --- | --- |
| `GET` | `/api/v1/products/{product_id}/reviews` | Không | Lấy danh sách đánh giá của sản phẩm (`?limit=20`) |
| `POST` | `/api/v1/products/{product_id}/reviews` | Bearer | Gửi đánh giá mới. |



Body: `{"rating": 5, "title": "Rất tốt", "comment": "Âm thanh chuẩn"}` |

---

### 4.3. Recommender Service (`http://localhost:8003`)

| Method | Endpoint | Mô tả & Query Parameters |
| --- | --- | --- |
| `GET` | `/health` | Kiểm tra trạng thái model, `deployment_slot` (`blue`/`green`), `model_version` |
| `GET` | `/api/v1/recommendations/{user_id}` | Lấy Top-K gợi ý cá nhân hóa cho Trang chủ (`?top_k=10`). Tự động fallback về danh sách thịnh hành (`cold_start_popular`) nếu `user_id` là khách mới |
| `GET` | `/api/v1/recommendations/popular/trending` | Lấy Top-K sản phẩm thịnh hành cho khách vãng lai chưa đăng nhập (`?top_k=10`) |
| `GET` | `/api/v1/products/{product_id}/frequently-bought-together` | Lấy Top-K sản phẩm thường được mua cùng (`?top_k=5`) hiển thị ở Trang chi tiết sản phẩm *(Alias: `/api/v1/recommendations/item/{product_id}`)* |
| `POST` | `/api/v1/recommendations/reload` | Nạp lại model artifacts và xóa cache bộ nhớ đệm |

**Response mẫu (`GET /api/v1/recommendations/{user_id}?top_k=10`):**

```json
{
  "user_id": "U_TEST_01",
  "strategy": "svd_personalized",
  "data_source": "cosmos_db",
  "model_version": "v1.0-svd",
  "deployment_slot": "blue",
  "latency_ms": 2.45,
  "count": 10,
  "recommendations": [
    {
      "product_id": "B01M4HO6RK",
      "name": "Pearl Export Lacquer EXL725S...",
      "category": "Drum Sets",
      "price": 32.34,
      "thumbnail_url": "https://m.media-amazon.com/images/...",
      "image_url": "https://m.media-amazon.com/images/...",
      "stock_quantity": 100,
      "rating": 4.6,
      "rating_count": 25,
      "score": 4.88,
      "rank": 1,
      "recommendation_type": "personalized"
    }
  ]
}

```

---

### 4.4. Azure Function FaaS (`http://localhost:7071`)

| Method | Endpoint | Auth | Mô tả |
| --- | --- | --- | --- |
| `POST` | `/api/LogInteractionFunction` | Không | Ghi nhận sự kiện tương tác của người dùng để phục vụ huấn luyện lại mô hình |

**Request Body:**

```json
{
  "user_id": "U_TEST_01",
  "product_id": "B01M4HO6RK",
  "action": "view",
  "value": null
}

```

* **Các giá trị `action` hợp lệ:**
* `"click"` (trọng số 1.0)
* `"view"` (trọng số 2.0 — gọi khi user mở trang chi tiết sản phẩm)
* `"add_to_cart"` (trọng số 3.5 — gọi khi user thêm vào giỏ)
* `"purchase"` (trọng số 5.0 — gọi khi thanh toán thành công)
* `"rating"` (truyền kèm `"value"` từ `1.0` đến `5.0`)



---

## 5. Lưu ý Tích hợp dành cho Frontend

1. **Cấu hình biến môi trường (`.env` ở Frontend):**
Nên tách riêng 4 biến Base URL để dễ dàng chuyển đổi giữa môi trường Local và Azure AKS sau này:
```env
VITE_AUTH_API_URL=http://localhost:8001
VITE_ORDER_API_URL=http://localhost:8002
VITE_RECOMMENDER_API_URL=http://localhost:8003
VITE_FAAS_API_URL=http://localhost:7071

```


2. **CORS & Nén dữ liệu:** Tất cả các service Backend đã bật sẵn `CORSMiddleware` (`allow_origins=["*"]`) và `GZipMiddleware` (tự động nén phản hồi JSON lớn hơn 500 bytes), Frontend có thể gọi trực tiếp bằng `fetch` hoặc `axios` mà không gặp lỗi CORS.
3. **Các mã lỗi HTTP cần xử lý tập trung trên Axios Interceptor:**
* `401 Unauthorized`: Token hết hạn hoặc chưa đăng nhập $\rightarrow$ xóa token và điều hướng về trang đăng nhập.
* `403 Forbidden`: Truy cập đơn hàng của người dùng khác.
* `404 Not Found`: Sai `product_id` hoặc `order_id`.
* `409 Conflict`: Trùng username/email khi đăng ký, hoặc số lượng đặt mua vượt quá `stock_quantity` hiện có trong kho.