
# Tổng quan tập dữ liệu: Amazon Reviews 2023 (Phân mục Musical Instruments)

Tập dữ liệu **Amazon Reviews 2023** do **McAuley Lab** (UC San Diego) thu thập và phát hành, phục vụ huấn luyện các bài toán RecSys, NLP, LLMs và Đa phương thức (Multimodal).

---

## 1. Nguồn dữ liệu & Liên kết gốc

* **Trang chủ & Tài liệu dự án:** `[https://amazon-reviews-2023.github.io/](https://amazon-reviews-2023.github.io/)`
* **Tệp đánh giá người dùng (User Reviews - `.jsonl`):**
`[https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/blob/main/raw/review_categories/Musical_Instruments.jsonl](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/blob/main/raw/review_categories/Musical_Instruments.jsonl)`
* **Thư mục siêu dữ liệu sản phẩm (Item Metadata):**
`[https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/tree/main/raw_meta_Musical_Instruments](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/tree/main/raw_meta_Musical_Instruments)`

---

## 2. Rủi ro kỹ thuật & Thách thức thực tế (Tóm tắt)

* **Phân rã liên kết ảnh (Image Rot & Inaccessibility):** Tập dữ liệu chỉ lưu trữ URL trỏ tới máy chủ/CDN chứ không lưu trữ file nhị phân. Các liên kết đối mặt với mã lỗi 404 hoặc ảnh placeholder do người bán xóa listing, người dùng xóa bài đánh giá, hoặc Amazon tái cấu trúc hạ tầng. Việc tải ảnh thời gian thực dễ gặp tình trạng rate-limit, timeout và tỷ lệ missing data tăng dần theo thời gian.
* **Lệch khóa liên kết (`asin` vs `parent_asin`):** Reviews được gắn theo biến thể cụ thể (`asin`), trong khi metadata lại gom nhóm theo mã gốc (`parent_asin`). Việc join sai cấp độ dẫn đến mất liên kết (orphan records) hoặc làm sai lệch đặc tính sản phẩm khi huấn luyện.
* **Thiếu hụt Metadata (Missing Metadata):** Số lượng item được đếm qua tập Reviews; một bộ phận sản phẩm không có metadata tương ứng, tạo vùng mù cold-start hoặc buộc phải loại bỏ khi xử lý dữ liệu.
* **Trôi dạt giá cả theo thời điểm (Price Point-in-time Error):** Trường `price` là snapshot tĩnh tại thời điểm crawl (2023), trong khi các review trải dài từ năm 1996 đến 2023. Sai lệch này ảnh hưởng nghiêm trọng tới các mô hình phân tích hành vi theo độ nhạy giá.
* **Trôi dạt nhãn & Thang đo (Temporal Concept Drift):** Khung thời gian kéo dài 27 năm khiến văn phong, tiếng lóng, độ dài văn bản và tiêu chuẩn chấm sao thay đổi đáng kể qua các thời kỳ, gây bias nếu không gắn trọng số thời gian.
* **Nhiễu cấu trúc trong trường `details`:** Dữ liệu cào từ web chứa nhiều thẻ HTML chưa làm sạch (`<br>`, `<div>`), ký tự escape (`\n`, `\t`) và cấu trúc key-value không chuẩn tắc giữa các gian hàng, làm tốn token của LLMs và đòi hỏi tiền xử lý phức tạp.
* **Spam & Bot Reviews:** Hiện tượng spam, bot đẩy rating hoặc văn bản ngắn vô nghĩa (dù có cờ `verified_purchase`) tạo nhiễu trực tiếp cho tác vụ Sentiment Analysis và tín hiệu Implicit Feedback.

---

## 3. Cấu trúc trường dữ liệu (Data Schema)

### A. Đánh giá của người dùng (User Reviews)

