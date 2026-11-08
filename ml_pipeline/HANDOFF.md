> **LƯU Ý QUAN TRỌNG / DISCLAIMER:**
> Toàn bộ mã nguồn trong thư mục `ml_pipeline/` được thiết kế phục vụ cho quy trình **Tự động hóa tái huấn luyện mô hình (Automated Retraining Pipeline)** khi hệ thống bước vào giai đoạn **vận hành thực tế (Production)**.
> **Hiện tại (Giai đoạn đồ án / Bước 1):** Module này **TẠM THỜI CHƯA TRIỂN KHAI HAY TÍCH HỢP** vào hệ thống đang chạy. Toàn bộ dữ liệu sản phẩm, tương tác và trọng số mô hình phục vụ cho việc kiểm thử, nạp seed ban đầu và dựng prototype đã được xử lý hoàn tất từ file Jupyter Notebook `notebooks/01_ecommerce_recommender_pipeline.ipynb` (chạy trên Google Colab).
> Tài liệu này đóng vai trò bàn giao kỹ thuật (Handoff Document), mô tả chi tiết kiến trúc dữ liệu, luồng vận hành và cách kích hoạt module khi đội ngũ tiến hành tích hợp tự động hóa trong tương lai.

---

# TÀI LIỆU BÀN GIAO KỸ THUẬT: MODULE TỰ ĐỘNG HÓA ML PIPELINE

**Dự án:** Hệ thống Gợi ý Sản phẩm Thương mại Điện tử trên nền tảng Cloud (E-Commerce Recommender System on Azure)

**Thư mục mục tiêu:** `ml_pipeline/`

**Đối tượng bàn giao:** Đội ngũ Backend, Data/ML Engineer, DevOps

---

## 1. Mục tiêu và Vị trí của Module trong Hệ thống

Hệ thống phân tách rành mạch hai giai đoạn xử lý dữ liệu và huấn luyện mô hình:

```
[ GIAI ĐOẠN 1: KHỞI TẠO LẠNH (COLD-START / BOOTSTRAPPING) ]
  • Công cụ: notebooks/01_ecommerce_recommender_pipeline.ipynb (Google Colab / GPU T4)
  • Nguồn dữ liệu: Hugging Face Hub (McAuley-Lab/Amazon-Reviews-2023 - Phân mục Musical Instruments)
  • Nhiệm vụ: Tải streaming, tiền xử lý, kiểm tra link ảnh CDN, lọc K-Core, huấn luyện thử nghiệm, 
              xuất dữ liệu mẫu (clean_products.parquet, seed_products.sql, model weights).
                                    │
                                    ▼ (Seed vào hệ thống)
[ GIAI ĐOẠN 2: VẬN HÀNH THỰC TẾ & TÁI HUẤN LUYỆN TỰ ĐỘNG (PRODUCTION MLOPS) ]
  • Module: ml_pipeline/ (Chạy độc lập trên máy chủ / VM / Docker / K8s CronJob)
  • Nguồn dữ liệu: PostgreSQL (Sản phẩm, Đơn hàng, Đánh giá) + Azure Blob Storage (Interaction logs)
  • Đích đến: Azure Blob Storage (model-artifacts) + Azure Cosmos DB NoSQL (Precomputed Top-K)

```

Module `ml_pipeline/` **không kết nối tới Hugging Face**. Khi hệ thống chạy thật, toàn bộ dữ liệu phản ánh hành vi mua hàng, đánh giá và clickstream thực tế của người dùng từ website thương mại điện tử.

---

## 2. Kiến trúc Luồng Dữ liệu (Data Flow Architecture)

```
                       ┌───────────────────────────────┐
                       │   PostgreSQL (RDS / Azure)    │
                       │   - Table: products           │
                       │   - Table: reviews / orders   │
                       └──────────────┬────────────────┘
                                      │
 ┌─────────────────────────────┐      │ (SQL Query)
 │ Azure Blob Storage          │      │
 │ Container: interaction-logs ├──────┼────────────────────────┐
 └─────────────────────────────┘      ▼                        ▼
                                ┌──────────────┐         ┌──────────────┐
                                │   Products   │         │ Interactions │
                                └──────┬───────┘         └──────┬───────┘
                                       │                        │
                                       ▼                        ▼
                             ┌───────────────────────────────────────────┐
                             │       ml_pipeline/train_recommender       │
                             │                                           │
                             │  • Model 1: Item-Item Cosine Similarity   │
                             │    (TF-IDF Content + Co-occurrence)       │
                             │  • Model 2: Matrix Factorization          │
                             │    (TruncatedSVD trên ma trận User-Item)  │
                             └─────────────────────┬─────────────────────┘
                                                   │
                  ┌────────────────────────────────┴──────────────────────────────┐
                  ▼                                                               ▼
   ┌─────────────────────────────┐                              ┌───────────────────────────────────┐
   │ Azure Blob Storage          │                              │   ml_pipeline/export_to_cosmos    │
   │ Container: model-artifacts  │                              └─────────────────┬─────────────────┘
   │ - item_similarity.npz       │                                                │ (Batch Upsert)
   │ - svd_recommender.pkl       │                                                ▼
   └──────────────┬──────────────┘                              ┌───────────────────────────────────┐
                  │ (Reload)                                    │ Azure Cosmos DB NoSQL             │
                  ▼                                             │                                   │
   ┌─────────────────────────────┐                              │ • Container: user_recommendations │
   │     Recommender Service     │                              │   Top-10 đề xuất cá nhân hóa      │
   │        (Port 8003)          │                              │                                   │
   │                             │◄─────────────────────────────┤ • Container: item_recommendations │
   │  Truy vấn thời gian thực    │                              │   Top-5 combo thường mua cùng     │
   │  cho React Frontend: O(1)   │                              │                                   │
   └─────────────────────────────┘                              │ • Container: system_metadata      │
                                                                │   Top Trending (Cold-start)       │
                                                                └───────────────────────────────────┘

```

