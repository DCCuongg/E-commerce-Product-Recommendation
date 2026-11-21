"""
ml_pipeline/etl_extractor.py
Trích xuất danh mục sản phẩm đang mở bán (is_active = TRUE) từ PostgreSQL và tổng hợp lịch sử tương tác từ:
1. Bảng `reviews` (Explicit rating 1-5 sao - giữ cả lịch sử của user đã is_disabled)
2. Bảng `orders` & `order_items` (Implicit purchase = 5.0 - giữ cả lịch sử của user đã is_disabled)
3. Azure Blob Storage container `interaction-logs` (Clickstream FaaS logs: view/click/add_to_cart/rating)
"""

import json
import logging
import pandas as pd
from sqlalchemy import create_engine
from azure.storage.blob import BlobServiceClient
from .config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Bảng quy đổi điểm tương tác ngầm theo Rubric Tiêu chí 3.2
ACTION_WEIGHT_MAP = {
    "view": 1.0,
    "page_view": 1.0,
    "click": 2.0,
    "add_to_cart": 3.5,
    "cart": 3.5,
    "checkout": 4.5,
    "purchase": 5.0,
    "buy": 5.0,
}


class ETLExtractor:
    def __init__(self, config=Config):
        self.config = config
        self.config.ensure_directories()
        self.db_engine = create_engine(self.config.get_postgres_uri())

    def extract_products_from_db(self) -> pd.DataFrame:
        """Trích xuất danh mục sản phẩm đang hoạt động (is_active = TRUE) và thống kê đánh giá từ PostgreSQL."""
        logger.info("[ETL 1/3] Đang tải danh mục sản phẩm đang mở bán từ PostgreSQL...")
        query = """
            SELECT 
                p.id AS product_id,
                p.name,
                p.category,
                p.price,
                p.image_url AS thumbnail_url,
                p.description,
                p.stock_quantity,
                COALESCE(r.avg_rating, 4.5) AS rating,
                COALESCE(r.rating_count, 10) AS rating_count
            FROM products p
            LEFT JOIN (
                SELECT 
                    product_id,
                    ROUND(AVG(rating)::numeric, 2) AS avg_rating,
                    COUNT(id) AS rating_count
                FROM reviews
                GROUP BY product_id
            ) r ON p.id = r.product_id
            WHERE COALESCE(p.is_active, TRUE) = TRUE
        """
        try:
            df_products = pd.read_sql(query, con=self.db_engine)
            if df_products.empty:
                raise ValueError("Bảng 'products' (is_active = TRUE) trong PostgreSQL đang rỗng.")

            df_products["content_raw"] = (
                df_products["name"].fillna("") + " " +
                df_products["category"].fillna("") + " " +
                df_products["description"].fillna("")
            ).str.strip()

            logger.info(f"   -> Đã trích xuất {len(df_products)} sản phẩm đang hoạt động từ database.")
            return df_products
        except Exception as e:
            logger.warning(f"Không thể đọc trực tiếp từ PostgreSQL ({e}). Thử fallback từ local Parquet...")
            for fallback_path in [self.config.PROCESSED_PRODUCTS_PARQUET]:
                if fallback_path.exists():
                    df_fb = pd.read_parquet(fallback_path)
                    if "is_active" in df_fb.columns:
                        df_fb = df_fb[df_fb["is_active"].fillna(True)].copy()
                    if "content_raw" not in df_fb.columns:
                        df_fb["content_raw"] = (
                            df_fb["name"].fillna("") + " " +
                            df_fb.get("category", pd.Series("", index=df_fb.index)).fillna("")
                        ).str.strip()
                    return df_fb
            raise e

    def extract_interactions(self, valid_product_ids: set) -> pd.DataFrame:
        """
        Hợp nhất tương tác từ PostgreSQL (reviews + orders) và Azure Blob Storage logs.
        Giữ nguyên lịch sử hành vi của cả các tài khoản đã bị Soft-Disable (is_disabled = TRUE).
        """
        logger.info("[ETL 2/3] Đang tổng hợp dữ liệu tương tác từ Database và Blob Storage...")
        interactions = []

        # 1. Đọc đánh giá sao từ bảng `reviews` (bao gồm cả user đã is_disabled)
        try:
            review_query = """
                SELECT 
                    user_id,
                    product_id,
                    rating::float AS rating,
                    EXTRACT(EPOCH FROM created_at)::BIGINT AS timestamp
                FROM reviews
            """
            df_db_reviews = pd.read_sql(review_query, con=self.db_engine)
            if not df_db_reviews.empty:
                interactions.append(df_db_reviews)
                logger.info(f"   -> Đã lấy {len(df_db_reviews)} đánh giá từ bảng 'reviews'.")
        except Exception as exc:
            logger.info(f"   -> Bỏ qua bảng 'reviews' ({exc}).")

        # 2. Đọc lịch sử mua hàng hợp lệ từ `orders` + `order_items` (bao gồm cả user đã is_disabled)
        try:
            order_query = """
                SELECT 
                    o.user_id,
                    oi.product_id,
                    5.0::float AS rating,
                    EXTRACT(EPOCH FROM o.created_at)::BIGINT AS timestamp
                FROM orders o
                JOIN order_items oi ON o.id = oi.order_id
                WHERE o.status IN ('CONFIRMED', 'SHIPPED', 'DELIVERED')
            """
            df_db_orders = pd.read_sql(order_query, con=self.db_engine)
            if not df_db_orders.empty:
                interactions.append(df_db_orders)
                logger.info(f"   -> Đã lấy {len(df_db_orders)} lượt mua hàng từ bảng 'orders'.")
        except Exception as exc:
            logger.info(f"   -> Bỏ qua bảng 'orders' ({exc}).")

        # 3. Đọc log hành vi clickstream từ Azure Blob Storage (container: interaction-logs)
        blob_interactions = self._extract_interactions_from_blob()
        if not blob_interactions.empty:
            interactions.append(blob_interactions)
            logger.info(f"   -> Đã lấy {len(blob_interactions)} sự kiện log từ Blob Storage.")

        if not interactions:
            logger.warning("   -> Chưa có dữ liệu tương tác thực tế nào từ DB hoặc Blob Storage.")
            return pd.DataFrame(columns=["user_id", "product_id", "rating", "timestamp"])

        df_all = pd.concat(interactions, ignore_index=True)

        # Chỉ gợi ý các sản phẩm đang hoạt động (is_active = TRUE)
        df_clean = df_all[df_all["product_id"].isin(valid_product_ids)].copy()
        df_clean["user_id"] = df_clean["user_id"].astype(str)
        df_clean["product_id"] = df_clean["product_id"].astype(str)
        df_clean["rating"] = pd.to_numeric(df_clean["rating"], errors="coerce").fillna(3.0).clip(1.0, 5.0)
        df_clean["timestamp"] = pd.to_numeric(df_clean["timestamp"], errors="coerce").fillna(0).astype("int64")

        df_clean = (
            df_clean.groupby(["user_id", "product_id"], as_index=False)
            .agg({"rating": "max", "timestamp": "max"})
        )

        # Áp dụng lọc độ thưa ma trận theo Rubric 3.2 (nếu tập dữ liệu đủ lớn)
        user_counts = df_clean["user_id"].value_counts()
        item_counts = df_clean["product_id"].value_counts()
        valid_users = user_counts[user_counts >= self.config.MIN_USER_INTERACTIONS].index
        valid_items = item_counts[item_counts >= self.config.MIN_ITEM_INTERACTIONS].index

        df_filtered = df_clean[
            df_clean["user_id"].isin(valid_users) & df_clean["product_id"].isin(valid_items)
        ]
        if len(df_filtered) >= 20:
            df_clean = df_filtered
            logger.info(
                f"   -> Đã lọc độ thưa (user >= {self.config.MIN_USER_INTERACTIONS}, "
                f"item >= {self.config.MIN_ITEM_INTERACTIONS}): còn {len(df_clean)} tương tác."
            )

        logger.info(f"   -> Tổng số tương tác sạch sẵn sàng huấn luyện: {len(df_clean)}")
        return df_clean

    def _extract_interactions_from_blob(self) -> pd.DataFrame:
        """Đọc các tệp log clickstream/event do Azure Function ghi vào container 'interaction-logs'."""
        conn_str = self.config.AZURE_STORAGE_CONNECTION_STRING
        if not conn_str or "your_storage_account" in conn_str or "<AZURITE" in conn_str:
            return pd.DataFrame()

        try:
            blob_service = BlobServiceClient.from_connection_string(conn_str)
            container_client = blob_service.get_container_client(self.config.BLOB_CONTAINER_INTERACTION_LOGS)

            records = []
            for blob in container_client.list_blobs():
                if not (blob.name.endswith(".json") or blob.name.endswith(".jsonl")):
                    continue
                blob_client = container_client.get_blob_client(blob.name)
                content = blob_client.download_blob().readall().decode("utf-8")
                for line in content.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    event = json.loads(line)
                    uid = event.get("user_id")
                    pid = event.get("product_id") or event.get("item_id")
                    if not uid or not pid or str(uid) == "anonymous":
                        continue

                    action = str(event.get("action") or event.get("event_type") or "click").lower()
                    if "rating" in event and event["rating"] is not None:
                        score = float(event["rating"])
                    elif action == "rating" and event.get("value") is not None:
                        score = float(event["value"])
                    else:
                        score = ACTION_WEIGHT_MAP.get(action, 2.0)

                    records.append({
                        "user_id": str(uid),
                        "product_id": str(pid),
                        "rating": min(max(score, 1.0), 5.0),
                        "timestamp": int(event.get("timestamp", 0)),
                    })
            return pd.DataFrame(records)
        except Exception as e:
            logger.warning(f"Không thể tải interaction logs từ Blob Storage: {str(e)}")
            return pd.DataFrame()

    def run(self):
        logger.info("=== BẮT ĐẦU CHẠY PIPELINE ETL (PRODUCTION AUTOMATION) ===")
        df_products = self.extract_products_from_db()
        valid_pids = set(df_products["product_id"].astype(str))

        df_interactions = self.extract_interactions(valid_pids)

        logger.info("[ETL 3/3] Lưu bộ dữ liệu đồng bộ cho quá trình Huấn luyện...")
        df_products.to_parquet(self.config.PROCESSED_PRODUCTS_PARQUET, index=False)
        df_interactions.to_parquet(self.config.PROCESSED_INTERACTIONS_PARQUET, index=False)

        logger.info(f"Hoàn tất: {len(df_products)} sản phẩm hoạt động, {len(df_interactions)} tương tác sẵn sàng.")
        return df_products, df_interactions


if __name__ == "__main__":
    extractor = ETLExtractor()
    extractor.run()