| Tên trường | Kiểu dữ liệu | Ý nghĩa & Mô tả |
| --- | --- | --- |
| `rating` | `float` | Điểm số đánh giá của người dùng (từ 1.0 đến 5.0). |
| `title` | `str` | Tiêu đề của bài đánh giá. |
| `text` | `str` | Nội dung chi tiết của bài đánh giá. |
| `images` | `list` | Danh sách hình ảnh do người mua tải lên kèm kích thước (`small_image_url`, `medium_image_url`, `large_image_url`). |
| `asin` | `str` | Mã định danh biến thể sản phẩm cụ thể (SKU). |
| `parent_asin` | `str` | Mã định danh gốc của nhóm sản phẩm. Sản phẩm có nhiều màu sắc, kích cỡ, phân loại chia sẻ chung `parent_asin`. **Lưu ý:** Cần dùng trường này để liên kết với tệp Metadata. |
| `user_id` | `str` | Mã định danh người đánh giá. |
| `timestamp` | `int` | Thời gian gửi đánh giá (Unix timestamp dạng mili-giây/giây). |
| `verified_purchase` | `bool` | Xác thực mua hàng thực tế từ người dùng (`True`/`False`). |
| `helpful_vote` | `int` | Số lượt bình chọn "hữu ích" cho bài đánh giá. |

---

### B. Siêu dữ liệu sản phẩm (Item Metadata)

| Tên trường | Kiểu dữ liệu | Ý nghĩa & Mô tả |
| --- | --- | --- |
| `main_category` | `str` | Miền danh mục chính của sản phẩm (e.g., *Musical Instruments*). |
| `title` | `str` | Tên đầy đủ của sản phẩm trên trang bán hàng. |
| `average_rating` | `float` | Điểm đánh giá trung bình hiển thị trên trang sản phẩm. |
| `rating_number` | `int` | Tổng số lượt xếp hạng của sản phẩm. |
| `features` | `list` | Danh sách các đặc tính nổi bật dạng gạch đầu dòng (bullet points). |
| `description` | `list` | Đoạn văn bản mô tả chi tiết sản phẩm. |
| `price` | `float` | Giá bán tính theo USD tại thời điểm thu thập dữ liệu. |
| `images` | `list` | Ảnh gốc của sản phẩm với các tỷ lệ (`thumb`, `large`, `hi_res`) và thuộc tính vị trí hiển thị (`variant`). |
| `videos` | `list` | Video giới thiệu sản phẩm (bao gồm tiêu đề và URL). |
| `store` | `str` | Tên gian hàng hoặc thương hiệu niêm yết sản phẩm. |
| `categories` | `list` | Cây thư mục phân cấp của sản phẩm (Hierarchical categories). |
| `details` | `dict` | Từ điển thông số kỹ thuật chi tiết (chất liệu, kích thước, xuất xứ, nhà sản xuất,...). |
| `parent_asin` | `str` | Khóa chính đại diện cho cụm sản phẩm (dùng để join với bảng Review). |
| `bought_together` | `list` | Danh sách `parent_asin` gợi ý mua kèm dựa trên thuật toán sàn. |

---

## 4. Thống kê cơ bản: Phân mục Musical Instruments

| Danh mục | Số lượng Reviews | Số lượng Items | Số lượng Users | #R_Tokens | #M_Tokens | Dữ liệu cung cấp |
| --- | --- | --- | --- | --- | --- | --- |
| **Musical Instruments** | **1.8M** | **213.6K** | **3.0M** | **182.2M** | **200.1M** | `review`, `meta` |

*Chú thích:*

* **#R_Tokens (Review Tokens):** Số lượng token văn bản trong các bài đánh giá của người dùng.
* **#M_Tokens (Metadata Tokens):** Số lượng token khi chuỗi hóa (serialize) các trường thuộc tính từ điển của sản phẩm.
* **Số lượng Items:** Tính theo số lượng mã xuất hiện trong tập đánh giá.

## Những gì cần làm trong bước 1
### 1. Danh mục file của Bước 1 & Các kỹ thuật trực quan hóa trên Colab

Khi bổ sung phương án huấn luyện trên Google Colab song song với mã nguồn triển khai thực tế (`.py`) và module khởi tạo tài nguyên tự động bằng mã nguồn (Infrastructure as Code qua Python SDK), **Bước 1 bao gồm tổng cộng 8 tệp**:

