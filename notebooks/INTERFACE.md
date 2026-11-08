# TÀI LIỆU TỔNG HỢP OUTPUT & HƯỚNG DẪN TÍCH HỢP HỆ THỐNG

Tài liệu này tổng hợp toàn bộ các artifact và output sinh ra từ quy trình ETL, huấn luyện mô hình Machine Learning (`01_ecommerce_recommender_pipeline.py`) và quy định phương thức tích hợp cho các dịch vụ tiếp theo trong kiến trúc hệ thống E-commerce Recommender (Backend Microservices, Azure Functions, Frontend SPA, Kubernetes).

---

## 1. Dữ liệu Danh mục Sản phẩm Web & SQL Seed

### 1.1. Output là gì? Trên nền tảng gì?
* **Bản chất Output:**
  * File `seed_products.sql`: Script DDL và DML khởi tạo bảng `products` và nạp dữ liệu chuẩn hóa của 1.000 sản phẩm Amazon (đã validate ảnh còn tồn tại 100%, khử rác, median impute giá).
  * File `web_products.parquet` & `web_products.csv`: Dataset sản phẩm dạng bảng rút gọn gồm các trường phục vụ hiển thị: `product_id`, `name`, `category`, `price`, `thumbnail_url`, `description`, `rating`, `rating_count`, `stock_quantity`.
* **Nền tảng lưu trữ / Phân phối:**
  * **Hugging Face Hub:** Dataset Repo `https://huggingface.co/datasets/cuongduongok/amazon-musical-instruments-clean`
  * **Cục bộ / Git Repo:** Đường dẫn `data/processed/seed_products.sql` và `scripts/sql/03_seed_data.sql`.

### 1.2. Để sử dụng vào hệ thống thì cần gì?
* **Chế độ bảo mật / Truy cập:** **Public** (trên Hugging Face Dataset) hoặc nội bộ mã nguồn Git.
* **Cần gì để tích hợp vào hệ thống?**
  * **Dành cho Auth/Order Service (PostgreSQL Database):**
    * Cần **Connection String** của Azure Database for PostgreSQL:
      `postgresql://<user>:<password>@<server-name>.postgres.database.azure.com:5432/<dbname>?sslmode=require`
    * Thực thi nạp dữ liệu một lần (Seed Data):
      ```bash
      psql "postgresql://..." -f data/processed/seed_products.sql
      ```
  * **Dành cho Frontend / Mock Test:** Truy cập file `data/processed/web_products_sample_50.json` để giả lập dữ liệu hiển thị component ProductCard trước khi kết nối API.

---

## 2. Model Artifacts (Item Similarity & Matrix Factorization SVD)

### 2.1. Output là gì? Trên nền tảng gì?
* **Bản chất Output:**
  * `item_similarity.npz`: Ma trận Cosine Similarity ($N \times N$, $1.000 \times 1.000$) kết hợp giữa Co-purchase ($70\%$) và Content TF-IDF ($30\%$). Dùng cho bài toán đề xuất Item-to-Item ("Sản phẩm thường được mua cùng").
  * `svd_recommender.pkl`: Đối tượng Python Pickle chứa ma trận người dùng tiềm ẩn $P_{M \times k}$, sản phẩm tiềm ẩn $Q_{N \times k}$ ($k=20$), cùng 2 từ điển ánh xạ `user2idx`, `item2idx` và vector giá trị suy biến `sigma`. Dùng để tính điểm tương quan tức thời giữa User và Item.
* **Nền tảng lưu trữ / Phân phối:**
  * **Azure Blob Storage:** Container `model-artifacts` (Blob path: `item_similarity.npz`, `svd_recommender.pkl`).
  * **Hugging Face Hub (Dự phòng):** Model Hub `https://huggingface.co/<HF_USERNAME>/amazon-musical-recommender-models`.

### 2.2. Để sử dụng vào hệ thống thì cần gì?
* **Chế độ bảo mật / Truy cập:** **Private** (khuyến nghị trên Cloud) hoặc **Public** (trên Hugging Face).
* **Thông tin xác thực & Tham số kết nối:**
  * **Azure Blob Storage Connection String:** Cần biến môi trường `AZURE_STORAGE_CONNECTION_STRING` khai báo trong file cấu hình Kubernetes Secret:
    ```bash
    AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=<storage_account>;AccountKey=<key>;EndpointSuffix=core.windows.net"
    ```
  * **Hugging Face Token (Nếu tải từ HF):** Cần `HF_TOKEN` hoặc public repo tải trực tiếp qua URL:
    `https://huggingface.co/cuongduongok/amazon-musical-recommender-models/resolve/main/item_similarity.npz`
* **Vị trí tích hợp trong hệ thống:**
  * Pod `recommender_service` (FastAPI) đọc trực tiếp các file này khi container khởi động (startup event) để nạp vào RAM máy chủ, phục vụ suy luận Real-time.

---

## 3. Precomputed Recommendations (Data Serving Layer)