---

## 3. Cấu trúc và Trách nhiệm của các Tệp Mã Nguồn

Thư mục `ml_pipeline/` gồm 6 tệp chính, được đóng gói theo dạng module thực thi độc lập:

| STT | Tệp mã nguồn | Trách nhiệm chính |
| --- | --- | --- |
| 1 | `__init__.py` | Định nghĩa package Python, export các class chính (`ETLExtractor`, `RecommenderTrainer`, `CosmosDBExporter`, `run_pipeline`). |
| 2 | `config.py` | Nạp biến môi trường từ `.env`, quản lý chuỗi kết nối (PostgreSQL URI, Azure Blob, Cosmos DB), đường dẫn thư mục và siêu tham số huấn luyện. |
| 3 | `etl_extractor.py` | Truy vấn danh mục sản phẩm từ bảng PostgreSQL `products`; thu thập đánh giá từ bảng `reviews` kết hợp event logs từ Azure Blob Container `interaction-logs`. Xuất bộ dữ liệu sạch sang Parquet. |
| 4 | `train_recommender.py` | Huấn luyện ma trận Item Cosine lai (70% hành vi co-occurrence, 30% TF-IDF nội dung) và TruncatedSVD. Tự động đẩy file nén `.npz` và `.pkl` lên Azure Blob Container `model-artifacts`. |
| 5 | `export_to_cosmos.py` | Tính toán trước (Precompute) Top-10 sản phẩm cho từng User, Top-5 bundle cho từng Item, và Top-10 Trending fallback. Upsert tài liệu JSON trực tiếp vào 3 Container của Azure Cosmos DB. Hỗ trợ cờ `--dry-run` để test JSON cục bộ. |
| 6 | `pipeline_runner.py` | **Single Entrypoint:** Điểm kích hoạt duy nhất kết nối tuần tự cả 3 bước (ETL $\rightarrow$ Train $\rightarrow$ Export Cosmos), xử lý logging và trả mã thoát (exit code) cho hệ thống điều phối lịch trình. |

---

## 4. Đặc tả Dữ liệu Đầu ra trên Azure Cosmos DB NoSQL

Các tài liệu JSON được đẩy vào Cosmos DB phải tuân thủ nghiêm ngặt schema dưới đây để `Recommender Service` (Bước 2 của dự án) có thể bóc tách tức thì:

### A. Container `user_recommendations` (Partition Key: `/user_id`)

Lưu danh sách Top-10 sản phẩm được tính sẵn từ vector tiềm ẩn $P_u \cdot Q^T$, đã loại bỏ các sản phẩm user đã mua/đánh giá:

```json
{
  "id": "A3V6Z4R53JWSKV",
  "user_id": "A3V6Z4R53JWSKV",
  "recommendations": [
    { "product_id": "B0002E1G5C", "score": 4.8812, "rank": 1 },
    { "product_id": "B0002F7K7Y", "score": 4.7504, "rank": 2 }
  ],
  "model_version": "v1.0-svd",
  "updated_at": "2026-11-08T15:30:00Z"
}

```

### B. Container `item_recommendations` (Partition Key: `/product_id`)

Lưu danh sách Top-5 sản phẩm thường được mua cùng phục vụ cho Carousel "Frequently Bought Together" tại trang chi tiết sản phẩm:

```json
{
  "id": "B0002E1G5C",
  "product_id": "B0002E1G5C",
  "frequently_bought_together": [
    { "product_id": "B0002GLDZC", "similarity_score": 0.9415, "bundle_type": "accessory" },
    { "product_id": "B00186AD70", "similarity_score": 0.8720, "bundle_type": "co-purchase" }
  ],
  "updated_at": "2026-11-08T15:30:00Z"
}

```

### C. Container `system_metadata` (Partition Key: `/id`)

Chứa tài liệu duy nhất lưu Top sản phẩm có lượt đánh giá và điểm số cao nhất, dùng làm fallback tức thì khi gặp khách hàng vãng lai chưa đăng nhập:

```json
{
  "id": "popular_items",
  "type": "cold_start_fallback",
  "items": [
    { "product_id": "B0002E1G5C", "name": "Fender Guitar Cable 10ft", "price": 14.99, "rank": 1 }
  ],
  "updated_at": "2026-11-08T15:30:00Z"
}

```