```bash
ecommerce-recommender-azure/
├── .env.example                          # [File 1] Mẫu cấu hình bảo mật, hướng dẫn lấy key Azure/DB
├── scripts/
│   └── init_azure_storage.py             # [File 2] Code tự động khởi tạo Azure Cosmos DB & Blob Containers
├── notebooks/
│   └── 01_ecommerce_recommender_pipeline.ipynb # [File 3] Jupyter Notebook chạy trên Google Colab (EDA, Train, Eval)
└── ml_pipeline/
    ├── __init__.py                       # [File 4] Package initialization
    ├── config.py                         # [File 5] Nạp biến môi trường, định nghĩa đường dẫn & siêu tham số
    ├── etl_extractor.py                  # [File 6] Tải data HF, lọc 1,000 sản phẩm & 5,000 tương tác, gom nhóm combo
    ├── train_recommender.py              # [File 7] Train Item-to-Item Cosine Similarity & Matrix Factorization (SVD)
    └── export_to_cosmos.py               # [File 8] Xuất kết quả Precomputed Top-K vào Azure Cosmos DB

```

#### Các phương pháp trực quan hóa (Visualizations) trong Notebook Colab

1. **Phân phối đánh giá và hiện tượng Đuôi dài (Rating Distribution & Long-tail Interaction Curve):**
* *Mục đích:* Biểu đồ cột thể hiện số lượng sao (1 đến 5 sao) và biểu đồ Log-scale thể hiện số lượng tương tác theo từng sản phẩm.
* *Ý nghĩa:* Chứng minh hiện tượng thưa thớt dữ liệu (Sparsity > 99%) và độ lệch tập trung vào các mặt hàng bán chạy (Head items) so với các mặt hàng ngách (Tail items).


2. **Ma trận thưa trước và sau khi lọc (Matrix Sparsity Spy Plot):**
* *Mục đích:* Dùng hàm `plt.spy()` từ Scipy để hiển thị mật độ điểm ảnh tương tác trên lưới $User \times Item$.
* *Ý nghĩa:* Đánh giá hiệu quả của bước lọc K-Core (lọc bỏ người dùng tương tác quá ít và sản phẩm không có đánh giá).


3. **Chiếu giảm chiều không gian tiềm ẩn sản phẩm (2D Latent Embeddings via t-SNE / PCA):**
* *Mục đích:* Trích xuất ma trận vector đặc trưng của sản phẩm ($Q$) từ mô hình Matrix Factorization (SVD), sau đó giảm chiều xuống 2D bằng t-SNE hoặc PCA và tô màu theo danh mục phụ (Sub-categories: Guitar, Trống, Dây cáp, Micro).
* *Ý nghĩa:* Kiểm chứng xem các sản phẩm có cùng chức năng hoặc thường được mua cùng nhau (ví dụ: Đàn Guitar điện và Ampli/Dây Jack) có tụ lại thành cụm trong không gian vector hay không.


4. **Biểu đồ tỷ lệ phương sai tích lũy (Cumulative Explained Variance Ratio):**
* *Mục đích:* Vẽ đường cong biến thiên phương sai theo số chiều tiềm ẩn $k$ (Latent Factors) của thuật toán TruncatedSVD từ $k=5$ đến $k=100$.
* *Ý nghĩa:* Dùng phương pháp Elbow Method để chọn số lượng latent factor $k$ tối ưu (cân bằng giữa độ chính xác và dung lượng bộ nhớ).


5. **Đường cong chỉ số đánh giá theo K (Metrics Curve: Precision@K, Recall@K, NDCG@K):**
* *Mục đích:* Biểu đồ đường thể hiện sự thay đổi của độ chính xác và độ bao phủ khi $K$ tăng dần ($K \in \{5, 10, 15, 20\}$).
* *Ý nghĩa:* Xác định giá trị $K$ phù hợp nhất để hiển thị trên giao diện người dùng (Carousel UI).


6. **Bản đồ nhiệt độ tương đồng (Item-to-Item Cosine Similarity Heatmap):**
* *Mục đích:* Heatmap thể hiện điểm Cosine Similarity giữa Top 15 nhạc cụ phổ biến nhất.
* *Ý nghĩa:* Đánh giá trực quan thuật toán gom nhóm "Sản phẩm thường mua cùng" (Bundling/Co-occurrence).



---

### 2. Context dữ liệu, ETL và Phương pháp huấn luyện

#### Nguồn dữ liệu & Giới hạn tải

