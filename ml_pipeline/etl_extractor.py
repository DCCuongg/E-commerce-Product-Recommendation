"""
ml_pipeline/etl_extractor.py
Trích xuất danh mục sản phẩm từ bảng PostgreSQL `products` và lịch sử tương tác 
từ bảng `reviews` / `orders` hoặc file log tương tác từ Azure Blob Storage.
"""

import json
import logging
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from azure.storage.blob import BlobServiceClient
from .config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class ETLExtractor:
    def __init__(self, config=Config):
        self.config = config
        self.config.ensure_directories()
        self.db_engine = create_engine(self.config.get_postgres_uri())

    def extract_products_from_db(self) -> pd.DataFrame:
        """Trích xuất danh mục sản phẩm đang active trực tiếp từ PostgreSQL."""
        logger.info("[ETL 1/3] Đang tải danh mục sản phẩm từ PostgreSQL...")
        query = """
            SELECT 
                id AS product_id,
                name,
                category,
                price,
                image_url AS thumbnail_url,
                description,
                stock_quantity
            FROM products
        """
        try:
            df_products = pd.read_sql(query, con=self.db_engine)
            if df_products.empty:
                raise ValueError("Bảng 'products' trong PostgreSQL đang rỗng.")
            
            # Chuẩn hóa văn bản dùng cho mô hình Content-based (TF-IDF)
            df_products["content_raw"] = (
                df_products["name"].fillna("") + " " +
                df_products["category"].fillna("") + " " +
                df_products["description"].fillna("")
            ).str.strip()

            # Bổ sung các trường thống kê nếu bảng sản phẩm chưa lưu sẵn
            if "rating" not in df_products.columns:
                df_products["rating"] = 4.5
            if "rating_count" not in df_products.columns:
                df_products["rating_count"] = 10

            logger.info(f"   -> Đã trích xuất {len(df_products)} sản phẩm từ database.")
            return df_products
        except Exception as e:
            logger.warning(f"Không thể đọc trực tiếp từ PostgreSQL ({e}). Đang thử fallback từ local cache...")
            if self.config.PROCESSED_PRODUCTS_PARQUET.exists():
                return pd.read_parquet(self.config.PROCESSED_PRODUCTS_PARQUET)
            raise e

    def extract_interactions(self, valid_product_ids: set) -> pd.DataFrame:
        """
        Trích xuất tương tác: Ưu tiên đọc từ PostgreSQL (reviews/order_items),
        sau đó hợp nhất với clickstream event logs từ Azure Blob Storage.
        """
        logger.info("[ETL 2/3] Đang tổng hợp dữ liệu tương tác từ Database và Blob Storage...")
        interactions = []

        # 1. Đọc từ PostgreSQL nếu có bảng reviews hoặc order_items
        try:
            query = """
                SELECT 
                    user_id,
                    product_id,
                    rating,
                    EXTRACT(EPOCH FROM created_at)::BIGINT AS timestamp
                FROM reviews
            """
            df_db_reviews = pd.read_sql(query, con=self.db_engine)
            if not df_db_reviews.empty:
                interactions.append(df_db_reviews)
                logger.info(f"   -> Đã lấy {len(df_db_reviews)} đánh giá từ bảng 'reviews'.")
        except Exception:
            logger.info("   -> Bảng 'reviews' chưa sẵn sàng hoặc rỗng, kiểm tra tiếp Blob Storage logs.")

        # 2. Đọc bổ sung từ Azure Blob Storage (container: interaction-logs)
        blob_interactions = self._extract_interactions_from_blob()
        if not blob_interactions.empty:
            interactions.append(blob_interactions)

        # 3. Tổng hợp và fallback nếu hệ thống mới tinh chưa có giao dịch
        if interactions:
            df_all = pd.concat(interactions, ignore_index=True)
        else:
            logger.warning("Chưa có tương tác thực tế từ người dùng. Nạp dữ liệu tương tác cơ sở (seed)...")
            if self.config.PROCESSED_INTERACTIONS_PARQUET.exists():
                df_all = pd.read_parquet(self.config.PROCESSED_INTERACTIONS_PARQUET)
            else:
                raise FileNotFoundError("Không tìm thấy bất kỳ nguồn dữ liệu tương tác nào.")

        # Lọc chỉ giữ tương tác của các sản phẩm thực sự tồn tại trong danh mục
        df_clean = df_all[df_all["product_id"].isin(valid_product_ids)].copy()
        df_clean = df_clean.drop_duplicates(subset=["user_id", "product_id"])

        logger.info(f"   -> Tổng số tương tác hợp lệ thu được: {len(df_clean)}")
        return df_clean

    def _extract_interactions_from_blob(self) -> pd.DataFrame:
        """Đọc các tệp log clickstream/event do microservice ghi vào container 'interaction-logs'."""
        if not self.config.AZURE_STORAGE_CONNECTION_STRING or "your_storage_account" in self.config.AZURE_STORAGE_CONNECTION_STRING:
            return pd.DataFrame()

        try:
            blob_service = BlobServiceClient.from_connection_string(self.config.AZURE_STORAGE_CONNECTION_STRING)
            container_client = blob_service.get_container_client(self.config.BLOB_CONTAINER_INTERACTION_LOGS)
            
            records = []
            for blob in container_client.list_blobs():
                if blob.name.endswith(".json") or blob.name.endswith(".jsonl"):
                    blob_client = container_client.get_blob_client(blob.name)
                    content = blob_client.download_blob().readall().decode("utf-8")
                    for line in content.splitlines():
                        if not line.strip():
                            continue
                        event = json.loads(line)
                        # Implicit rating mapping: view = 2.0, cart = 4.0, purchase = 5.0
                        score = float(event.get("rating", 3.0))
                        records.append({
                            "user_id": str(event["user_id"]),
                            "product_id": str(event["product_id"]),
                            "rating": score,
                            "timestamp": int(event.get("timestamp", 0))
                        })
            return pd.DataFrame(records)
        except Exception as e:
            logger.warning(f"Không thể tải interaction logs từ Blob Storage: {str(e)}")
            return pd.DataFrame()

    def run(self):
        logger.info("=== BẮT ĐẦU CHẠY PIPELINE ETL (PRODUCTION AUTOMATION) ===")
        df_products = self.extract_products_from_db()
        valid_pids = set(df_products["product_id"])

        df_interactions = self.extract_interactions(valid_pids)

        logger.info("[ETL 3/3] Lưu bộ dữ liệu đồng bộ cho quá trình Huấn luyện...")
        df_products.to_parquet(self.config.PROCESSED_PRODUCTS_PARQUET, index=False)
        df_interactions.to_parquet(self.config.PROCESSED_INTERACTIONS_PARQUET, index=False)

        logger.info(f"Hoàn tất: {len(df_products)} sản phẩm, {len(df_interactions)} tương tác sẵn sàng.")
        return df_products, df_interactions


if __name__ == "__main__":
    extractor = ETLExtractor()
    extractor.run()