---

## 5. Hướng dẫn Vận hành & Kích hoạt khi Triển khai Thật

Khi hệ sinh thái Microservice hoàn tất và bắt đầu đưa tính năng tái huấn luyện tự động vào hoạt động, thực hiện theo các bước sau:

### Bước 1: Chuẩn bị Môi trường Máy chủ

Đảm bảo máy chủ (hoặc container) đã cài đặt Python 3.10+ và các driver kết nối cần thiết:

```bash
# Kích hoạt môi trường ảo
source .venv/bin/activate  # Trên Linux/macOS
# hoặc .\.venv\Scripts\activate trên Windows

# Cài đặt danh mục thư viện vận hành
pip install sqlalchemy psycopg2-binary azure-storage-blob azure-cosmos scikit-learn pandas numpy scipy python-dotenv pyarrow

```

### Bước 2: Kiểm tra File Cấu hình Môi trường (`.env`)

Đảm bảo các biến sau được điền giá trị thật từ Azure Portal và Database Server:

```ini
# PostgreSQL Kết nối trực tiếp
POSTGRES_HOST="<azure-postgres-host>.postgres.database.azure.com"
POSTGRES_PORT=5432
POSTGRES_DB="ecommerce_shop_db"
POSTGRES_USER="<db_admin>"
POSTGRES_PASSWORD="<db_password>"
POSTGRES_SSL_MODE="require"

# Azure Blob Storage
AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net"
BLOB_CONTAINER_INTERACTION_LOGS="interaction-logs"
BLOB_CONTAINER_MODEL_ARTIFACTS="model-artifacts"

# Azure Cosmos DB NoSQL
COSMOS_DB_ENDPOINT="https://<your-cosmos-account>.documents.azure.com:443/"
COSMOS_DB_PRIMARY_KEY="<primary_master_key>=="
COSMOS_DB_DATABASE_NAME="ecommerce_recommender_db"

```

### Bước 3: Chạy Kiểm thử Cục bộ (Dry-Run Mode)

Chạy thử nghiệm mà không ghi đè dữ liệu lên Cosmos DB trên đám mây để kiểm tra tính toàn vẹn của mô hình:

```bash
# 1. Chạy ETL kiểm tra kết nối PostgreSQL
python -m ml_pipeline.etl_extractor

# 2. Huấn luyện mô hình kiểm tra sinh ma trận
python -m ml_pipeline.train_recommender

# 3. Tính toán trước và xuất file JSON mẫu kiểm tra
python -m ml_pipeline.export_to_cosmos --dry-run

```

Kiểm tra thư mục `exports/` để xem các bản ghi JSON mẫu được sinh ra.

### Bước 4: Chạy Toàn bộ Pipeline Tự động

Để chạy trọn gói từ đầu đến cuối và đồng bộ lên Cloud:

```bash
python -m ml_pipeline.pipeline_runner

```

### Bước 5: Cấu hình Lịch trình Tự động (Automated Scheduling)

* **Phương án 1 (Linux Crontab):** Lên lịch chạy vào lúc 02:00 sáng mỗi Chủ Nhật:
```bash
0 2 * * 0 cd /path/to/E-commerce-Product-Recommendation && .venv/bin/python -m ml_pipeline.pipeline_runner >> /var/log/ml_pipeline.log 2>&1

```


* **Phương án 2 (Kubernetes CronJob / Azure Container Apps Job):** Đóng gói thư mục dự án thành Docker Image và cấu hình CronSchedule định kỳ nạp biến môi trường từ Azure Key Vault.

---

## 6. Các Điểm Cần Lưu ý Kỹ thuật cho Đội ngũ Tiếp quản

1. **Tính toàn vẹn tham chiếu (Foreign Key Alignment):** Module `etl_extractor.py` có hàm kiểm tra ràng buộc nghiêm ngặt: mọi bản ghi tương tác trong bảng `reviews` hoặc log clickstream trỏ tới `product_id` không tồn tại trong bảng `products` sẽ tự động bị loại bỏ để tránh sinh ra dữ liệu mồ côi (dangling recommendations).
2. **Quản lý Thông lượng Cosmos DB (Throughput RU/s):** Trong quá trình batch upsert hàng nghìn tài liệu vào Cosmos DB, nếu gặp lỗi `429 Too Many Requests`, cần tạm thời nâng RU/s của Database lên 1,000 RU/s trong lúc pipeline chạy hoặc bổ sung cơ chế sleep ngắn giữa các batch trong `export_to_cosmos.py`.
3. **Cơ chế Reload Mô hình của Service Gợi ý:** `recommender_service` ở Bước 2 khi khởi động sẽ đọc trực tiếp từ Cosmos DB để phục vụ API. Nếu muốn dịch vụ này nhận biết trọng số SVD mới nhất từ Azure Blob Storage mà không cần khởi động lại container, cần cài đặt một background worker kiểm tra trường `updated_at` trong tệp `models/svd_recommender.pkl` theo chu kỳ 1 giờ một lần.