* **Danh mục mục tiêu:** `Musical_Instruments` (Trang thương mại điện tử chuyên nhạc cụ & thiết bị âm thanh) từ kho dữ liệu `McAuley-Lab/Amazon-Reviews-2023`.
* **Đường dẫn dữ liệu thô:**
* Metadata sản phẩm: `[https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/tree/main/raw_meta_Musical_Instruments](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/tree/main/raw_meta_Musical_Instruments)` (dạng Parquet hoặc JSONL nén).
* Lịch sử tương tác/đánh giá: `[https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/blob/main/raw/review_categories/Musical_Instruments.jsonl](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/blob/main/raw/review_categories/Musical_Instruments.jsonl)` (JSONL).


* **Quy mô lọc mục tiêu:**
* Đúng **1,000 sản phẩm** nhạc cụ có thông tin đầy đủ nhất (ảnh, giá, mô tả).
* Đúng **5,000 tương tác** tiêu biểu từ các người dùng tích cực.



#### Phương pháp ETL (Extract - Transform - Load)

```
[Hugging Face / Local Raw Files]
       │ (Streaming read / Batch parsing)
       ▼
[Làm sạch & Chuẩn hóa Schema]
       │ 1. Ép kiểu: price -> float, timestamp -> datetime
       │ 2. Xử lý thiếu: Điền giá trung vị, lọc bỏ sản phẩm không có title/ảnh
       │ 3. Lọc K-Core: User >= 3 tương tác, Item >= 2 tương tác
       ▼
[Gom nhóm Nhu cầu / Co-purchase Bundles]
       │ 1. Khai thác trường 'bought_together' từ Metadata
       │ 2. Khai thác đồng xuất hiện: Các item được đánh giá trong cùng 1 giỏ/thời gian bởi cùng user
       ▼
[Phân tách & Lưu trữ Processed Data]
       ├──> clean_products.parquet   ──> (Dùng để seed vào PostgreSQL)
       └──> clean_interactions.parquet ──> (Dùng để Train ML Models)

```

1. **Extract:** Đọc dữ liệu theo phương thức Streaming (`requests` streaming hoặc thư viện `datasets` của Hugging Face) để nạp từng khối JSONL/Parquet, tránh đọc toàn bộ tệp kích thước lớn gây tràn RAM (OOM) trên môi trường Colab gói tiêu chuẩn hoặc máy trạm.
2. **Transform:**
* Ánh xạ `parent_asin` thành `product_id`.
* Làm sạch trường `price`: Loại bỏ ký hiệu tiền tệ (`$`), parse về `float`. Các bản ghi rỗng được điền bằng giá trung vị (median) của nhóm hàng tương ứng.
* Lọc tương tác: Ưu tiên `verified_purchase == True`. Gán trọng số tương tác: Nếu có `rating` từ 1 đến 5 thì giữ nguyên giá trị explicit; nếu là hành vi xem/click (logs từ web sau này), gán điểm implicit từ 1.0 đến 3.0.
* **Gom nhóm nhu cầu theo bộ (Bundling / Co-purchase Logic):**
* Phân tích trường `bought_together` có sẵn trong metadata.
* Tính toán ma trận đồng xuất hiện (Co-occurrence): Hai sản phẩm $A$ và $B$ được xem là một "Bộ nhu cầu" (Combo) nếu cùng được một `user_id` mua hoặc đánh giá tích cực ($\ge 4$ sao) trong cùng một chu kỳ thời gian.




3. **Load:** Lưu dữ liệu đã làm sạch thành hai tệp trung gian định dạng Apache Parquet (`clean_products.parquet` và `clean_interactions.parquet`) nhằm tối ưu tốc độ đọc và giảm 80% dung lượng so với JSONL.

#### Phương pháp Huấn luyện Mô hình Gợi ý

Pipeline sử dụng phương pháp Hybrid kết hợp hai mô hình bổ trợ nhau:

1. **Mô hình 1: Item-to-Item Cosine Similarity (Gợi ý Bundle / Mua cùng):**
* *Mục đích:* Phục vụ cho Trang chi tiết sản phẩm (`ProductDetail.tsx`) dưới mục "Sản phẩm thường được mua cùng".
* *Thuật toán:* Kết hợp ma trận Co-occurrence chuẩn hóa và vector TF-IDF trích xuất từ `title` + `features` + `categories`.
* *Công thức:*