### 3.1. Output là gì? Trên nền tảng gì?
* **Bản chất Output:** Dữ liệu tính toán trước dạng tài liệu NoSQL Document JSON, chia thành 3 nhóm:
  1. `system_metadata` (Document ID: `popular_items`): Chứa Top-10 sản phẩm có số lượng rating và điểm trung bình cao nhất, dùng làm fallback cho người dùng mới (Cold-Start Problem).
  2. `user_recommendations` (Partition Key `/id` = `user_id`): Chứa mảng danh sách Top-10 sản phẩm gợi ý cá nhân hóa `[{product_id, score, rank}]` đã lọc bỏ các sản phẩm user từng tương tác.
  3. `item_recommendations` (Partition Key `/id` = `product_id`): Chứa mảng Top-5 sản phẩm liên quan mật thiết nhất `[{product_id, similarity_score, bundle_type}]` phục vụ khối "Thường mua cùng".
* **Nền tảng lưu trữ / Phân phối:**
  * **Azure Cosmos DB NoSQL:** Database `ecommerce_recommender_db` (chạy chế độ Shared Throughput 400 RU/s).

### 3.2. Để sử dụng vào hệ thống thì cần gì?
* **Chế độ bảo mật / Truy cập:** **Private / Protected** (yêu cầu Master Key hoặc RBAC).
* **Thông tin xác thực & Tham số kết nối:**
  * Cần cấu hình 2 biến môi trường vào `k8s/configmap-secrets.yaml` hoặc `.env`:
    * `COSMOS_DB_ENDPOINT`: `https://<account-name>.documents.azure.com:443/`
    * `COSMOS_DB_PRIMARY_KEY`: Khóa chính `AccountKey==`
* **Vị trí tích hợp trong hệ thống:**
  * `recommender_service/cosmos_client.py`: Khởi tạo `CosmosClient`, thực hiện truy vấn Point-Read với độ phức tạp $O(1)$ và độ trễ $< 10\text{ms}$:
    ```python
    container = db.get_container_client("user_recommendations")
    response = container.read_item(item=user_id, partition_key=user_id)
    ```

---

## 4. Dataset Đầy đủ & File Ảnh Backup (Serving Assets)

### 4.1. Output là gì? Trên nền tảng gì?
* **Bản chất Output:**
  * `training_products.parquet` & `training_interactions.parquet`: Bộ dữ liệu đã lọc K-core, đồng bộ khóa ngoại và làm giàu thuộc tính text/features phục vụ cho các chu kỳ re-train mô hình hoặc huấn luyện Deep Learning/GNN sau này.
  * Thư mục ảnh backup `/images/{thumb, large, hi_res}/{product_id}.jpg`: Toàn bộ 3.000 file ảnh gốc được tải trực tiếp về lưu trữ dự phòng, phòng trường hợp CDN của Amazon xóa hoặc chặn IP truy cập từ Web client.
* **Nền tảng lưu trữ / Phân phối:**
  * **Hugging Face Hub:** Dataset Repository `https://huggingface.co/datasets/<HF_USERNAME>/amazon-musical-instruments-clean` (Thư mục `/images`).

### 4.2. Để sử dụng vào hệ thống thì cần gì?
* **Chế độ bảo mật / Truy cập:** **Public** (cho phép Client tải trực tiếp ảnh).
* **Thông tin xác thực & Tham số kết nối:**
  * Không cần API key để đọc ảnh/dữ liệu nếu Repository đặt ở chế độ **Public**.
  * Định dạng URL CDN lấy ảnh trực tiếp cho Frontend React:
    `https://huggingface.co/datasets/<HF_USERNAME>/amazon-musical-instruments-clean/resolve/main/images/thumb/{product_id}.jpg`
* **Vị trí tích hợp trong hệ thống:**
  * Thuộc tính `thumbnail_url` trong UI Components (`ProductCard.tsx`, `ProductDetail.tsx`) fallback về đường dẫn ảnh trên Hugging Face nếu link gốc Amazon bị lỗi 403/404.

---

## 5. Bảng Tổng Hợp Chi Tiết Ma Trận Tích Hợp (Integration Matrix)

| STT | Thành phần Output | Nền tảng lưu trữ | Cơ chế bảo mật | Tham số xác thực cần thiết | Thành phần hệ thống tích hợp |
| :---: | :--- | :--- | :--- | :--- | :--- |
| **1** | `seed_products.sql` / `web_products.parquet` | Cục bộ / HF Dataset | Public / Nội bộ | `DATABASE_URL` (PostgreSQL Connection String) | **Auth Service & Order Service** (Khởi tạo kho và danh mục) |
| **2** | `item_similarity.npz` & `svd_recommender.pkl` | Azure Blob Storage (`model-artifacts`) | Private | `AZURE_STORAGE_CONNECTION_STRING` | **Recommender Service** (Khởi động Model Pod trên AKS) |
| **3** | Precomputed JSON (Metadata, User Recs, Item Recs) | Azure Cosmos DB (`ecommerce_recommender_db`) | Private | `COSMOS_DB_ENDPOINT`, `COSMOS_DB_PRIMARY_KEY` | **Recommender API** (Endpoint `/api/v1/recommendations/{user_id}`) |
| **4** | Cụm ảnh backup (`/images/*/*.jpg`) | Hugging Face Dataset | Public | URL CDN trực tiếp (Không cần key) | **Web Frontend (React/Vite)** (Thẻ `<img>` hiển thị sản phẩm) |
| **5** | Log tương tác mới (`click`, `rating`, `add_to_cart`) | Azure Blob Storage (Append Blobs) | Private | `AzureWebJobsStorage` / `AZURE_STORAGE_CONNECTION_STRING` | **Azure Functions** (Tiếp nhận event từ Frontend đẩy vào Raw Data Lake) |