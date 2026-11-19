# Hướng Dẫn Bàn Giao & Vận Hành Hệ Thống (HANDOFF.md)

Tài liệu này hướng dẫn chi tiết quy trình thiết lập môi trường phát triển cục bộ, vận hành ML Pipeline, chạy kiểm thử hiệu năng (Benchmark) và triển khai Cloud Blue/Green trên Azure Kubernetes Service (AKS) cho dự án **E-commerce-Product-Recommendation**.

---

## 1. Tổng quan trạng thái bàn giao (5 Giai đoạn)

| Giai đoạn | Thành phần | Trạng thái | Ghi chú kỹ thuật |
| :--- | :--- | :---: | :--- |
| **Bước 1: Data & ML Pipeline** | `ml_pipeline/`, `models/`, `notebooks/` | Hoàn tất | ETL hợp nhất PostgreSQL (`reviews`, `order_items`) + Azure Blob (`interaction-logs`), huấn luyện Hybrid Cosine Similarity & TruncatedSVD, xuất Top-10/Top-5 lên Cosmos DB. |
| **Bước 2: Backend & FaaS** | `services/*`, `azure_functions/` | Hoàn tất | 3 Microservices FastAPI (8001, 8002, 8003) + FaaS HTTP Trigger (7071). Đã sửa cờ `--factory` trong `run_backend_services.py` và bổ sung `local.settings.json`. |
| **Bước 3: Frontend SPA** | `frontend/` | Đang tích hợp | Giao diện React + Vite + Tailwind + Zustand (4 màn hình nghiệp vụ). |
| **Bước 4: Docker, K8s & CI/CD** | `k8s/`, `.github/workflows/`, `docker-compose.yml` | Hoàn tất | 8 manifest Kubernetes Blue/Green (giới hạn RAM chuẩn node `Standard_B2s`) + GitHub Actions tách bạch CI tự động và CD bấm tay (`workflow_dispatch`). |
| **Bước 5: Benchmark & Nghiệm thu** | `scripts/latency_benchmark.py` | Hoàn tất | Script đo 100 requests ($P_{50}, P_{90}, P_{99}$, RPS) cho Network & Storage Latency, tự động xuất JSON và biểu đồ PNG vào `exports/`. |

---

## 2. Yêu cầu tiên quyết & Cổng mạng (Prerequisites & Ports)

### Công cụ cần cài đặt
- **Git** (khuyến nghị Git Bash trên Windows).
- **Python**: Phiên bản `3.10` hoặc `3.11`.
- **Docker Desktop**: Bật Linux Containers, cấp tối thiểu `4GB RAM` trong Settings.
- **Azure CLI (`az`) & `kubectl`** *(chỉ cần khi thao tác triển khai trực tiếp lên cụm AKS ở Mục 8)*.

### Danh sách cổng mạng (Ports) sử dụng
- **Tầng lưu trữ (Infrastructure):** `5432` (PostgreSQL), `10000` (Azurite Blob Storage), `8081` (Azure Cosmos DB Emulator).
- **Tầng ứng dụng (Microservices & FaaS):** `8001` (Auth Service), `8002` (Order/Cart Service), `8003` (Recommender Service), `7071` (FaaS Event Collector), `3000` (Frontend Nginx khi chạy Compose).

---

## 3. Khởi tạo môi trường Python & Cấu hình `.env`

### 3.1 Tạo môi trường ảo và cài thư viện
Mở terminal tại thư mục gốc `E-commerce-Product-Recommendation/`:

```bash
# 1. Tạo và kích hoạt môi trường ảo .venv
python -m venv .venv
source .venv/Scripts/activate        # Windows (Git Bash)
# .venv\Scripts\Activate.ps1         # Windows (PowerShell)
# source .venv/bin/activate          # macOS / Linux

# 2. Cài đặt toàn bộ dependencies (bao gồm matplotlib để vẽ biểu đồ benchmark)
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install matplotlib
```

### 3.2 Cấu hình biến môi trường (`.env`)
Sao chép file mẫu và cập nhật giá trị cho môi trường Local Dev:

```bash
cp .env.example .env
```

Nội dung chuẩn cho file `.env` cục bộ:

```ini
# ==============================================================================
# LOCAL DEVELOPMENT CONFIGURATION (.env)
# ==============================================================================

# 1. AZURE BLOB STORAGE (Azurite Well-known Emulator Credentials)
AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=[http://127.0.0.1:10000/devstoreaccount1](http://127.0.0.1:10000/devstoreaccount1);"
AZURE_STORAGE_ACCOUNT_NAME="devstoreaccount1"
AZURE_STORAGE_ACCOUNT_KEY="Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="

BLOB_CONTAINER_RAW_DATA="raw-data"
BLOB_CONTAINER_PROCESSED_DATA="processed-data"
BLOB_CONTAINER_MODEL_ARTIFACTS="model-artifacts"
BLOB_CONTAINER_INTERACTION_LOGS="interaction-logs"

# 2. AZURE COSMOS DB (Linux vnext-preview Emulator dùng HTTP cổng 8081)
COSMOS_DB_ENDPOINT="http://localhost:8081/"
COSMOS_DB_PRIMARY_KEY="C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="
COSMOS_DB_DATABASE_NAME="ecommerce_recommender_db"
COSMOS_CONTAINER_USER_RECS="user_recommendations"
COSMOS_CONTAINER_ITEM_RECS="item_recommendations"
COSMOS_CONTAINER_METADATA="system_metadata"
COSMOS_DATABASE_THROUGHPUT=400
COSMOS_SSL_VERIFY="false"

# 3. POSTGRESQL (Docker Container)
POSTGRES_HOST="localhost"
POSTGRES_PORT=5432
POSTGRES_DB="ecommerce_shop_db"
POSTGRES_USER="postgres_admin"
POSTGRES_PASSWORD="YourSecurePasswordHere123!"
POSTGRES_SSL_MODE="disable"

# 4. AUTHENTICATION & MODEL VERSIONING
JWT_SECRET_KEY="ecommerce-recommender-super-secret-jwt-key-2026"
JWT_ALGORITHM="HS256"
MODEL_VERSION="v1.0-svd"

# 5. HUGGING FACE REPOSITORIES
HF_DATASET_REPO="cuongduongok/amazon-musical-instruments-clean"
HF_MODEL_REPO="cuongduongok/amazon-musical-recommender-models"
```

---

## 4. Khởi chạy hạ tầng & Dữ liệu mẫu (Local Dev)

### Cách A: Khởi chạy hạ tầng bằng Docker + Chạy Python Services trực tiếp (Khuyên dùng khi dev)

1. **Bật 3 container lưu trữ (`postgres`, `azurite`, `cosmos-emulator`):**
   ```bash
   docker compose up -d postgres azurite cosmos-emulator
   ```
   *(Chờ khoảng 15–30 giây để `cosmos-emulator` khởi động hoàn tất).*

2. **Nạp dữ liệu mẫu & đồng bộ Model Artifacts:**
   ```bash
   # Bước 1: Tải dataset từ HF, tạo containers trên Azurite/Cosmos và chạy SQL seed Postgres
   python scripts/init_local_dev.py

   # Bước 2: Tải model artifacts (item_similarity.npz, svd_recommender.pkl) về thư mục models/
   python scripts/sync_models_to_dev.py

   # Bước 3: Kiểm tra trạng thái kết nối toàn bộ hạ tầng
   python scripts/verify_dev_env.py
   ```

3. **Khởi chạy đồng thời 3 Backend Microservices & FaaS:**
   ```bash
   python scripts/run_backend_services.py
   ```
   Script tự động dọn file rác `data/test_backend.db` (nếu có), kiểm tra đủ file trong `models/` và mở 4 tiến trình:
   - Auth Service: `http://localhost:8001/docs`
   - Order Service: `http://localhost:8002/docs`
   - Recommender Service: `http://localhost:8003/docs`
   - FaaS Event Collector: `http://localhost:7071/api/LogInteractionFunction`

### Cách B: Chạy toàn bộ Full-Stack bằng 1 lệnh Docker Compose
Nếu muốn đóng gói và chạy cả backend lẫn frontend trong Docker:

```bash
docker compose up -d --build
```

---

## 5. Vận hành & Huấn luyện lại ML Pipeline (`ml_pipeline/`)

Khi hệ thống phát sinh đánh giá mới trong PostgreSQL (`reviews`), đơn hàng mới (`orders`) hoặc log hành vi từ người dùng trên Azure Blob Storage (`interaction-logs`), chạy lệnh sau để cập nhật mô hình và đẩy kết quả gợi ý mới lên Cosmos DB:

```bash
# Chạy đầy đủ 3 bước: ETL -> Train SVD/Hybrid -> Upload Blob -> Export Cosmos DB
python -m ml_pipeline.pipeline_runner --model-version v1.0-svd

# Hoặc chạy chế độ Dry-run (chỉ xuất file JSON kiểm tra vào exports/, không ghi Cosmos DB)
python -m ml_pipeline.pipeline_runner --dry-run --model-version v2.0-svd
```

**Quy tắc xử lý dữ liệu bên trong `ml_pipeline`:**
- **Trọng số hành vi (Implicit Feedback):** `view = 1.0`, `click = 2.0`, `add_to_cart = 3.5`, `checkout = 4.5`, `purchase / rating = 5.0`.
- **Khử trùng tương tác:** Gộp nhóm theo cặp `(user_id, product_id)` và giữ mức điểm cao nhất (`max(rating)`).
- **Lọc độ thưa ma trận:** Loại bỏ người dùng có `< 3` tương tác và sản phẩm có `< 2` tương tác trước khi phân rã `TruncatedSVD`.

---

## 6. Kiểm thử API, Concurrency & Đo độ trễ (Benchmark)

### 6.1 Kiểm thử chức năng Backend APIs
```bash
python scripts/test_backend_apis.py
```

### 6.2 Kiểm thử khóa đồng bộ `SELECT ... FOR UPDATE` (Chống Overselling)
Gửi đồng thời 5 request đặt cùng 1 sản phẩm chỉ còn tồn kho = 1 (kết quả chuẩn: chỉ 1 request trả về `HTTP 201`, 4 request còn lại trả về `HTTP 409 Conflict`):

```bash
seq 1 5 | xargs -I{} -P5 curl -s -o /dev/null -w "Req {}: HTTP %{http_code}\n" \
  -X POST http://localhost:8002/api/v1/orders/checkout \
  -H "Content-Type: application/json" \
  -H "X-User-Id: U_TEST_{}" \
  -d '{"items":[{"product_id":"<ID_SAN_PHAM_TON_KHO_1>","quantity":1}]}'
```

### 6.3 Chạy kịch bản Benchmark 100 Requests ($P_{50}, P_{90}, P_{99}$)
```bash
# Đo trên môi trường Local
python scripts/latency_benchmark.py \
  --sea-url "http://localhost:8003/api/v1/recommendations/popular/trending" \
  --requests 100 --concurrency 10

# Hoặc so sánh trực tiếp 2 Region trên Azure (Southeast Asia vs East US)
python scripts/latency_benchmark.py \
  --sea-url "http://<INGRESS_IP_SEA>/api/v1/recommendations/popular/trending" \
  --eastus-url "http://<INGRESS_IP_EASTUS>/api/v1/recommendations/popular/trending" \
  --requests 100 --concurrency 10
```
Kết quả chi tiết được lưu tại `exports/latency_benchmark_results.json` và ảnh biểu đồ cột tại `exports/latency_benchmark_chart.png`.

---

## 7. Quy trình CI/CD trên GitHub Actions (`.github/workflows/`)

Hệ thống CI/CD được thiết kế tách biệt 2 giai đoạn để bảo vệ tín dụng Azure for Students:

1. **CI (Tự động chạy khi `git push` hoặc `pull_request` lên `main`):**
   - Kiểm tra cú pháp Python (`compileall`), thử import toàn bộ 3 ứng dụng FastAPI, chạy `pytest` (nếu có) và build thử Docker image (`push: false`).
   - Build thử React/Vite (`npm run build`).
   - Không yêu cầu Azure Secrets, không đụng chạm hạ tầng Cloud.
2. **CD (Chỉ chạy thủ công bằng tay khi bấm nút `Run workflow`):**
   - Vào GitHub Repository $\rightarrow$ tab **Actions** $\rightarrow$ chọn **CI/CD Backend Microservices** $\rightarrow$ bấm **Run workflow**.
   - Chọn `target_slot` (`blue` hoặc `green`) và `switch_traffic` (`true` hoặc `false`).