$$\text{Similarity}(i, j) = \alpha \cdot \text{Cosine}_{\text{co-purchase}}(i, j) + (1 - \alpha) \cdot \text{Cosine}_{\text{content}}(i, j) \quad (\text{với } \alpha = 0.7)$$




2. **Mô hình 2: Matrix Factorization via TruncatedSVD (Gợi ý Cá nhân hóa):**
* *Mục đích:* Phục vụ cho Trang chủ (`HomePage.tsx`) dưới mục "Gợi ý dành riêng cho bạn" (Top-10 Recommendation).
* *Thuật toán:* Xây dựng ma trận thưa User-Item $R \in \mathbb{R}^{M \times N}$ ($M$ người dùng, $N$ sản phẩm). Áp dụng phân rã ma trận giá trị suy biến:

$$R \approx U \Sigma V^T = P \times Q^T$$



với $k$ latent dimensions (mặc định $k=20$).
* *Dự đoán điểm:* $\hat{R}_{u, i} = P_u \cdot Q_i^T$. Lọc bỏ các sản phẩm người dùng đã mua/đánh giá, chọn ra 10 sản phẩm có điểm $\hat{R}_{u, i}$ cao nhất.


3. **Cơ chế Fallback (Cold-Start Problem):**
* Đối với người dùng chưa có lịch sử tương tác (`user_id` mới), hệ thống tự động fallback về danh sách Top-10 sản phẩm có số lượt đánh giá cao nhất và điểm trung bình $\ge 4.5$ sao trong danh mục.



---

### 3. Kết quả đầu ra của Bước 1

Sau khi hoàn thành Bước 1, hệ thống thu được 3 nhóm tài sản dữ liệu:

1. **Bộ Dataset sạch chuẩn hóa:**
* `data/processed/clean_products.parquet`: Chứa đúng 1,000 sản phẩm nhạc cụ với schema chuẩn: `product_id`, `name`, `category`, `price`, `thumbnail_url`, `description`, `rating`, `rating_count`, `stock_quantity`.
* `data/processed/clean_interactions.parquet`: Chứa 5,000 bản ghi tương tác sạch (`user_id`, `product_id`, `rating`, `timestamp`).
* `data/processed/seed_products.sql`: File script SQL chứa các câu lệnh `INSERT INTO products (...)` tự động sinh ra từ tập 1,000 sản phẩm, sẵn sàng để nạp trực tiếp vào PostgreSQL (dùng cho Service Giỏ hàng và Quản trị đơn hàng ở Bước 2).


2. **Mô hình Machine Learning và Trọng số (Artifacts):**
* `models/item_similarity.npz`: Ma trận đối xứng $1000 \times 1000$ lưu độ tương đồng giữa các nhạc cụ.
* `models/svd_recommender.pkl`: Đối tượng chứa ma trận trọng số người dùng ($P$), ma trận trọng số sản phẩm ($Q$), kèm theo từ điển ánh xạ chỉ số (`user2idx`, `idx2user`, `item2idx`, `idx2item`).
* Các tệp này được đồng bộ trực tiếp lên Azure Blob Storage tại container `model-artifacts` để phục vụ việc reload model độc lập.


3. **Dữ liệu Precomputed Recommendations nạp sẵn vào Azure Cosmos DB:**
* Container `user_recommendations`: Mỗi tài liệu đại diện cho 1 người dùng, chứa danh sách mảng 10 sản phẩm được tính sẵn.
* Container `item_recommendations`: Mỗi tài liệu đại diện cho 1 sản phẩm, chứa danh sách top 5 sản phẩm thường mua cùng (Bundles).
* Container `system_metadata`: Chứa 1 tài liệu duy nhất lưu Top sản phẩm thịnh hành (Popular Items) dùng làm fallback cho người dùng mới.



---

### 4. Interface kết nối sang các bước sau

Bước 1 đóng vai trò cung cấp dữ liệu và mô hình cho các Microservices và Frontend thông qua 4 chuẩn Interface:

#### A. Interface Lưu trữ NoSQL (Cosmos DB Documents Schema)

Phục vụ trực tiếp cho `Recommender Service (Port 8003)` truy vấn với thời gian $O(1)$:

*Document trong Container `user_recommendations` (Partition Key: `/user_id`):*

