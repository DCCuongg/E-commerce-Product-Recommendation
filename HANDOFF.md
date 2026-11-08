# Hướng Dẫn Thiết Lập Môi Trường Phát Triển Cục Bộ (HANDOFF.md)

Tài liệu này hướng dẫn chi tiết quy trình dựng toàn bộ hạ tầng phát triển từ con số 0 dành cho thành viên mới tham gia dự án **E-commerce-Product-Recommendation**.

---

## 1. Yêu cầu tiên quyết (Prerequisites)

Đảm bảo máy trạm đã cài đặt các công cụ sau trước khi bắt đầu:

* **Git** (khuyến nghị dùng Git Bash trên Windows).
* **Python**: Phiên bản 3.10 hoặc 3.11.
* **Docker Desktop**: Đã bật chế độ Linux Containers và cấp tối thiểu 4GB RAM trong Settings.
* **Cổng mạng (Ports) khả dụng**: `5432` (PostgreSQL), `10000` (Azurite), `8081` (Cosmos Emulator).

---

## 2. Khởi tạo môi trường ảo Python & Cài đặt thư viện

Mở terminal (Git Bash hoặc PowerShell) tại thư mục gốc của dự án:

```bash
# 1. Tạo môi trường ảo .venv
python -m venv .venv

# 2. Kích hoạt môi trường ảo
# Trên Windows (Git Bash):
source .venv/Scripts/activate
# Trên Windows (PowerShell):
# .venv\Scripts\Activate.ps1
# Trên macOS / Linux:
# source .venv/bin/activate

# 3. Nâng cấp pip và cài đặt dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

```

Nếu trong quá trình dev thiếu một số gói thao tác với Azure SDK và Hugging Face, hãy chạy lệnh cài đặt bổ sung:

```bash
pip install azure-storage-blob azure-cosmos huggingface_hub pandas pyarrow psycopg2-binary python-dotenv

```

---

## 3. Cấu hình biến môi trường (`.env`)

Sao chép cấu hình mẫu và tạo file `.env` tại thư mục gốc dự án:

```bash
cp .env.example .env

```

Mở tệp `.env` vừa tạo và cập nhật các tham số dành riêng cho môi trường Local Dev:

```ini
# ==============================================================================
# LOCAL DEVELOPMENT CONFIGURATION (.env)
# ==============================================================================
# Nguồn gốc cụ thể của từng key:

# AZURE_STORAGE_ACCOUNT_KEY (Eby8vdM02...): Đây là chuỗi khóa mặc định công khai (Well-known Key) do Microsoft ấn định cho trình giả lập cục bộ Azurite (Azure Storage Emulator). Mọi lập trình viên chạy Azurite trên Docker đều dùng chung chuỗi key cố định này.

# COSMOS_DB_PRIMARY_KEY (C2y6yDjf...): Đây là Master Key mặc định công khai của Microsoft dành riêng cho bản Docker Linux Azure Cosmos DB Emulator (cổng 8081).

# POSTGRES_PASSWORD (YourSecurePasswordHere123!): Lấy nguyên văn từ file mẫu .env.example bạn gửi trong prompt.

# 1. AZURE BLOB STORAGE (Azurite Emulator)
AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
AZURE_STORAGE_ACCOUNT_NAME="devstoreaccount1"
AZURE_STORAGE_ACCOUNT_KEY="Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="

BLOB_CONTAINER_RAW_DATA="raw-data"
BLOB_CONTAINER_PROCESSED_DATA="processed-data"
BLOB_CONTAINER_MODEL_ARTIFACTS="model-artifacts"
BLOB_CONTAINER_INTERACTION_LOGS="interaction-logs"

# 2. AZURE COSMOS DB (Local Emulator)
COSMOS_DB_ENDPOINT="https://localhost:8081/"
COSMOS_DB_PRIMARY_KEY="C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="
COSMOS_DB_DATABASE_NAME="ecommerce_recommender_db"
COSMOS_CONTAINER_USER_RECS="user_recommendations"
COSMOS_CONTAINER_ITEM_RECS="item_recommendations"
COSMOS_CONTAINER_METADATA="system_metadata"
COSMOS_DATABASE_THROUGHPUT=400

# 3. POSTGRESQL (Docker Container)
POSTGRES_HOST="localhost"
POSTGRES_PORT=5432
POSTGRES_DB="ecommerce_shop_db"
POSTGRES_USER="postgres_admin"
POSTGRES_PASSWORD="YourSecurePasswordHere123!"
POSTGRES_SSL_MODE="disable"

# 4. HUGGING FACE REPOSITORIES
HF_DATASET_REPO="cuongduongok/amazon-musical-instruments-clean"
HF_MODEL_REPO="cuongduongok/amazon-musical-recommender-models"

```