### Danh sách GitHub Secrets cần khai báo trước khi chạy CD
- `CONTAINER_REGISTRY`: Địa chỉ Azure Container Registry (vd: `myacr.azurecr.io`) hoặc `docker.io`.
- `REGISTRY_USERNAME` & `REGISTRY_PASSWORD`: Tài khoản đăng nhập Registry.
- `AZURE_CREDENTIALS`: JSON Service Principal xuất từ lệnh `az ad sp create-for-rbac --sdk-auth`.
- `AKS_RESOURCE_GROUP` & `AKS_CLUSTER_NAME`: Tên Resource Group và cụm AKS.

---

## 8. Triển khai & Chuyển đổi Blue/Green trên Azure AKS (`k8s/`)

### 8.1 Áp dụng Manifest lên cụm AKS
```bash
# Cập nhật thông tin kết nối thật trong k8s/configmap-secrets.yaml trước khi chạy
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap-secrets.yaml
envsubst < k8s/auth-service-deploy.yaml | kubectl apply -f -
envsubst < k8s/order-service-deploy.yaml | kubectl apply -f -
envsubst < k8s/recommender-blue.yaml | kubectl apply -f -
envsubst < k8s/recommender-green.yaml | kubectl apply -f -
kubectl apply -f k8s/recommender-service.yaml
kubectl apply -f k8s/ingress.yaml
```

### 8.2 Chuyển đổi lưu lượng Zero-downtime giữa Blue và Green
```bash
# Kiểm tra slot đang phục vụ hiện tại
curl -s http://<INGRESS_IP>/api/v1/recommendations/popular/trending | grep -E "deployment_slot|model_version"

# Chuyển toàn bộ traffic sang Green (v2.0-svd) không gián đoạn dịch vụ
kubectl patch service recommender-service -n ecommerce-rec \
  -p '{"spec":{"selector":{"app":"recommender","version":"green"}}}'

# Rollback về Blue (v1.0-svd) nếu cần
kubectl patch service recommender-service -n ecommerce-rec \
  -p '{"spec":{"selector":{"app":"recommender","version":"blue"}}}'
```

---

## 9. Xử lý sự cố thường gặp (Troubleshooting)

| Vấn đề | Nguyên nhân | Hướng xử lý |
| :--- | :--- | :--- |
| **`Connection refused` trên cổng `5432`** | PostgreSQL container chưa sẵn sàng hoặc trùng với PostgreSQL cài sẵn trên Windows. | Kiểm tra bằng `netstat -ano \| findstr 5432`. Tắt dịch vụ Postgres của Windows hoặc đổi port mapping thành `5433:5432`. |
| **Lỗi kết nối Cosmos DB Emulator (`http` vs `https`)** | Image `azure-cosmos-emulator:vnext-preview` chạy giao thức `http://localhost:8081/` mặc định. | Đặt `COSMOS_DB_ENDPOINT="http://localhost:8081/"` và `COSMOS_SSL_VERIFY="false"` trong `.env`. |
| **Thiếu `models/svd_recommender.pkl` khi chạy Recommender** | File `.pkl` được loại trừ khỏi Git nên chưa có sẵn sau khi clone repo. | Chạy `python scripts/sync_models_to_dev.py` hoặc `python -m ml_pipeline.pipeline_runner --dry-run`. |
| **Xuất hiện file rác `data/test_backend.db`** | Sinh ra khi chạy test lúc PostgreSQL chưa bật. | Chạy `python scripts/run_backend_services.py` (tự động xóa) hoặc `git rm -f data/test_backend.db`. |
| **Pod trên AKS bị `OOMKilled`** | Node `Standard_B2s` chỉ có 4GB RAM; chạy quá nhiều pod không giới hạn bộ nhớ. | Giữ nguyên cấu hình `resources.limits.memory` (`384Mi–512Mi`) đã thiết lập trong các file `k8s/*-deploy.yaml`. |

---

## 10. Lệnh tắt và Dọn dẹp tài nguyên

```bash
# Dừng containers cục bộ (giữ nguyên dữ liệu)
docker compose down

# Dừng containers và xóa sạch toàn bộ volume dữ liệu để dựng lại từ đầu
docker compose down -v

# Tắt cụm AKS trên Azure khi không demo để tiết kiệm 100$ credit sinh viên
az aks stop --resource-group <AKS_RESOURCE_GROUP> --name <AKS_CLUSTER_NAME>
```