```json
{
  "id": "A3V6Z4R53JWSKV",
  "user_id": "A3V6Z4R53JWSKV",
  "recommendations": [
    { "product_id": "B0002E1G5C", "score": 4.88, "rank": 1 },
    { "product_id": "B0002F7K7Y", "score": 4.75, "rank": 2 }
  ],
  "model_version": "v1.0-svd",
  "updated_at": "2026-11-08T13:00:00Z"
}

```

*Document trong Container `item_recommendations` (Partition Key: `/product_id`):*

```json
{
  "id": "B0002E1G5C",
  "product_id": "B0002E1G5C",
  "frequently_bought_together": [
    { "product_id": "B0002GLDZC", "similarity_score": 0.94, "bundle_type": "accessory" },
    { "product_id": "B00186AD70", "similarity_score": 0.87, "bundle_type": "co-purchase" }
  ],
  "updated_at": "2026-11-08T13:00:00Z"
}

```

#### B. Interface Cơ sở dữ liệu Quan hệ (PostgreSQL Table Schema)

Phục vụ cho `Auth Service (Port 8001)` và `Order/Cart Service (Port 8002)`:

* Bảng `products`: `id` (VARCHAR PK = `product_id`), `name` (VARCHAR), `category` (VARCHAR), `price` (NUMERIC), `image_url` (TEXT), `stock_quantity` (INT, mặc định 100 để kiểm thử Concurrency Lock), `description` (TEXT).

#### C. Interface Model Serving (Recommender API Endpoints)

Quy định sẵn cấu trúc JSON response mà service `recommender_service` sẽ trả về cho Frontend React:

* `GET /api/v1/recommendations/{user_id}`: Trả về danh sách chi tiết các sản phẩm được đề xuất cho user.
* `GET /api/v1/products/{product_id}/frequently-bought-together`: Trả về danh sách bundle kèm theo.

---

### 5. Mã nguồn Quản lý Hạ tầng bằng Code (IaC) & Cấu hình môi trường

#### File `.env.example`

Tệp định nghĩa và hướng dẫn toàn bộ khóa kết nối, cấu hình lưu trữ đám mây và siêu tham số mô hình:

```bash
# ==============================================================================
# HỆ THỐNG GỢI Ý THƯƠNG MẠI ĐIỆN TỬ (ECOMMERCE RECOMMENDER SYSTEM)
# Tệp mẫu cấu hình môi trường (.env.example)
# Sao chép tệp này thành .env và điền các giá trị thực tế trước khi chạy hệ thống.
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. CẤU HÌNH AZURE BLOB STORAGE (LƯU TRỮ DỮ LIỆU THÔ, LOGS VÀ ARTIFACTS MÔ HÌNH)
# Cách lấy: Azure Portal -> Storage Accounts -> Chọn tài khoản -> Security + networking -> Access keys
# ------------------------------------------------------------------------------
AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=<your_storage_account_name>;AccountKey=<your_storage_account_key>;EndpointSuffix=core.windows.net"
AZURE_STORAGE_ACCOUNT_NAME="<your_storage_account_name>"
AZURE_STORAGE_ACCOUNT_KEY="<your_storage_account_key>"

# Tên các Blob Containers sẽ được tạo tự động bởi script init
BLOB_CONTAINER_RAW_DATA="raw-data"
BLOB_CONTAINER_PROCESSED_DATA="processed-data"
BLOB_CONTAINER_MODEL_ARTIFACTS="model-artifacts"
BLOB_CONTAINER_INTERACTION_LOGS="interaction-logs"

# ------------------------------------------------------------------------------
# 2. CẤU HÌNH AZURE COSMOS DB (NOSQL DATABASE PHỤC VỤ DỮ LIỆU GỢI Ý TỐC ĐỘ CAO)
# Cách lấy: Azure Portal -> Azure Cosmos DB -> Chọn tài khoản NoSQL -> Keys -> URI & Primary Key
# Lưu ý: Bật tính năng 'Free Tier Discount' trên gói Azure for Students (1000 RU/s & 25GB miễn phí)
# ------------------------------------------------------------------------------
COSMOS_DB_ENDPOINT="https://<your-cosmos-account-name>.documents.azure.com:443/"
COSMOS_DB_PRIMARY_KEY="<your_cosmos_primary_master_key>=="
COSMOS_DB_DATABASE_NAME="ecommerce_recommender_db"

# Tên các Containers trong Cosmos DB NoSQL
COSMOS_CONTAINER_USER_RECS="user_recommendations"
COSMOS_CONTAINER_ITEM_RECS="item_recommendations"
COSMOS_CONTAINER_METADATA="system_metadata"

# Throughput cấu hình cho Database (RU/s). Để 400 hoặc 1000 RU/s để tối ưu chi phí học tập
COSMOS_DATABASE_THROUGHPUT=400

# ------------------------------------------------------------------------------
# 3. CẤU HÌNH POSTGRESQL (DÙNG CHO AUTH SERVICE & ORDER/CART SERVICE)
# Cách lấy: Thông tin kết nối Azure Database for PostgreSQL Flexible Server hoặc Docker cục bộ
# ------------------------------------------------------------------------------
POSTGRES_HOST="localhost"
POSTGRES_PORT=5432
POSTGRES_DB="ecommerce_shop_db"
POSTGRES_USER="postgres_admin"
POSTGRES_PASSWORD="YourSecurePasswordHere123!"
POSTGRES_SSL_MODE="require"

# ------------------------------------------------------------------------------
# 4. THAM SỐ HUẤN LUYỆN PIPELINE MACHINE LEARNING
# ------------------------------------------------------------------------------
ML_TARGET_CATEGORY="Musical_Instruments"
ML_NUM_PRODUCTS=1000
ML_NUM_INTERACTIONS=5000
ML_SVD_FACTORS=20
ML_TOP_K_RECOMMENDATIONS=10
ML_RANDOM_STATE=42

# ------------------------------------------------------------------------------
# 5. HUGGING FACE DATASET CONFIG (NẾU STREAMING TRỰC TIẾP TỪ HUB)
# ------------------------------------------------------------------------------
HF_DATASET_NAME="McAuley-Lab/Amazon-Reviews-2023"
HF_CATEGORY_SUBSET="Musical_Instruments"

```

