# TÀI LIỆU ĐẶC TẢ & BÀN GIAO API BACKEND (STEP 2 HANDOFF)

Tài liệu này mô tả chi tiết toàn bộ các Endpoints, Request/Response JSON Schema và cơ chế hoạt động của **Bước 2: Backend Microservices & Azure Function (FaaS)** để thành viên làm **Frontend (Bước 3)** và **DevOps/AKS (Bước 4)** tích hợp trực tiếp.

---

## 1. Tổng quan Cổng dịch vụ (Service Ports)

| Dịch vụ | Thư mục mã nguồn | Port mặc định | Swagger UI (Tài liệu tương tác) | Cơ sở dữ liệu / Lưu trữ |
| :--- | :--- | :---: | :--- | :--- |
| **Auth Service** | `services/auth_service/` | `8001` | `http://localhost:8001/docs` | PostgreSQL (`users`) |
| **Order & Cart Service** | `services/order_service/` | `8002` | `http://localhost:8002/docs` | PostgreSQL (`products`, `cart_items`, `orders`, `order_items`, `reviews`) |
| **Recommender Service** | `services/recommender_service/` | `8003` | `http://localhost:8003/docs` | Azure Cosmos DB NoSQL + Model Artifacts (`item_similarity.npz`, `svd_recommender.pkl`) |
| **Log Interaction (FaaS)** | `azure_functions/LogInteractionFunction/` | `7071` | `http://localhost:7071/docs` | Azure Blob Storage (`interaction-logs`) |

### Lệnh khởi chạy nhanh toàn bộ 4 dịch vụ cùng lúc:
```bash
python scripts/run_backend_services.py
```

### Lệnh chạy kịch bản kiểm thử tự động (Smoke & Concurrency Test):
```bash
python scripts/test_backend_apis.py
```

---

## 2. Chi tiết API của từng Microservice

### 2.1. Auth Service (`http://localhost:8001`)

#### A. Đăng nhập (`POST /api/v1/auth/login`)
* **Tài khoản mẫu có sẵn (từ `03_seed_auth.sql`):**
  * Username: `cuongduong` | Password: `Password123!` (Role: `customer`, ID: `U_TEST_01`)
  * Username: `testuser` | Password: `Password123!` (Role: `customer`, ID: `U_TEST_02`)
  * Username: `admin` | Password: `Password123!` (Role: `admin`, ID: `U_ADMIN_01`)
* **Request Body:**
  ```json
  {
    "username": "cuongduong",
    "password": "Password123!"
  }
  ```
* **Response (`200 OK`):**
  ```json
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

#### B. Đăng ký (`POST /api/v1/auth/register`)
* **Request Body:**
  ```json
  {
    "username": "newuser",
    "email": "newuser@ecommerce.local",
    "password": "Password123!",
    "user_id": "A3V6Z4R53JWSKV"
  }
  ```

#### C. Xác thực Token nội bộ (`GET /api/v1/auth/verify-token`)
* **Headers:** `Authorization: Bearer <access_token>`
* **Response (`200 OK`):**
  ```json
  {
    "valid": true,
    "user_id": "U_TEST_01",
    "username": "cuongduong",
    "email": "cuong@ecommerce.local",
    "role": "customer",
    "message": "Token hợp lệ."
  }
  ```

---

### 2.2. Order, Cart & Product Service (`http://localhost:8002`)

#### A. Danh mục sản phẩm (Không yêu cầu Token)
* `GET /api/v1/products?page=1&page_size=20&category=Guitar&search=Fender&sort_by=price_asc`
* `GET /api/v1/products/categories`: Lấy danh sách danh mục kèm số lượng sản phẩm.
* `GET /api/v1/products/{product_id}`: Lấy chi tiết sản phẩm và `stock_quantity` hiện tại.
* `POST /api/v1/products/batch`: Truyền `{"product_ids": ["B01M4HO6RK", "..."]}` để lấy danh sách chi tiết.

#### B. Giỏ hàng (Yêu cầu Header `Authorization: Bearer <access_token>`)
* `GET /api/v1/cart`: Lấy toàn bộ giỏ hàng và tổng tiền (`total_amount`, `total_quantity`, `items`).
* `POST /api/v1/cart/items`: Thêm vào giỏ hàng:
  ```json
  {
    "product_id": "B01M4HO6RK",
    "quantity": 1
  }
  ```
* `PUT /api/v1/cart/items/{product_id}`: Cập nhật số lượng `{"quantity": 3}` (truyền `0` để xóa).
* `DELETE /api/v1/cart/items/{product_id}`: Xóa 1 sản phẩm khỏi giỏ.
* `DELETE /api/v1/cart`: Xóa sạch giỏ hàng.

#### C. Đặt hàng với Pessimistic Concurrency Lock (`POST /api/v1/orders/checkout`)
* **Cơ chế:** Sử dụng câu lệnh khóa dòng `SELECT ... FOR UPDATE` trong PostgreSQL. Nếu nhiều người cùng bấm mua sản phẩm cuối cùng, chỉ 1 giao dịch thành công, các giao dịch còn lại nhận mã `409 Conflict` (`INSUFFICIENT_STOCK`) và được `ROLLBACK` an toàn.
* **Request Body (Tùy chọn):**
  ```json
  {
    "items": [
      { "product_id": "B01M4HO6RK", "quantity": 1 }
    ],
    "simulate_failure": false
  }
  ```
  *(Nếu bỏ trống `items`, hệ thống tự động thanh toán toàn bộ sản phẩm trong giỏ hàng hiện tại của user. Nếu đặt `simulate_failure: true`, hệ thống giả lập lỗi cổng thanh toán sau khi trừ kho để chứng minh `ROLLBACK` tự động hoàn trả tồn kho).*

---

### 2.3. Recommender Service (`http://localhost:8003`)

#### A. Gợi ý cá nhân hóa cho Trang chủ (`GET /api/v1/recommendations/{user_id}?top_k=10`)
* Truy vấn Point-Read $O(1)$ từ Azure Cosmos DB container `user_recommendations` hoặc ma trận SVD. Nếu `user_id` là khách mới chưa có lịch sử, tự động fallback về `cold_start_popular` (`system_metadata`).
* **Response (`200 OK`):**
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
        "stock_quantity": 100,
        "rating": 4.6,
        "score": 4.88,
        "rank": 1
      }
    ]
  }
  ```

#### B. Sản phẩm thường được mua cùng cho Trang chi tiết (`GET /api/v1/products/{product_id}/frequently-bought-together?top_k=5`)
* Truy vấn từ container `item_recommendations` hoặc ma trận `models/item_similarity.npz`.

---

### 2.4. Azure Function FaaS (`http://localhost:7071`)

#### Ghi nhận hành vi tương tác (`POST /api/LogInteractionFunction`)
* **Request Body:**
  ```json
  {
    "user_id": "U_TEST_01",
    "product_id": "B01M4HO6RK",
    "action": "view",
    "value": null
  }
  ```
  *(Hỗ trợ các `action`: `view` (2.0), `click` (1.0), `add_to_cart` (3.5), `purchase` (5.0), `rating` (1.0 - 5.0)).*
