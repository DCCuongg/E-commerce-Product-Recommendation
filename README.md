# E-commerce-Product-Recommendation
Đồ án môn
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
| 4 | Đặng Nguyễn Hoàng Thạch | 23521411 | [@EvogasBaron](https://github.com/EvogasBaron) | Thành viên |\


## Kiến trúc tổng thể hệ thống

Hệ thống được thiết kế theo mô hình Microservices và kiến trúc Lambda/Cloud-Native phục vụ hệ thống gợi ý thương mại điện tử:

```
[ Client Browser (React + Vite) ]
          │
          ├──> [ Ingress Controller / Azure API Management ]
          │         │
          │         ├──> [ Auth Service (FastAPI) - Port 8001 ] ──> [ Database: Postgres/Cosmos ]
          │         ├──> [ Order/Cart Service (FastAPI) - Port 8002 ] ──> [ Database: Postgres/Cosmos ]
          │         └──> [ Recommender API (FastAPI) - Port 8003 ] ──> [ Cosmos DB (Precomputed Top-K / Features) ]
          │
          └──> [ Event Collector (Azure Function - FaaS) ]
                    │ (Lưu trữ bất đồng bộ log rating/click)
                    ▼
          [ Azure Blob Storage (Raw Data Lake) ]
                    │
                    ▼ (ETL & Huấn luyện: DSVM / Local Training Script)
          [ Data Science Machine / PySpark Pipeline ]
                    │
                    ▼ (Export Model & Predictions)
          [ Azure Cosmos DB (NoSQL Document Store) ]

```

---

## Cấu hình hạ tầng trên gói Azure for Students

Gói Azure for Students cung cấp **100 USD credit** kèm một số dịch vụ miễn phí 12 tháng. Để tránh cạn kiệt tài nguyên và credit trong thời gian làm bài, cấu hình hệ thống được chuẩn hóa như sau:

| Thành phần | Dịch vụ đề xuất | Cấu hình tối ưu ngân sách | Chính sách chi phí & Hạn mức Free |
| --- | --- | --- | --- |
| **Database NoSQL** | Azure Cosmos DB | API for NoSQL, Serverless hoặc Provisioned Throughput 1000 RU/s | **Bật chế độ Free Tier Discount** (miễn phí 1000 RU/s và 25 GB dung lượng trọn đời). |
| **Database Relational (Auth/Cart)** | Azure Database for PostgreSQL (Flexible Server) hoặc SQLite | Burstable `Standard_B1ms` (1 vCPU, 2GB RAM, 32GB Storage) | Nằm trong gói miễn phí 12 tháng của Azure Student. Nếu hết quota, containerize PostgreSQL trên VM. |
| **Object Storage** | Azure Blob Storage | Hot Tier, Locally Redundant Storage (LRS) | 5GB LRS Block Blob miễn phí 12 tháng. Lưu trữ dataset raw và checkpoints. |
| **Microservices & Model Serving** | Azure Kubernetes Service (AKS) / Azure Container Instances (ACI) | 1 System Node Pool: `Standard_B2s` (2 vCPU, 4GB RAM, Linux) | AKS Master Node miễn phí quản lý; chỉ tính tiền Worker Node VM (~$0.04/h, tắt khi không demo). |
| **FaaS (Hàm phi máy chủ)** | Azure Functions | Consumption Plan (Linux, Python 3.10/3.11) | Miễn phí 1,000,000 requests/tháng và 400,000 GB-s/tháng. |
| **Training Pipeline** | Local Machine / Google Colab (T4 GPU) | Export model artifact lên Blob Storage | Không tốn credit Azure; giả lập đúng quy trình Data Science VM của Azure. |

---

## Kiến trúc thư mục dự án (Monorepo)

```bash
ecommerce-recommender-azure/
├── .github/
│   └── workflows/
│       ├── deploy-frontend.yml
│       └── deploy-k8s.yml
├── data/
│   ├── raw/                       # Chứa sample tập Amazon Reviews 2023
│   │   ├── meta_sample.jsonl
│   │   └── review_sample.jsonl
│   └── processed/                 # Dữ liệu sau ETL sẵn sàng huấn luyện
├── ml_pipeline/                   # Module ETL và Huấn luyện mô hình
│   ├── __init__.py
│   ├── config.py                  # Cấu hình tham số, Azure Connection Strings
│   ├── etl_extractor.py           # Bước 1: Trích xuất và làm sạch dữ liệu Amazon
│   ├── feature_engineering.py     # Bước 2: Xây dựng ma trận tương tác User-Item
│   ├── train_recommender.py       # Bước 3: Huấn luyện ALS / SVD / Item-to-Item
│   └── export_to_cosmos.py        # Bước 4: Đẩy kết quả Top-K và vectors vào Cosmos DB
├── services/
│   ├── auth_service/              # Microservice 1: Quản lý người dùng & phân quyền
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py
│   │   ├── models.py
│   │   └── auth_handler.py
│   ├── order_service/             # Microservice 2: Giỏ hàng, Đặt hàng & Khóa tồn kho
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py
│   │   ├── models.py
│   │   └── inventory_lock.py
│   └── recommender_service/       # Model Serving API (AKS Deployment)
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── main.py                # Endpoint: GET /api/v1/recommendations/{user_id}
│       └── cosmos_client.py
├── azure_functions/               # FaaS: Thu thập log tương tác người dùng
│   ├── LogInteractionFunction/
│   │   ├── __init__.py
│   │   └── function.json
│   ├── host.json
│   └── local.settings.json
├── frontend/                      # Giao diện Web Client
│   ├── public/
│   ├── src/
│   │   ├── assets/
│   │   ├── components/            # Header, ProductCard, CartDrawer, Carousel
│   │   ├── pages/
│   │   │   ├── HomePage.tsx       # Trang 1: Trang chủ & Top gợi ý
│   │   │   ├── ProductDetail.tsx  # Trang 2: Chi tiết & "Thường mua cùng"
│   │   │   ├── AddToCartModal.tsx # Trang 3: Thao tác thêm vào giỏ
│   │   │   └── CartPage.tsx       # Trang 4: Danh sách giỏ hàng & Checkout
│   │   ├── services/              # Axios API calls
│   │   ├── store/                 # Zustand store (Cart & Session)
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   ├── tailwind.config.js
│   └── vite.config.ts
├── k8s/                           # Tệp cấu hình triển khai Kubernetes (Blue/Green)
│   ├── namespace.yaml
│   ├── configmap-secrets.yaml
│   ├── auth-service-deploy.yaml
│   ├── order-service-deploy.yaml
│   ├── recommender-blue.yaml      # Deployment Blue (Phiên bản v1)
│   ├── recommender-green.yaml     # Deployment Green (Phiên bản v2)
│   ├── recommender-service.yaml   # Service định tuyến traffic Blue/Green
│   └── ingress.yaml
├── scripts/
│   ├── latency_benchmark.py       # Kịch bản đo độ trễ Network & Storage
│   └── seed_products.py           # Import danh mục sản phẩm vào Web DB
├── docker-compose.yml             # Môi trường chạy kiểm thử cục bộ
└── README.md

```

---

## Giải trình chi tiết theo bảng Rubric đánh giá

### Tiêu chí 1: Giới thiệu bài toán (1.5 điểm)

1. **Phân loại bài toán (0.25đ):**
* *Thu thập (Data Ingestion):* Ghi nhận hành vi tương tác thực tế từ client (click, view, add-to-cart, star rating) thông qua Azure Function ghi log trực tiếp vào Azure Blob Storage.
* *Lưu trữ (Storage):* Lưu trữ dữ liệu phi cấu trúc/bán cấu trúc (logs, JSONL raw) trên Azure Blob Storage; lưu trữ danh mục sản phẩm và bảng tra cứu kết quả gợi ý (Top-K Precomputed) trên Azure Cosmos DB; lưu trữ dữ liệu giao dịch trên PostgreSQL.
* *Xử lý (Data Processing & Training):* Xử lý luồng ETL, lọc ma trận thưa (Sparse Matrix), huấn luyện mô hình Collaborative Filtering & Content-Based.
* *Trực quan (Visualization/Serving):* Hiển thị danh mục sản phẩm và các dải đề xuất theo thời gian thực (Real-time Recommendation Shelf) trên Web Frontend.


2. **Loại dữ liệu (0.25đ):**
* *Web Data:* Tương tác người dùng dạng JSON payloads gửi từ giao diện SPA.
* *Database:* Dữ liệu quan hệ (Người dùng, Đơn hàng, Tồn kho) và Dữ liệu Document NoSQL (Metadata sản phẩm, Vector đặc trưng).
* *Data Analyst / Dataset:* Dữ liệu lịch sử mua sắm và đánh giá từ tập `Amazon-Reviews-2023`.


3. **Kích thước dữ liệu và dung lượng bộ nhớ (>4GB) - So sánh Cloud vs On-premise (0.75đ):**
* *Kích thước dữ liệu:* Tập dữ liệu gốc Amazon Reviews 2023 có kích thước vượt mức 4GB (hàng chục GB nếu tính toàn bộ danh mục). Khi đưa vào pipeline, dữ liệu thô dạng JSONL > 4.2 GB được xử lý phân tán theo batch.
* *So sánh hiệu năng xử lý:*



| Tiêu chí | Máy chủ truyền thống (On-premise / Local PC) | Hệ thống Cloud (Azure Data Lake + Virtual VM/Databricks) |
| --- | --- | --- |
| **Tốc độ đọc/ghi (I/O)** | Phụ thuộc tốc độ SSD cục bộ (500MB/s - 2GB/s). Giới hạn bởi băng thông bus nội bộ. | Tốc độ truyền tải mở rộng tự động theo IOPS phân tán của Storage Account (hỗ trợ tới hàng chục Gbps). |
| **Giới hạn bộ nhớ (RAM/Out-Of-Memory)** | Cố định (ví dụ 8GB - 16GB). Khi nạp tập dữ liệu >4GB để tính ma trận tương tác $U \times I$, nguy cơ tràn RAM (OOM) rất cao. | Dễ dàng scale-up cấu hình RAM (32GB - 128GB) hoặc scale-out theo cụm Spark (Databricks) phân tán bộ nhớ trên RAM nhiều worker node. |
| **Thời gian huấn luyện mô hình** | Lâu (chạy tuần tự trên CPU), không tận dụng được GPU chuyên dụng nếu phần cứng không hỗ trợ. | Tăng tốc qua VM có GPU (NC-series) hoặc tối ưu hóa vectorization trên Spark cluster. |

4. **Phân loại thành phần Cloud (0.25đ):**
* **IaaS (Infrastructure as a Service):** Azure Virtual Machines (dùng cho Data Science VM hoặc k3s/AKS worker node VM).
* **PaaS (Platform as a Service):** Azure Cosmos DB, Azure Database for PostgreSQL, Azure App Service / AKS (Managed Kubernetes Control Plane).
* **FaaS (Function as a Service):** Azure Functions (chạy tác vụ log interaction không máy chủ).
* **SaaS (Software as a Service):** Power BI (nếu dùng làm báo cáo quản trị) hoặc Azure Monitor / Application Insights.



---

### Tiêu chí 2: Cơ sở lý thuyết (1.5 điểm)

1. **Cơ sở lý thuyết về định dạng lưu trữ (0.5đ):**
* *Web - Visualize:* JSON (JavaScript Object Notation) - chuẩn dữ liệu nhẹ, tương thích trực tiếp với React State và REST API.
* *Database:*
* PostgreSQL: Relational Tables (chuẩn hóa 3NF) đảm bảo tính toàn vẹn dữ liệu cho giao dịch thanh toán và tài khoản.
* Azure Cosmos DB: BSON/JSON Document - mô hình Key-Value và Document Store với cấu trúc linh hoạt, hỗ trợ lưu mảng đối tượng danh sách sản phẩm gợi ý `top_recommendations: [{product_id, score}]`.


* *Train Model:* Lưu trữ ma trận thưa dưới định dạng Scipy CSR Matrix (Compressed Sparse Row) để tiết kiệm 95% bộ nhớ; xuất mô hình dưới dạng `.pkl` (Pickle), `.onnx` hoặc ma trận trọng số nhúng (Embedding weights).
* *Storage Cloud (Azure Blob):* Dạng Block Blob phân vùng theo thư mục logic `logs/year=2026/month=11/day=07/*.jsonl` và định dạng nén Parquet/Gzip giúp tối ưu hóa dung lượng lưu trữ và chi phí I/O.


2. **Cơ sở lý thuyết về thuật toán xử lý & Luồng dữ liệu (0.5đ):**
* *Thuật toán Gợi ý 1 - Item-to-Item Collaborative Filtering (Cosine Similarity trên TF-IDF & Metadata):*
* Áp dụng cho trang chi tiết sản phẩm: "Khách hàng mua bút chì cũng thường mua gọt bút chì, sổ tay".
* Sử dụng độ đo tương đồng Cosine giữa vector đặc tính của sản phẩm $i$ và $j$:

$$\text{Cosine Similarity}(u, v) = \frac{\mathbf{u} \cdot \mathbf{v}}{\Vert{}\mathbf{u}\Vert{}_2 \Vert{}\mathbf{v}\Vert{}_2}$$




* *Thuật toán Gợi ý 2 - Matrix Factorization (Truncated SVD / Implicit ALS):*
* Phân rã ma trận tương tác User - Item $R_{m \times n}$ thành hai ma trận bậc thấp đại diện cho vector ẩn của người dùng $P_{m \times k}$ và sản phẩm $Q_{n \times k}$ sao cho:

$$\hat{R} \approx P \times Q^T$$


* Với người dùng mới (Cold-start): Fallback về Top sản phẩm có đánh giá trung bình cao nhất và số lượng đánh giá lớn nhất trong cùng danh mục.


* *Luồng dữ liệu (Data Pipeline Flow):*
`Client Browser` $\rightarrow$ Thao tác Click/Đánh giá $\rightarrow$ `Azure Function` $\rightarrow$ Ghi log Append vào `Blob Storage` $\rightarrow$ Định kỳ chạy `ETL Job` $\rightarrow$ Train mô hình $\rightarrow$ Lưu kết quả Top-K vào `Cosmos DB` $\rightarrow$ `Recommender Service` truy vấn theo $O(1)$ $\rightarrow$ `Frontend`.


3. **Chi tiết các dịch vụ Azure sử dụng (0.5đ):**
* **Azure Blob Storage:** Chứa dữ liệu gốc (Amazon Reviews dataset) và log luồng tương tác thực tế từ web.
* **Data Science VM / Local Python Runtime:** Cài đặt sẵn PySpark, Scikit-Learn, LightFM/Surprise để chạy pipeline xử lý dữ liệu lớn.
* **Azure Cosmos DB:** Đóng vai trò Data Serving Layer lưu trữ `user_id -> list of recommended items` với độ trễ phản hồi < 10ms.
* **Azure Kubernetes Service (AKS):** Nền tảng điều phối container chứa 3 microservices (Auth, Order, Recommender), hỗ trợ cân bằng tải và Auto-scaling.
* **Azure Functions:** Hàm phi máy chủ tiếp nhận HTTP POST event từ web để giải phóng tải cho Backend chính.



---

### Tiêu chí 3: Mô hình dữ liệu & Tối ưu hiệu năng (2.0 điểm)

1. **Tốc độ cho phép đọc ghi (0.5đ):**
* *Azure Cosmos DB:* Cung cấp cam kết SLA đọc < 10ms và ghi < 10ms với phân vùng hợp lý (Partition Key: `/user_id` hoặc `/category`). Thông lượng cấu hình từ 400 đến 1000 RU/s (Request Units/giây) cho phép đáp ứng hàng trăm lượt đọc đồng thời.
* *Azure Blob Storage:* Hỗ trợ thông lượng đọc tuần tự lên đến 60 MB/s trên mỗi blob, đáp ứng tốt cho tác vụ nạp dữ liệu huấn luyện hàng loạt.


2. **Thiết lập luồng xử lý dữ liệu tự động ETL (0.5đ):**
* *Bước 1 (Extract):* Web Client kích hoạt request đánh giá sản phẩm $\rightarrow$ Azure Function tiếp nhận và ghi nhận bản ghi vào Blob Storage theo định dạng:
`{"user_id": "U101", "item_id": "B001", "action": "rating", "value": 5, "timestamp": 1731000000}`
* *Bước 2 (Transform):* Script Python `etl_extractor.py` định kỳ kích hoạt:
* Lọc bỏ người dùng có dưới 3 lượt tương tác và sản phẩm có dưới 2 lượt tương tác để giải quyết độ thưa ma trận.
* Chuẩn hóa điểm rating từ khoảng $[1, 5]$ và chuyển đổi hành vi xem trang thành implicit score: Click = 1, Add-to-cart = 3, Purchase/Review = 5.


* *Bước 3 (Load):* Nạp dữ liệu vào mô hình tính toán, sau đó lưu kết quả Top-20 sản phẩm gợi ý cho mỗi người dùng vào Cosmos DB.


3. **Phương pháp đo độ trễ (Latency Delay) khi thiết lập Server ở các Region khác nhau (0.5đ):**
* *Bản chất phép đo:* Cần thực hiện kiểm thử ở cả **2 cấp độ**:
1. **Network Latency (Mạng giữa các Region):** Triển khai ứng dụng/API tại 2 Region khác nhau: `Southeast Asia` (Singapore - Region gần người dùng Việt Nam nhất) và `East US` (Mỹ). Sử dụng script đo đạc để ghi lại:
* DNS Lookup Time.
* TCP Handshake + TLS Connect Time.
* TTFB (Time to First Byte): Thời gian từ lúc gửi byte request đầu tiên đến khi nhận byte response đầu tiên.


2. **Storage Latency (Truy xuất lưu trữ nội vùng vs xuyên vùng):** Đo tốc độ đọc/ghi dữ liệu từ API đặt tại `Southeast Asia` kết nối đến Blob Storage/Cosmos DB đặt cùng tại `Southeast Asia` (Intra-region) so với Storage đặt tại `East US` (Cross-region).


* *Kịch bản kiểm thử:* Sử dụng script `scripts/latency_benchmark.py` gửi đồng thời 100 requests lặp lại và tính toán các chỉ số: $P_{50}, P_{90}, P_{99}$ latency.


4. **Giải pháp tối ưu hóa lưu trữ và tốc độ đọc ghi (0.5đ):**
* **In-memory Caching (Redis / Client Caching):** Sử dụng Redis hoặc bộ nhớ đệm tại API Gateway để cache lại kết quả Top-K gợi ý của các sản phẩm phổ biến (TTL = 30 phút), giảm 80% lượt đọc vào Cosmos DB.
* **Connection Pooling:** Duy trì pool kết nối TCP tái sử dụng tới Cosmos DB và Database thay vì tạo kết nối mới ở mỗi request.
* **Partition Key Optimization:** Chọn Partition Key đồng đều (ví dụ `user_id` băm hoặc `category`) trong Cosmos DB để tránh "Hot Partition", phân bổ tải đều trên các phân vùng vật lý.
* **Data Compression:** Nén payload JSON trả về từ server bằng Gzip/Brotli; định dạng ảnh thumbnail sản phẩm chuyển đổi sang định dạng WebP thế hệ mới.



---

### Tiêu chí 4: Hiện thực hệ thống Web & Nghiệp vụ (3.0 điểm)

1. **Deploy trang web lên Cloud - Đủ 4 trang nghiệp vụ (1.0đ):**
* *Lựa chọn Frontend:* Sử dụng **React.js (Vite) + Tailwind CSS**.
* *Lý do:* Build ra mã nguồn tĩnh siêu nhẹ, đóng gói vào Docker container chạy bằng Nginx (dung lượng chỉ ~25MB RAM, khởi động tức thì), tiêu thụ rất ít tài nguyên trên VM gói sinh viên so với runtime Node.js của Next.js.


* *Chi tiết 4 màn hình:*
* **Trang 1 - Trang chủ (Home Page):** Hiển thị danh mục sản phẩm, banner, và khối Carousel "Gợi ý dành riêng cho bạn" gọi từ Recommender API.
* **Trang 2 - Trang chi tiết sản phẩm (Product Detail Page):** Mô tả sản phẩm, giá, số sao, form đánh giá rating/review, kèm khối "Sản phẩm thường được mua cùng".
* **Trang 3 - Modal/Trang thêm vào giỏ hàng (Add to Cart Modal/Action):** Cho phép chọn số lượng, biến thể, kiểm tra nhanh tồn kho, cập nhật giỏ hàng tức thời không cần tải lại trang.
* **Trang 4 - Danh sách giỏ hàng & Thanh toán (Cart Page):** Liệt kê các mặt hàng, điều chỉnh số lượng, tính tổng tiền, nút "Đặt hàng" (Checkout).




2. **Triển khai hệ thống Blue/Green Deployment (0.5đ):**
* Tạo 2 Kubernetes Deployment riêng biệt trên AKS: `recommender-deployment-blue` (chạy phiên bản v1) và `recommender-deployment-green` (chạy phiên bản v2).
* Sử dụng một Kubernetes Service làm Router:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: recommender-service
spec:
  selector:
    app: recommender
    version: blue   # Khi muốn chuyển sang Green, chỉ cần đổi thành: version: green
  ports:
    - port: 80
      targetPort: 8003

```


* Khi cập nhật mô hình mới: Triển khai pod Green $\rightarrow$ Kiểm tra trạng thái Health Check sẵn sàng $\rightarrow$ Cập nhật label selector của Service sang `green` $\rightarrow$ Chuyển dịch lưu lượng tức thời mà không gây gián đoạn dịch vụ (Zero-downtime).


3. **Triển khai 2 Microservices độc lập và giao tiếp nội bộ (1.0đ):**
* **Service A - Auth Service (Port 8001):**
* Đăng ký, đăng nhập tài khoản người dùng, băm mật khẩu (bcrypt), sinh JWT (JSON Web Token) chứa `user_id` và `role`.


* **Service B - Order/Cart Service (Port 8002):**
* Quản lý trạng thái giỏ hàng và đặt hàng.


* **Cơ chế giao tiếp giữa 2 Service:**
* Khi người dùng gửi request tạo đơn hàng đến `Order Service`, request mang theo Bearer Token.
* `Order Service` thực hiện HTTP Call nội bộ (hoặc giải mã xác thực public key) sang `http://auth-service/api/v1/auth/verify-token` để xác thực danh tính người dùng trước khi trừ kho và tạo đơn.




4. **Xử lý bài toán Concurrency, Khóa đồng bộ và Rollback chống vi phạm:**
* *Vấn đề đặt ra:* Khi chỉ còn 1 sản phẩm cuối cùng trong kho nhưng có nhiều người dùng bấm "Mua ngay" cùng một thời điểm.
* *Giải pháp - Pessimistic Concurrency Control (Khóa bi quan):*
* Thực hiện câu lệnh SQL có khóa hàng tại `Order Service`:
```sql
BEGIN;
SELECT stock_quantity FROM products WHERE id = :product_id FOR UPDATE;
-- Kiểm tra: Nếu stock_quantity < requested_quantity => ROLLBACK và báo lỗi hết hàng
UPDATE products SET stock_quantity = stock_quantity - :requested_quantity WHERE id = :product_id;
INSERT INTO orders (user_id, total_amount, status) VALUES (...);
COMMIT;

```


* Nếu có bất kỳ lỗi nào trong quá trình xử lý (lỗi thanh toán, lỗi mạng), lệnh `ROLLBACK` tự động hoàn trả lại số lượng tồn kho nguyên vẹn, đảm bảo tính nhất quán dữ liệu ACID.




5. **Sử dụng FaaS (Azure Function) (0.5đ):**
* Viết một Azure Function HTTP Trigger bằng Python (`azure_functions/LogInteractionFunction`).
* Mỗi khi người dùng bấm vào xem sản phẩm hoặc gửi đánh giá, frontend gọi ngầm một request bất đồng bộ tới Function này.
* Function đẩy dữ liệu trực tiếp vào Azure Blob Storage dưới dạng append log mà không làm chậm luồng xử lý chính của trang web.


6. **Tối ưu độ mượt giao diện Web (Frontend Smoothness):**
* **Optimistic UI Updates:** Khi người dùng bấm "Thêm vào giỏ hàng", giao diện tăng số lượng giỏ hàng ngay lập tức trên UI trước khi server phản hồi thành công; nếu server trả về lỗi mới rollback lại số cũ.
* **Skeleton Loading:** Sử dụng khung xương hiệu ứng shimmer trong lúc chờ dữ liệu API của khối gợi ý sản phẩm, tránh giật layout (Cumulative Layout Shift = 0).
* **Debounced Event Logging:** Các hành vi lướt/tìm kiếm được debounce 300ms trước khi gửi về API để không làm nghẽn mạng client.



---

## Trích xuất & Trừu tượng hóa dữ liệu Amazon Reviews 2023

Tập dữ liệu `McAuley-Lab/Amazon-Reviews-2023` được trừu tượng hóa và ánh xạ vào hệ thống như sau:

* **Tập Metadata (`meta_sample.jsonl`):**
* Trường `parent_asin` $\rightarrow$ Ánh xạ thành `product_id`.
* Trường `title` $\rightarrow$ Ánh xạ thành `product_name`.
* Trường `price` $\rightarrow$ Ánh xạ thành `price` (nếu null, mặc định random phân bổ chuẩn).
* Trường `images` $\rightarrow$ Lấy link ảnh đầu tiên làm `thumbnail_url`.
* Trường `categories` $\rightarrow$ Ánh xạ thành `category`.


* **Tập Reviews & Interactions (`review_sample.jsonl`):**
* Trường `user_id` $\rightarrow$ Khách hàng.
* Trường `parent_asin` $\rightarrow$ Sản phẩm được tương tác.
* Trường `rating` (1 đến 5 sao) $\rightarrow$ Điểm Explicit Feedback.
* Trường `timestamp` $\rightarrow$ Thời gian tương tác.


* **Quy tắc phân nhóm sản phẩm liên quan (Co-purchase):**
* Dựa trên lịch sử các sản phẩm được đánh giá hoặc mua cùng bởi cùng một nhóm khách hàng trong khoảng thời gian nhất định để tính ma trận đồng xuất hiện (Co-occurrence matrix).



---

## Lộ trình các bước thực hiện & Danh mục file code cần viết

Quy trình triển khai chia làm 5 bước lớn, thực hiện tuần tự theo luồng file:

```
[Bước 1: Chuẩn bị Dữ liệu & Huấn luyện Model]
      ├── 1.1: ml_pipeline/config.py
      ├── 1.2: ml_pipeline/etl_extractor.py
      ├── 1.3: ml_pipeline/train_recommender.py
      └── 1.4: ml_pipeline/export_to_cosmos.py
               │
               ▼
[Bước 2: Phát triển Backend Microservices & FaaS]
      ├── 2.1: services/auth_service/main.py
      ├── 2.2: services/order_service/inventory_lock.py & main.py
      ├── 2.3: services/recommender_service/cosmos_client.py & main.py
      └── 2.4: azure_functions/LogInteractionFunction/__init__.py
               │
               ▼
[Bước 3: Phát triển Giao diện Frontend (React + Vite)]
      ├── 3.1: frontend/src/store/cartStore.ts
      ├── 3.2: frontend/src/pages/HomePage.tsx
      ├── 3.3: frontend/src/pages/ProductDetail.tsx
      ├── 3.4: frontend/src/pages/AddToCartModal.tsx
      └── 3.5: frontend/src/pages/CartPage.tsx
               │
               ▼
[Bước 4: Đóng gói Docker & Triển khai AKS (Blue/Green)]
      ├── 4.1: Các tệp Dockerfile (Frontend & 3 Services)
      ├── 4.2: k8s/configmap-secrets.yaml
      ├── 4.3: k8s/recommender-blue.yaml & recommender-green.yaml
      └── 4.4: k8s/recommender-service.yaml & ingress.yaml
               │
               ▼
[Bước 5: Kiểm thử Đo độ trễ & Hoàn thiện Báo cáo]
      ├── 5.1: scripts/latency_benchmark.py
      └── 5.2: Báo cáo Word/PowerPoint chuẩn đồ án KLTN

```

### Bước 1: Pipeline Dữ liệu và Mô hình học máy

1. Viết `ml_pipeline/config.py`: Định nghĩa các chuỗi kết nối Azure Blob, Cosmos DB, đường dẫn thư mục và siêu tham số mô hình.
2. Viết `ml_pipeline/etl_extractor.py`: Đọc file mẫu Amazon Reviews 2023, làm sạch các trường dữ liệu thiếu, lọc danh sách 1,000 sản phẩm và 5,000 tương tác tiêu biểu.
3. Viết `ml_pipeline/train_recommender.py`:
* Xây dựng ma trận tương quan giữa các sản phẩm (Item-to-Item Cosine Similarity).
* Huấn luyện mô hình phân rã ma trận (Matrix Factorization) để sinh danh sách Top-10 sản phẩm cho từng `user_id`.


4. Viết `ml_pipeline/export_to_cosmos.py`: Kết nối Azure Cosmos DB và lưu dữ liệu đã tiền tính toán (Precomputed Recommendations) dưới dạng tài liệu NoSQL.

### Bước 2: Xây dựng Microservices Backend & Azure Function

1. Viết `services/auth_service/main.py`: Cung cấp API `/register`, `/login`, và `/verify-token`.
2. Viết `services/order_service/inventory_lock.py` & `main.py`: Cung cấp API giỏ hàng, thực thi giao dịch trừ kho có khóa chống trùng lặp dữ liệu (Concurrency Lock).
3. Viết `services/recommender_service/cosmos_client.py` & `main.py`: Cung cấp API `/recommendations/{user_id}` đọc dữ liệu từ Cosmos DB trả về JSON cho frontend với độ trễ tối thiểu.
4. Viết `azure_functions/LogInteractionFunction/__init__.py`: Tiếp nhận sự kiện tương tác từ web và ghi vào Azure Blob Storage.

### Bước 3: Phát triển Giao diện Người dùng Web Frontend

1. Cấu hình `frontend/src/store/cartStore.ts`: Quản lý state giỏ hàng và danh tính người dùng bằng Zustand.
2. Viết `frontend/src/pages/HomePage.tsx`: Trang chủ hiển thị danh sách sản phẩm và dải Carousel gợi ý cá nhân hóa.
3. Viết `frontend/src/pages/ProductDetail.tsx`: Trang chi tiết hiển thị sản phẩm kèm mục "Sản phẩm thường được mua cùng".
4. Viết `frontend/src/pages/AddToCartModal.tsx`: Thao tác thêm sản phẩm mượt mà với Optimistic UI.
5. Viết `frontend/src/pages/CartPage.tsx`: Hiển thị giỏ hàng và xử lý nút đặt hàng.

### Bước 4: Đóng gói Container và Triển khai Cloud (Blue/Green)

1. Viết `Dockerfile` cho Frontend và từng Microservice: Sử dụng Multi-stage build để tối ưu kích thước image (< 100MB).
2. Viết `k8s/configmap-secrets.yaml`: Lưu trữ biến môi trường bảo mật trên cụm Kubernetes.
3. Viết `k8s/recommender-blue.yaml` và `recommender-green.yaml`: Tạo hai bản deployment ứng dụng model.
4. Viết `k8s/recommender-service.yaml` và `k8s/ingress.yaml`: Cấu hình bộ điều hướng chuyển đổi lưu lượng giữa hai phiên bản Blue và Green.

### Bước 5: Đo đạc chỉ số & Hoàn thiện hồ sơ nghiệm thu

1. Viết `scripts/latency_benchmark.py`: Thực thi kịch bản đo độ trễ Network giữa các vùng Azure (Southeast Asia vs East US) và đo thông lượng đọc/ghi trên Storage.
2. Xuất dữ liệu biểu đồ độ trễ và hình ảnh chứng minh trên Azure Portal đưa vào báo cáo Word và slide PowerPoint theo định dạng Khóa luận tốt nghiệp.