---

#### File `scripts/init_azure_storage.py`

Mã nguồn Python quản lý toàn bộ hạ tầng lưu trữ (Azure Cosmos DB NoSQL và Azure Blob Storage) bằng code, có cơ chế kiểm tra trùng lặp và tự động thiết lập đúng Partition Key:

```python
"""
scripts/init_azure_storage.py
Mục đích: Tự động khởi tạo hạ tầng Cloud Storage & NoSQL Database cho dự án E-commerce Recommender.
Không cần thao tác thủ công trên giao diện Azure Portal.
"""

import os
import sys
from dotenv import load_dotenv
from azure.core.exceptions import ResourceExistsError, HttpResponseError
from azure.storage.blob import BlobServiceClient
from azure.cosmos import CosmosClient, PartitionKey, ThroughputProperties

# Nạp biến môi trường từ .env
load_dotenv()

# Lấy cấu hình Azure Blob Storage
BLOB_CONN_STR = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
BLOB_CONTAINERS = [
    os.getenv("BLOB_CONTAINER_RAW_DATA", "raw-data"),
    os.getenv("BLOB_CONTAINER_PROCESSED_DATA", "processed-data"),
    os.getenv("BLOB_CONTAINER_MODEL_ARTIFACTS", "model-artifacts"),
    os.getenv("BLOB_CONTAINER_INTERACTION_LOGS", "interaction-logs"),
]

# Lấy cấu hình Azure Cosmos DB
COSMOS_ENDPOINT = os.getenv("COSMOS_DB_ENDPOINT")
COSMOS_KEY = os.getenv("COSMOS_DB_PRIMARY_KEY")
COSMOS_DB_NAME = os.getenv("COSMOS_DB_DATABASE_NAME", "ecommerce_recommender_db")
COSMOS_THROUGHPUT = int(os.getenv("COSMOS_DATABASE_THROUGHPUT", "400"))

COSMOS_CONTAINERS_CONFIG = [
    {
        "id": os.getenv("COSMOS_CONTAINER_USER_RECS", "user_recommendations"),
        "partition_key": "/user_id",
    },
    {
        "id": os.getenv("COSMOS_CONTAINER_ITEM_RECS", "item_recommendations"),
        "partition_key": "/product_id",
    },
    {
        "id": os.getenv("COSMOS_CONTAINER_METADATA", "system_metadata"),
        "partition_key": "/id",
    },
]


def init_blob_storage():
    """Khởi tạo các Containers trong Azure Blob Storage."""
    print("\n--- [1/2] ĐANG KHỞI TẠO AZURE BLOB STORAGE CONTAINERS ---")
    if not BLOB_CONN_STR or "your_storage_account" in BLOB_CONN_STR:
        print("[-] Lỗi: Chưa cung cấp AZURE_STORAGE_CONNECTION_STRING hợp lệ trong file .env")
        return False

    try:
        blob_service_client = BlobServiceClient.from_connection_string(BLOB_CONN_STR)
        for container_name in BLOB_CONTAINERS:
            try:
                container_client = blob_service_client.create_container(container_name)
                print(f"[+] Đã tạo thành công Blob Container: '{container_name}'")
            except ResourceExistsError:
                print(f"[*] Blob Container '{container_name}' đã tồn tại từ trước (Bỏ qua).")
        return True
    except Exception as e:
        print(f"[-] Khởi tạo Blob Storage thất bại: {str(e)}")
        return False


def init_cosmos_db():
    """Khởi tạo Database và các Containers trong Azure Cosmos DB NoSQL."""
    print("\n--- [2/2] ĐANG KHỞI TẠO AZURE COSMOS DB NOSQL ---")
    if not COSMOS_ENDPOINT or not COSMOS_KEY or "your-cosmos-account" in COSMOS_ENDPOINT:
        print("[-] Lỗi: Chưa cấu hình COSMOS_DB_ENDPOINT hoặc COSMOS_DB_PRIMARY_KEY trong .env")
        return False

    try:
        cosmos_client = CosmosClient(COSMOS_ENDPOINT, credential=COSMOS_KEY)

        # 1. Tạo Database cấp phát thông lượng dùng chung (Shared Throughput)
        try:
            database = cosmos_client.create_database(
                id=COSMOS_DB_NAME,
                offer_throughput=ThroughputProperties(auto_upgrade_max_throughput=False, offer_throughput=COSMOS_THROUGHPUT)
            )
            print(f"[+] Đã tạo Database Cosmos DB: '{COSMOS_DB_NAME}' với thông lượng {COSMOS_THROUGHPUT} RU/s.")
        except ResourceExistsError:
            database = cosmos_client.get_database_client(COSMOS_DB_NAME)
            print(f"[*] Database Cosmos DB '{COSMOS_DB_NAME}' đã tồn tại từ trước.")

        # 2. Tạo từng Container với Partition Key tương ứng
        for c_config in COSMOS_CONTAINERS_CONFIG:
            container_id = c_config["id"]
            pk_path = c_config["partition_key"]
            try:
                database.create_container(
                    id=container_id,
                    partition_key=PartitionKey(path=pk_path)
                )
                print(f"[+] Đã tạo Cosmos Container: '{container_id}' (Partition Key: {pk_path})")
            except ResourceExistsError:
                print(f"[*] Cosmos Container '{container_id}' đã tồn tại từ trước (Bỏ qua).")

        return True
    except HttpResponseError as http_err:
        print(f"[-] Lỗi HTTP kết nối Cosmos DB: {http_err.message}")
        return False
    except Exception as e:
        print(f"[-] Khởi tạo Cosmos DB thất bại: {str(e)}")
        return False


if __name__ == "__main__":
    print("==================================================================")
    print("KHỞI TẠO HẠ TẦNG LƯU TRỮ VÀ DATABASE TỰ ĐỘNG BẰNG PYTHON CODE")
    print("==================================================================")
    blob_ok = init_blob_storage()
    cosmos_ok = init_cosmos_db()

    if blob_ok and cosmos_ok:
        print("\n[V] TOÀN BỘ HẠ TẦNG ĐÃ ĐƯỢC THIẾT LẬP THÀNH CÔNG, SẴN SÀNG CHO BƯỚC ETL.")
    else:
        print("\n[X] QUÁ TRÌNH KHỞI TẠO CÓ LỖI, VUI LÒNG KIỂM TRA LẠI THÔNG TIN CREDENTIALS TRONG FILE .ENV.")
        sys.exit(1)

```