---

## 4. Khởi chạy hạ tầng với Docker Compose

Khởi động toàn bộ 3 dịch vụ: PostgreSQL, Azurite Blob Storage, và Cosmos DB NoSQL Emulator ở chế độ chạy nền (background):

```bash
docker compose up -d

```

Kiểm tra trạng thái sẵn sàng của các container:

```bash
docker compose ps

```

*Lưu ý:* Riêng dịch vụ `cosmos-emulator` cần khoảng **15 - 30 giây** để hoàn tất việc khởi động runtime và chứng chỉ TLS giả lập. Hãy đảm bảo cột `STATUS` hiển thị `Up` hoặc `healthy` trước khi thực thi các bước tiếp theo.

---

## 5. Đồng bộ Dữ liệu & Khởi tạo Môi trường Dev

Thực thi 2 kịch bản tự động hóa theo thứ tự:

```bash
# Bước 5.1: Tải Dataset từ Hugging Face, khởi tạo Blob Containers và Cosmos DB Schemas
python scripts/init_local_dev.py

# Bước 5.2: Tải Model Artifacts từ HF, nạp vào Azurite và tạo Item Recommendations
python scripts/sync_models_to_dev.py

```

---

## 6. Kiểm thử và Xác minh Hạ tầng (Smoke Test)

Chạy file script kiểm tra toàn diện để xác thực việc đọc/ghi trên cả 3 dịch vụ hạ tầng cục bộ. Tạo file `scripts/verify_dev_env.py` và chạy:

Kích hoạt file test:

```bash
python scripts/verify_dev_env.py

```

**Kết quả kỳ vọng (Expected Output):**

```text
--- [1/3] Kiểm tra PostgreSQL ---
  [PASS] Kết nối thành công!
  [DATA] Tổng sản phẩm: 1000
  [SAMPLE] SP: ID=B01M4HO6RK | Tên=Pearl Export Lacquer EXL725S... | Giá=32.34 | Kho=100

--- [2/3] Kiểm tra Azurite (Blob Storage) ---
  [PASS] Kết nối thành công!
  [CONTAINERS] Danh sách: ['interaction-logs', 'model-artifacts', 'processed-data', 'raw-data']
  [ARTIFACTS] Model files đã nạp: ['item_similarity.npz', 'svd_recommender.pkl']

--- [3/3] Kiểm tra Azure Cosmos DB NoSQL ---
  [PASS] Kết nối thành công!
  [METADATA] Cold-start fallback items: 10 IDs
  [RECOMMENDER] Đã đọc gợi ý mua kèm cho SP: B01M4HO6RK
  [RECOMMENDER] Top 1 bundle: {'bundle_type': 'content_match', 'product_id': '...', 'similarity_score': 0.58}

```

---

## 7. Xử lý sự cố thường gặp (Troubleshooting)

| Vấn đề | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| **`Connection refused` trên cổng 5432** | PostgreSQL chưa sẵn sàng hoặc cổng 5432 bị chiếm bởi PostgreSQL cục bộ trên Windows. | Kiểm tra tiến trình: `netstat -ano | findstr 5432`. Nếu có dịch vụ Postgres của máy đang chạy, hãy tạm dừng (Stop Service) hoặc map lại port trong compose thành `5433:5432`. |
| **`SSLError: [SSL: CERTIFICATE_VERIFY_FAILED]` khi gọi Cosmos DB** | Cosmos DB Emulator dùng self-signed certificate cho cổng HTTPS cục bộ. | Đảm bảo khởi tạo client với cờ `connection_verify=False` trong Python: `CosmosClient(..., connection_verify=False)`. |
| **Bảng `products` trong PostgreSQL rỗng (0 dòng)** | Docker volume `postgres_data` đã được khởi tạo từ trước khi mount file SQL mới. | Reset lại volume bằng lệnh: `docker compose down -v` sau đó chạy lại `docker compose up -d`. |
| **Cosmos DB báo lỗi `RequestRateTooLarge` (429)** | Throughput vượt quá hạn mức cấu hình. | File script đã tự động thiết lập Database Shared Throughput = 400 RU/s cho toàn bộ 3 containers để tránh vượt trần. |

---

## 8. Lệnh tắt và Dọn dẹp môi trường

Khi kết thúc phiên làm việc:

```bash
# Tạm dừng containers nhưng giữ nguyên dữ liệu đã nạp
docker compose down

# Xóa toàn bộ dữ liệu database để dựng lại từ đầu (nếu cần reset)
docker compose down -v

```