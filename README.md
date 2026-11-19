# E-commerce-Product-Recommendation

Đồ án môn học: **Điện toán đám mây (IS402)**

## 👨‍🏫 Giảng viên hướng dẫn
- **Giảng viên:** Thầy Hà Lê Hoài Trung
- **GitHub:** [@TrungHa-DL](https://github.com/TrungHa-DL)

---

## 👥 Danh sách thành viên nhóm

| STT | Họ và tên | MSSV | GitHub Username | Vai trò |
| :---: | :--- | :---: | :--- | :---: |
| 1 | Dương Chí Cường | 23520195 | [@DCCuongg](https://github.com/DCCuongg) | Thành viên |
| 2 | Cao Nguyễn Kỳ Dỵ | 23520403 | [@DWY4X](https://github.com/DWY4X) | Thành viên |
| 3 | Huỳnh Quang Minh Quân | 23521253 | [@QuanHuynh1005](https://github.com/QuanHuynh1005) | Thành viên |
| 4 | Đặng Nguyễn Hoàng Thạch | 23521411 | [@EvogasBaron](https://github.com/EvogasBaron) | Thành viên |

---

## Kiến trúc tổng thể hệ thống

Hệ thống được thiết kế theo mô hình **Microservices** kết hợp **kiến trúc Lambda / Cloud-Native** phục vụ bài toán gợi ý sản phẩm thương mại điện tử:

```text
[ Client Browser (React + Vite) ]
          │
          ├──> [ NGINX Ingress Controller (AKS) ]
          │         │
          │         ├──> [ Auth Service (FastAPI) - Port 8001 ] ──────────┐
          │         ├──> [ Order/Cart Service (FastAPI) - Port 8002 ] ────┼──> [ Azure PostgreSQL (ACID / FOR UPDATE) ]
          │         └──> [ Recommender API (FastAPI) - Port 8003 ] ───────┼──> [ Azure Cosmos DB (Precomputed Top-K) ]
          │                   (Blue v1.0-svd / Green v2.0-svd)            │
          │                                                               │
          └──> [ Event Collector (Azure Function - FaaS, Port 7071) ]     │
                    │ (Ghi log hành vi click/view/cart bất đồng bộ)       │
                    ▼                                                     │
          [ Azure Blob Storage (Raw Data Lake & Model Artifacts) ]        │
                    │                                                     │
                    └──────────────────────────┬──────────────────────────┘
                                               ▼ (Batch ETL & Retraining)
                                 [ ML Pipeline (TF-IDF + TruncatedSVD) ]
                                               │
                                               ├──> [ Blob: item_similarity.npz & svd_recommender.pkl ]
                                               └──> [ Cosmos DB: user_recommendations & item_recommendations ]
```

---

## Cấu hình hạ tầng trên gói Azure for Students

Gói Azure for Students cung cấp **100 USD credit** kèm các dịch vụ miễn phí 12 tháng. Cấu hình hệ thống được tối ưu ngân sách như sau:

| Thành phần | Dịch vụ đề xuất | Cấu hình tối ưu ngân sách | Chính sách chi phí & Hạn mức Free |
| --- | --- | --- | --- |
| **Database NoSQL** | Azure Cosmos DB | API for NoSQL, Provisioned Throughput 400–1000 RU/s | **Bật chế độ Free Tier Discount** (miễn phí 1000 RU/s và 25 GB dung lượng trọn đời). |
| **Database Relational (Auth/Cart)** | Azure Database for PostgreSQL (Flexible Server) | Burstable `Standard_B1ms` (1 vCPU, 2GB RAM, 32GB Storage) | Nằm trong gói miễn phí 12 tháng của Azure Student. |
| **Object Storage** | Azure Blob Storage | Hot Tier, Locally Redundant Storage (LRS) | 5GB LRS Block Blob miễn phí 12 tháng. Lưu dataset, interaction logs và model artifacts. |
| **Microservices & Model Serving** | Azure Kubernetes Service (AKS) | 1 System Node Pool: `Standard_B2s` (2 vCPU, 4GB RAM, Linux) | Master Node miễn phí; giới hạn RAM từng Pod (`384Mi–512Mi`) chống OOM; tắt node khi không demo. |
| **FaaS (Hàm phi máy chủ)** | Azure Functions | Consumption Plan (Linux, Python 3.11) | Miễn phí 1,000,000 requests/tháng và 400,000 GB-s/tháng. |
| **Training Pipeline** | Local Machine / Google Colab (T4 GPU) | Export model artifacts lên Blob & Cosmos DB | Không tốn credit Azure; giả lập đúng luồng Data Science VM. |

---

## Kiến trúc thư mục dự án (Monorepo)

```bash
E-commerce-Product-Recommendation/
├── .github/
│   └── workflows/                                  # Quy trình tự động hóa CI/CD trên GitHub Actions
│       ├── deploy-frontend.yml                     # CI kiểm tra build React/Vite & CD đóng gói Docker Frontend thủ công
│       └── deploy-k8s.yml                          # CI test Python/Docker & CD triển khai Blue/Green lên Azure AKS thủ công
├── azure_functions/                                # Tầng FaaS (Serverless) thu thập sự kiện tương tác người dùng
│   ├── LogInteractionFunction/
│   │   ├── __init__.py                             # Handler HTTP Trigger nhận log click/view/rating đẩy lên Blob Storage
│   │   └── function.json                           # Khai báo binding HTTP Trigger (route, methods, authLevel) cho Azure Functions
│   ├── Dockerfile                                  # Đóng gói Multi-stage FaaS chạy độc lập qua Uvicorn (Port 7071)
│   ├── host.json                                   # Cấu hình runtime toàn cục cho Azure Functions Host v4
│   ├── local.settings.json                         # Cấu hình biến môi trường cục bộ cho Azure Functions Core Tools (gitignored)
│   └── requirements.txt                            # Thư viện Python riêng của FaaS (azure-functions, azure-storage-blob, fastapi)
├── data/                                           # Thư mục lưu dữ liệu cục bộ (parquets đã ETL từ Hugging Face / Postgres)
├── frontend/                                       # [Bước 3 - Đang hoàn thiện] Giao diện Web SPA (React + Vite + Tailwind)
├── k8s/                                            # Bộ Manifest triển khai cụm Kubernetes trên Azure AKS (Namespace: ecommerce-rec)
│   ├── namespace.yaml                              # Khởi tạo không gian tên cô lập 'ecommerce-rec' cho toàn bộ dự án
│   ├── configmap-secrets.yaml                      # Quản lý biến môi trường cấu hình (ConfigMap) & chuỗi kết nối mật (Secret)
│   ├── auth-service-deploy.yaml                    # Deployment & ClusterIP Service cho Auth Service (Port 8001, giới hạn RAM)
│   ├── order-service-deploy.yaml                   # Deployment & ClusterIP Service cho Order Service (Port 8002, giới hạn RAM)
│   ├── recommender-blue.yaml                       # Deployment slot Blue (MODEL_VERSION=v1.0-svd) phục vụ traffic chính
│   ├── recommender-green.yaml                      # Deployment slot Green (MODEL_VERSION=v2.0-svd) chờ chuyển đổi Zero-downtime
│   ├── recommender-service.yaml                    # Router Service điều hướng traffic giữa Blue và Green qua label selector
│   └── ingress.yaml                                # NGINX Ingress định tuyến API (/auth, /recommendations, /products, /cart, /orders)
├── ml_pipeline/                                    # Luồng xử lý dữ liệu & huấn luyện mô hình gợi ý (Batch / Lambda Layer)
│   ├── __init__.py                                 # Khởi tạo Python package ml_pipeline
│   ├── config.py                                   # Nạp .env, quản lý URI PostgreSQL, Blob, Cosmos DB & siêu tham số SVD/Hybrid
│   ├── etl_extractor.py                            # Trích xuất & hợp nhất dữ liệu từ PostgreSQL (reviews, orders) + Blob logs
│   ├── train_recommender.py                        # Huấn luyện Item-to-Item Cosine Similarity & TruncatedSVD, sync lên Blob
│   ├── export_to_cosmos.py                         # Tiền tính toán Top-10 User Recs, Top-5 Bundles, Trending & upsert vào Cosmos DB
│   └── pipeline_runner.py                          # Entrypoint điều phối tự động 3 bước: ETL -> Train -> Export Cosmos DB
├── models/                                         # Lưu trữ trọng số mô hình đã huấn luyện để đóng gói vào Recommender Image
│   ├── item_similarity.npz                         # Ma trận nén tương đồng sản phẩm Hybrid (TF-IDF + Co-occurrence)
│   └── svd_recommender.pkl                         # Trọng số phân rã ma trận TruncatedSVD (sinh qua sync_models / pipeline_runner)
├── notebooks/                                      # Môi trường thử nghiệm & huấn luyện trên Google Colab / Jupyter
│   ├── 01_ecommerce_recommender_pipeline.ipynb     # Notebook EDA dữ liệu Amazon Reviews 2023, đánh giá & huấn luyện model
│   └── 01_ecommerce_recommender_pipeline.py        # Bản xuất script Python tương ứng từ Notebook để dễ diff trên Git
├── scripts/                                        # Bộ công cụ tự động hóa khởi tạo, kiểm thử & đo kiểm hiệu năng
│   ├── sql/                                        # Các script SQL khởi tạo lược đồ và dữ liệu mẫu PostgreSQL
│   │   ├── 01_init_auth_db.sql                     # Tạo bảng 'users' và index phục vụ xác thực/phân quyền
│   │   ├── 02_init_order_db.sql                    # Tạo các bảng 'products', 'cart_items', 'orders', 'order_items' & ràng buộc
│   │   ├── 03_seed_auth.sql                        # Nạp tài khoản mẫu (customer/admin) phục vụ đăng nhập & demo
│   │   └── seed_products.sql                       # Nạp danh mục sản phẩm nhạc cụ & tồn kho ban đầu
│   ├── init_local_dev.py                           # Đồng bộ dataset từ Hugging Face, khởi tạo Azurite, Cosmos Emulator & Postgres
│   ├── latency_benchmark.py                        # Kịch bản bắn 100 requests đo P50/P90/P99 Network Latency & Storage Latency
│   ├── run_backend_services.py                     # Khởi chạy đồng thời 3 Microservices (8001-8003) & FaaS (7071) ở local
│   ├── sync_models_to_dev.py                       # Tải model artifacts (svd_recommender.pkl, item_similarity.npz) về thư mục models/
│   ├── test_backend_apis.py                        # Kiểm thử tự động luồng API: Auth, Cart, Checkout khóa tồn kho & Recommender
│   └── verify_dev_env.py                           # Kiểm tra trạng thái kết nối tới PostgreSQL, Azurite và Cosmos DB Emulator
├── services/                                       # Kiến trúc 3 Backend Microservices độc lập (FastAPI)
│   ├── auth_service/                               # Microservice 1: Quản lý tài khoản, JWT & phân quyền (Port 8001)
│   │   ├── __init__.py                             # Khởi tạo package auth_service
│   │   ├── auth_handler.py                         # Xử lý mã hóa mật khẩu (bcrypt) và ký/giải mã JWT Token
│   │   ├── Dockerfile                              # Đóng gói Multi-stage image nhẹ cho Auth Service (Port 8001)
│   │   ├── main.py                                 # Định nghĩa REST API (/register, /login, /verify-token, /me) & GZip
│   │   ├── models.py                               # ORM SQLAlchemy bảng 'users' & Pydantic schemas request/response
│   │   └── requirements.txt                        # Thư viện riêng của Auth Service (fastapi, sqlalchemy, pyjwt, passlib)
│   ├── order_service/                              # Microservice 2: Danh mục, Giỏ hàng, Đặt hàng & Khóa tồn kho (Port 8002)
│   │   ├── __init__.py                             # Khởi tạo package order_service
│   │   ├── Dockerfile                              # Đóng gói Multi-stage image nhẹ cho Order Service (Port 8002)
│   │   ├── inventory_lock.py                       # Xử lý giao dịch Checkout với Pessimistic Lock (SELECT ... FOR UPDATE)
│   │   ├── main.py                                 # REST API sản phẩm, giỏ hàng, đặt hàng & gọi xác thực nội bộ sang Auth Service
│   │   ├── models.py                               # ORM SQLAlchemy (Product, CartItem, Order, OrderItem, Review) & schemas
│   │   └── requirements.txt                        # Thư viện riêng của Order Service (fastapi, httpx, sqlalchemy, psycopg2)
│   └── recommender_service/                        # Microservice 3: Model Serving API độ trễ thấp (Port 8003 - Blue/Green)
│       ├── __init__.py                             # Khởi tạo package recommender_service
│       ├── cosmos_client.py                        # Truy vấn O(1) từ Cosmos DB kết hợp fallback SVD/Similarity trên RAM
│       ├── Dockerfile                              # Đóng gói Multi-stage image kèm thư mục models/ phục vụ chạy trên AKS
│       ├── main.py                                 # REST API gợi ý cá nhân hóa (/recommendations/{user_id}) & mua kèm (bundles)
│       └── requirements.txt                        # Thư viện riêng của Recommender Service (azure-cosmos, numpy, scipy)
├── .env.example                                    # File mẫu khai báo toàn bộ biến môi trường (Azure Keys, Postgres, JWT)
├── .gitignore                                      # Loại trừ file nhạy cảm (.env), môi trường ảo (.venv) & cache khỏi Git
├── docker-compose.yml                              # Dựng toàn bộ stack local bằng 1 lệnh (Postgres, Azurite, Cosmos, Services)
├── README.md                                       # Tài liệu tổng quan kiến trúc, cấu hình Azure Students & hướng dẫn cài đặt
└── requirements.txt                                # Danh sách thư viện Python tổng hợp cho môi trường phát triển cục bộ
```

---

## Giải trình chi tiết theo bảng Rubric đánh giá

### Tiêu chí 1: Giới thiệu bài toán (1.5 điểm)

1. **Phân loại bài toán (0.25đ):**
   - *Thu thập (Data Ingestion):* Ghi nhận hành vi tương tác thực tế từ client (view, click, add-to-cart, star rating) thông qua Azure Function ghi log bất đồng bộ vào Azure Blob Storage.
   - *Lưu trữ (Storage):* Lưu trữ dữ liệu phi cấu trúc/bán cấu trúc (logs, JSONL raw, model artifacts) trên Azure Blob Storage; lưu trữ bảng tra cứu kết quả gợi ý tiền tính toán (Precomputed Top-K) trên Azure Cosmos DB; lưu trữ dữ liệu giao dịch ACID trên PostgreSQL.
   - *Xử lý (Data Processing & Training):* Xử lý luồng ETL hợp nhất PostgreSQL + Blob logs, lọc ma trận thưa (Sparse Matrix), huấn luyện mô hình Collaborative Filtering & Content-Based.
   - *Trực quan (Visualization/Serving):* Hiển thị danh mục sản phẩm và các dải đề xuất theo thời gian thực trên Web Frontend.

2. **Loại dữ liệu (0.25đ):**
   - *Web Data:* Tương tác người dùng dạng JSON payloads gửi từ giao diện SPA.
   - *Database:* Dữ liệu quan hệ (Người dùng, Sản phẩm, Đơn hàng, Tồn kho) và Dữ liệu Document NoSQL (Precomputed User/Item Recommendations).
   - *Data Analyst / Dataset:* Dữ liệu lịch sử mua sắm và đánh giá từ tập `Amazon-Reviews-2023` (`Musical_Instruments`).

3. **Kích thước dữ liệu và dung lượng bộ nhớ (>4GB) - So sánh Cloud vs On-premise (0.75đ):**
   - *Kích thước dữ liệu:* Tập dữ liệu gốc Amazon Reviews 2023 có kích thước vượt mức 4GB (hàng chục GB toàn bộ danh mục). Khi đưa vào pipeline, dữ liệu thô dạng JSONL > 4.2 GB được xử lý phân tán theo batch và nén sang định dạng cột Parquet.
   - *So sánh hiệu năng xử lý:*

| Tiêu chí | Máy chủ truyền thống (On-premise / Local PC) | Hệ thống Cloud (Azure Data Lake + Virtual VM/Databricks) |
| --- | --- | --- |
| **Tốc độ đọc/ghi (I/O)** | Phụ thuộc tốc độ SSD cục bộ (500MB/s - 2GB/s). Giới hạn bởi băng thông bus nội bộ. | Tốc độ truyền tải mở rộng tự động theo IOPS phân tán của Storage Account (hỗ trợ tới hàng chục Gbps). |
| **Giới hạn bộ nhớ (RAM/Out-Of-Memory)** | Cố định (ví dụ 8GB - 16GB). Khi nạp tập dữ liệu >4GB để tính ma trận tương tác $U \times I$, nguy cơ tràn RAM (OOM) rất cao. | Dễ dàng scale-up cấu hình RAM (32GB - 128GB) hoặc scale-out theo cụm Spark (Databricks) phân tán bộ nhớ trên RAM nhiều worker node. |
| **Thời gian huấn luyện mô hình** | Lâu (chạy tuần tự trên CPU), không tận dụng được GPU chuyên dụng nếu phần cứng không hỗ trợ. | Tăng tốc qua VM/Colab có GPU (T4/NC-series) hoặc tối ưu hóa vectorization trên Spark cluster. |

4. **Phân loại thành phần Cloud (0.25đ):**
   - **IaaS (Infrastructure as a Service):** Azure Virtual Machines (Worker Node VM cho cụm AKS).
   - **PaaS (Platform as a Service):** Azure Cosmos DB, Azure Database for PostgreSQL Flexible Server, Azure Kubernetes Service (Managed Control Plane).
   - **FaaS (Function as a Service):** Azure Functions (`LogInteractionFunction` chạy tác vụ ghi log không máy chủ).
   - **SaaS (Software as a Service):** GitHub Actions (CI/CD) & Azure Monitor / Application Insights.

---

### Tiêu chí 2: Cơ sở lý thuyết (1.5 điểm)

1. **Cơ sở lý thuyết về định dạng lưu trữ (0.5đ):**
   - *Web - Visualize:* JSON (JavaScript Object Notation) - chuẩn dữ liệu nhẹ, tương thích trực tiếp với React State và FastAPI REST API.
   - *Database:*
     - PostgreSQL: Relational Tables (chuẩn hóa 3NF) đảm bảo tính toàn vẹn ACID cho giao dịch thanh toán và khóa tồn kho.
     - Azure Cosmos DB: JSON Document Store với Partition Key `/id`, hỗ trợ truy vấn điểm $O(1)$ cho danh sách gợi ý `recommendations: [{product_id, score, rank}]`.
   - *Train Model:* Lưu trữ ma trận thưa dưới định dạng Scipy CSR Matrix (Compressed Sparse Row) để tiết kiệm 95% bộ nhớ; xuất trọng số mô hình dưới dạng ma trận nén `.npz` (`item_similarity.npz`) và `.pkl` (`svd_recommender.pkl`).
   - *Storage Cloud (Azure Blob):* Dạng Block Blob lưu trữ log dạng JSONL (`interaction-logs`), dữ liệu sạch dạng Parquet (`processed-data`) và trọng số mô hình (`model-artifacts`).

2. **Cơ sở lý thuyết về thuật toán xử lý & Luồng dữ liệu (0.5đ):**
   - *Thuật toán Gợi ý 1 - Hybrid Item-to-Item Similarity (TF-IDF Content + Co-occurrence):*
     - Áp dụng cho khối "Sản phẩm thường được mua cùng" trên trang chi tiết sản phẩm.
     - Kết hợp độ tương đồng nội dung TF-IDF và độ tương đồng đồng xuất hiện hành vi theo hệ số trộn $\alpha = 0.7$:

$$\text{Cosine Similarity}(u, v) = \frac{\mathbf{u} \cdot \mathbf{v}}{\Vert{}\mathbf{u}\Vert{}_2 \Vert{}\mathbf{v}\Vert{}_2}$$

   - *Thuật toán Gợi ý 2 - Matrix Factorization (Truncated SVD):*
     - Phân rã ma trận tương tác User - Item $R_{m \times n}$ thành hai ma trận bậc thấp đại diện cho vector ẩn của người dùng $P_{m \times k}$ và sản phẩm $Q_{n \times k}$ sao cho:

$$\hat{R} \approx P \times Q^T$$

     - Với người dùng mới (Cold-start): Tự động fallback về Top-10 sản phẩm thịnh hành nhất (`system_metadata/popular_items`).

   - *Luồng dữ liệu (Data Pipeline Flow):*
     `Client Browser` $\rightarrow$ Thao tác Click/Đánh giá $\rightarrow$ `Azure Function` $\rightarrow$ Ghi log vào `Blob Storage` $\rightarrow$ Chạy `ml_pipeline` (hợp nhất PostgreSQL + Blob logs) $\rightarrow$ Train mô hình $\rightarrow$ Lưu kết quả Top-K vào `Cosmos DB` $\rightarrow$ `Recommender Service` truy vấn theo $O(1)$ $\rightarrow$ `Frontend`.

3. **Chi tiết các dịch vụ Azure sử dụng (0.5đ):**
   - **Azure Blob Storage:** Chứa dữ liệu gốc/đã xử lý, log luồng tương tác thực tế từ web và file trọng số mô hình.
   - **Data Science VM / Local & Colab Runtime:** Cài đặt sẵn PySpark, Scikit-Learn, Scipy để chạy pipeline ETL và huấn luyện.
   - **Azure Cosmos DB:** Đóng vai trò Data Serving Layer lưu trữ `user_recommendations`, `item_recommendations`, `system_metadata` với độ trễ phản hồi < 10ms.
   - **Azure Kubernetes Service (AKS):** Nền tảng điều phối container chứa 3 microservices (Auth, Order, Recommender), hỗ trợ Blue/Green Deployment.
   - **Azure Functions:** Hàm phi máy chủ tiếp nhận HTTP POST event từ web để giải phóng tải cho Backend chính.

---

### Tiêu chí 3: Mô hình dữ liệu & Tối ưu hiệu năng (2.0 điểm)

1. **Tốc độ cho phép đọc ghi (0.5đ):**
   - *Azure Cosmos DB:* Cung cấp cam kết SLA đọc < 10ms và ghi < 10ms với phân vùng hợp lý (Partition Key: `/id`). Thông lượng cấu hình 400–1000 RU/s đáp ứng hàng trăm lượt đọc đồng thời.
   - *Azure Blob Storage:* Hỗ trợ thông lượng đọc tuần tự lên đến 60 MB/s trên mỗi blob, đáp ứng tốt cho tác vụ nạp dữ liệu huấn luyện hàng loạt.

2. **Thiết lập luồng xử lý dữ liệu tự động ETL (0.5đ):**
   - *Bước 1 (Extract):* Web Client gửi sự kiện tương tác $\rightarrow$ Azure Function ghi bản ghi JSON vào Blob Storage (`interaction-logs`) theo định dạng:
     `{"user_id": "U101", "product_id": "B001", "action": "click", "timestamp": 1731000000}`
   - *Bước 2 (Transform - `ml_pipeline/etl_extractor.py`):*
     - Hợp nhất đánh giá sao từ bảng `reviews`, lịch sử mua từ `orders/order_items` và clickstream logs từ Blob Storage.
     - Quy đổi trọng số hành vi: `view = 1.0`, `click = 2.0`, `add_to_cart = 3.5`, `purchase / rating = 5.0`; gộp trùng cặp `(user_id, product_id)` lấy mức tương tác cao nhất.
     - Lọc bỏ người dùng có dưới 3 lượt tương tác và sản phẩm có dưới 2 lượt tương tác để giải quyết độ thưa ma trận.
   - *Bước 3 (Load - `ml_pipeline/export_to_cosmos.py`):* Tính toán và upsert **Top-10** sản phẩm gợi ý cho từng người dùng, **Top-5** sản phẩm mua kèm và **Top-10** sản phẩm thịnh hành vào Cosmos DB.

3. **Phương pháp đo độ trễ (Latency Delay) khi thiết lập Server ở các Region khác nhau (0.5đ):**
   - *Bản chất phép đo:* Thực hiện kiểm thử ở cả **2 cấp độ** qua `scripts/latency_benchmark.py`:
     1. **Network Latency (Mạng giữa các Region):** Triển khai API tại 2 Region `Southeast Asia` (Singapore) và `East US` (Mỹ), gửi 100 requests đồng thời để đo thời gian kết nối TCP/TLS và TTFB, tính toán các phân vị $P_{50}, P_{90}, P_{99}$ và thông lượng RPS.
     2. **Storage Latency (Truy xuất lưu trữ):** Đo trực tiếp độ trễ đọc điểm $O(1)$ trên Azure Cosmos DB và ghi/đọc trên Azure Blob Storage.

4. **Giải pháp tối ưu hóa lưu trữ và tốc độ đọc ghi (0.5đ):**
   - **In-memory Application Caching:** `RecommenderCosmosClient` lưu đệm kết quả gợi ý ngay trên RAM của Pod, giảm đáng kể số lượt truy vấn RU/s vào Cosmos DB.
   - **Connection Pooling:** Duy trì HTTP/TCP connection pool tái sử dụng tới PostgreSQL (SQLAlchemy pool) và Cosmos DB thay vì tạo kết nối mới ở mỗi request.
   - **Partition Key Optimization:** Sử dụng Partition Key `/id` đồng đều cho từng `user_id` và `product_id` trong Cosmos DB để tránh "Hot Partition".
   - **Data Compression:** Nén payload JSON trả về từ cả 3 FastAPI microservices bằng `GZipMiddleware` (`minimum_size=500`).

---

### Tiêu chí 4: Hiện thực hệ thống Web & Nghiệp vụ (3.0 điểm)

1. **Deploy trang web lên Cloud - Đủ 4 trang nghiệp vụ (1.0đ):**
   - *Lựa chọn Frontend:* **React.js (Vite) + TypeScript + Tailwind CSS**, đóng gói tĩnh phục vụ qua Nginx (~25MB RAM).
   - *Chi tiết 4 màn hình:*
     - **Trang 1 - Trang chủ (Home Page):** Hiển thị danh mục sản phẩm, thanh tìm kiếm và khối Carousel "Gợi ý dành riêng cho bạn" gọi từ Recommender API.
     - **Trang 2 - Trang chi tiết sản phẩm (Product Detail Page):** Mô tả sản phẩm, giá, số sao, form đánh giá rating/review, kèm khối "Sản phẩm thường được mua cùng".
     - **Trang 3 - Modal thêm vào giỏ hàng (Add to Cart Modal):** Chọn số lượng, kiểm tra nhanh tồn kho, cập nhật giỏ hàng tức thời.
     - **Trang 4 - Danh sách giỏ hàng & Thanh toán (Cart Page):** Liệt kê mặt hàng, điều chỉnh số lượng, tính tổng tiền, nút "Đặt hàng" (Checkout).

2. **Triển khai hệ thống Blue/Green Deployment (0.5đ):**
   - Tạo 2 Kubernetes Deployment riêng biệt trên AKS (`namespace: ecommerce-rec`): `recommender-deployment-blue` (`MODEL_VERSION=v1.0-svd`) và `recommender-deployment-green` (`MODEL_VERSION=v2.0-svd`).
   - Sử dụng Kubernetes Service `k8s/recommender-service.yaml` làm Router:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: recommender-service
  namespace: ecommerce-rec
spec:
  selector:
    app: recommender
    version: blue   # Chuyển sang Green tức thì bằng lệnh: kubectl patch svc recommender-service ...
  ports:
    - name: http
      port: 8003
      targetPort: 8003
```
   - Khi cập nhật mô hình mới: Triển khai pod Green $\rightarrow$ Kiểm tra `/health` Readiness Probe sẵn sàng $\rightarrow$ Cập nhật label selector của Service sang `green` $\rightarrow$ Chuyển dịch lưu lượng Zero-downtime.

3. **Triển khai Microservices độc lập và giao tiếp nội bộ (1.0đ):**
   - **Auth Service (Port 8001):** Đăng ký, đăng nhập, băm mật khẩu (bcrypt), cấp phát và xác thực JWT Token.
   - **Order/Cart Service (Port 8002):** Quản lý danh mục sản phẩm, giỏ hàng và đặt hàng. Khi nhận request cần xác thực, `Order Service` gọi HTTP nội bộ sang `http://auth-service:8001/api/v1/auth/verify-token` để xác minh danh tính người dùng trước khi trừ kho.
   - **Recommender Service (Port 8003):** Phục vụ gợi ý cá nhân hóa và sản phẩm mua kèm.

4. **Xử lý bài toán Concurrency, Khóa đồng bộ và Rollback chống vi phạm:**
   - Áp dụng **Pessimistic Concurrency Control (Khóa bi quan)** trong `services/order_service/inventory_lock.py`:
```sql
BEGIN;
SELECT stock_quantity FROM products WHERE id = :product_id FOR UPDATE;
-- Kiểm tra: Nếu stock_quantity < requested_quantity => ROLLBACK và trả về HTTP 409 Conflict
UPDATE products SET stock_quantity = stock_quantity - :requested_quantity WHERE id = :product_id;
INSERT INTO orders (user_id, total_amount, status) VALUES (...);
COMMIT;
```
   - Nếu có bất kỳ lỗi nào phát sinh giữa giao dịch, khối `try/except` tự động gọi `db.rollback()`, hoàn trả nguyên vẹn tồn kho và đảm bảo tính chất ACID.

5. **Sử dụng FaaS (Azure Function) (0.5đ):**
   - Hàm HTTP Trigger Python (`azure_functions/LogInteractionFunction`) tiếp nhận các sự kiện xem/click/đánh giá từ frontend và đẩy bất đồng bộ vào container `interaction-logs` của Azure Blob Storage.

6. **Tối ưu độ mượt giao diện Web (Frontend Smoothness):**
   - **Optimistic UI Updates:** Cập nhật ngay badge số lượng giỏ hàng trên UI trước khi server phản hồi; rollback nếu server báo hết hàng.
   - **Skeleton Loading & Debounced Event Logging:** Hiển thị khung xương shimmer khi tải API gợi ý và debounce 300ms các sự kiện gửi về FaaS.

---

## Trích xuất & Trừu tượng hóa dữ liệu Amazon Reviews 2023

Tập dữ liệu `McAuley-Lab/Amazon-Reviews-2023` (`Musical_Instruments`) được ánh xạ vào hệ thống:
- **Metadata:** `parent_asin` $\rightarrow$ `product_id`, `title` $\rightarrow$ `name`, `price` $\rightarrow$ `price`, `images` $\rightarrow$ `image_url`, `categories` $\rightarrow$ `category`.
- **Reviews & Interactions:** `user_id`, `parent_asin` $\rightarrow$ `product_id`, `rating` (1–5 sao), `timestamp`.
- **Co-purchase Bundles:** Tính ma trận đồng xuất hiện từ các sản phẩm được cùng nhóm người dùng tương tác/mua chung kết hợp TF-IDF.

---

## Tiến độ triển khai theo lộ trình 5 bước

- [x] **Bước 1: Pipeline Dữ liệu & Mô hình học máy (`ml_pipeline/`, `notebooks/`, `models/`)**
  - Hoàn thiện `config.py`, `etl_extractor.py` (hợp nhất PostgreSQL + Blob logs), `train_recommender.py`, `export_to_cosmos.py`, `pipeline_runner.py`.
- [x] **Bước 2: Backend Microservices & FaaS (`services/`, `azure_functions/`)**
  - Hoàn thiện `auth_service` (8001), `order_service` (8002 - Pessimistic Lock), `recommender_service` (8003 - Blue/Green), `LogInteractionFunction` (7071) và script kiểm thử `scripts/test_backend_apis.py`.
- [ ] **Bước 3: Giao diện Web Client (`frontend/`)**
  - Xây dựng 4 màn hình React + Vite + Tailwind + Zustand.
- [x] **Bước 4: Đóng gói Container, Kubernetes AKS & CI/CD (`k8s/`, `.github/workflows/`, `docker-compose.yml`)**
  - Hoàn thiện Multi-stage `Dockerfile` cho từng service, 8 manifest Kubernetes Blue/Green trong `k8s/` và quy trình GitHub Actions tách bạch (CI tự động kiểm tra code/build khi push, CD bấm nút thủ công `workflow_dispatch` khi deploy lên AKS).
- [x] **Bước 5: Script Đo độ trễ & Nghiệm thu (`scripts/latency_benchmark.py`)**
  - Hoàn thiện công cụ đo 100 requests tính $P_{50}, P_{90}, P_{99}$ Network/Storage Latency và tự động xuất biểu đồ PNG vào `exports/`.

---

## Hướng dẫn khởi chạy & Kiểm thử nhanh

### 1. Chạy toàn bộ hệ thống bằng Docker Compose (Local)
```bash
cp .env.example .env
docker compose up -d --build
```

### 2. Chạy môi trường phát triển Python & Huấn luyện lại Model
```bash
# Khởi tạo dữ liệu mẫu vào PostgreSQL, Azurite và Cosmos Emulator
python scripts/init_local_dev.py

# Chạy luồng ETL -> Train SVD/Hybrid -> Export lên Cosmos DB
python -m ml_pipeline.pipeline_runner --model-version v1.0-svd

# Khởi chạy đồng thời 3 Microservices (8001-8003) & FaaS (7071)
python scripts/run_backend_services.py
```

### 3. Đo kiểm độ trễ Network & Storage (100 Requests)
```bash
python scripts/latency_benchmark.py \
  --sea-url "http://localhost:8003/api/v1/recommendations/popular/trending" \
  --requests 100 --concurrency 10
```

### 4. Chuyển đổi lưu lượng Zero-downtime Blue/Green trên AKS
```bash
kubectl patch service recommender-service -n ecommerce-rec \
  -p '{"spec":{"selector":{"app":"recommender","version":"green"}}}'
```