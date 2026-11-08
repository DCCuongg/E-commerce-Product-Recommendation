"""
ml_pipeline/config.py
Quản lý cấu hình kết nối PostgreSQL, Azure Blob Storage, Azure Cosmos DB và siêu tham số ML.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


class Config:
    # --------------------------------------------------------------------------
    # 1. ĐƯỜNG DẪN DỮ LIỆU CỤC BỘ / ARTIFACTS
    # --------------------------------------------------------------------------
    PROJECT_ROOT: Path = BASE_DIR
    DATA_DIR: Path = BASE_DIR / "data"
    PROCESSED_DATA_DIR: Path = DATA_DIR / "processed"
    MODELS_DIR: Path = BASE_DIR / "models"
    EXPORTS_DIR: Path = BASE_DIR / "exports"

    PROCESSED_PRODUCTS_PARQUET: Path = PROCESSED_DATA_DIR / "clean_products.parquet"
    PROCESSED_INTERACTIONS_PARQUET: Path = PROCESSED_DATA_DIR / "clean_interactions.parquet"
    ITEM_SIMILARITY_PATH: Path = MODELS_DIR / "item_similarity.npz"
    SVD_MODEL_PATH: Path = MODELS_DIR / "svd_recommender.pkl"

    # --------------------------------------------------------------------------
    # 2. CẤU HÌNH POSTGRESQL (NGUỒN DỮ LIỆU CHÍNH CHO PRODUCTS VÀ ORDERS/REVIEWS)
    # --------------------------------------------------------------------------
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "ecommerce_shop_db")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres_admin")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "")
    POSTGRES_SSL_MODE: str = os.getenv("POSTGRES_SSL_MODE", "prefer")

    @classmethod
    def get_postgres_uri(cls) -> str:
        return (
            f"postgresql+psycopg2://{cls.POSTGRES_USER}:{cls.POSTGRES_PASSWORD}"
            f"@{cls.POSTGRES_HOST}:{cls.POSTGRES_PORT}/{cls.POSTGRES_DB}"
            f"?sslmode={cls.POSTGRES_SSL_MODE}"
        )

    # --------------------------------------------------------------------------
    # 3. CẤU HÌNH AZURE BLOB STORAGE
    # --------------------------------------------------------------------------
    AZURE_STORAGE_CONNECTION_STRING: str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    BLOB_CONTAINER_RAW_DATA: str = os.getenv("BLOB_CONTAINER_RAW_DATA", "raw-data")
    BLOB_CONTAINER_PROCESSED_DATA: str = os.getenv("BLOB_CONTAINER_PROCESSED_DATA", "processed-data")
    BLOB_CONTAINER_MODEL_ARTIFACTS: str = os.getenv("BLOB_CONTAINER_MODEL_ARTIFACTS", "model-artifacts")
    BLOB_CONTAINER_INTERACTION_LOGS: str = os.getenv("BLOB_CONTAINER_INTERACTION_LOGS", "interaction-logs")

    # --------------------------------------------------------------------------
    # 4. CẤU HÌNH AZURE COSMOS DB NOSQL
    # --------------------------------------------------------------------------
    COSMOS_ENDPOINT: str = os.getenv("COSMOS_DB_ENDPOINT", "")
    COSMOS_KEY: str = os.getenv("COSMOS_DB_PRIMARY_KEY", "")
    COSMOS_DATABASE_NAME: str = os.getenv("COSMOS_DB_DATABASE_NAME", "ecommerce_recommender_db")
    COSMOS_CONTAINER_USER_RECS: str = os.getenv("COSMOS_CONTAINER_USER_RECS", "user_recommendations")
    COSMOS_CONTAINER_ITEM_RECS: str = os.getenv("COSMOS_CONTAINER_ITEM_RECS", "item_recommendations")
    COSMOS_CONTAINER_METADATA: str = os.getenv("COSMOS_CONTAINER_METADATA", "system_metadata")
    COSMOS_THROUGHPUT: int = int(os.getenv("COSMOS_DATABASE_THROUGHPUT", "400"))

    # --------------------------------------------------------------------------
    # 5. SIÊU THAM SỐ HUẤN LUYỆN ML
    # --------------------------------------------------------------------------
    ML_TARGET_CATEGORY: str = os.getenv("ML_TARGET_CATEGORY", "Musical_Instruments")
    ML_NUM_PRODUCTS: int = int(os.getenv("ML_NUM_PRODUCTS", "1000"))
    ML_NUM_INTERACTIONS: int = int(os.getenv("ML_NUM_INTERACTIONS", "5000"))
    ML_SVD_FACTORS: int = int(os.getenv("ML_SVD_FACTORS", "20"))
    ML_TOP_K_RECOMMENDATIONS: int = int(os.getenv("ML_TOP_K_RECOMMENDATIONS", "10"))
    ML_RANDOM_STATE: int = int(os.getenv("ML_RANDOM_STATE", "42"))
    TOP_K_BUNDLES: int = 5
    HYBRID_ALPHA: float = 0.7

    @classmethod
    def ensure_directories(cls):
        for directory in [cls.PROCESSED_DATA_DIR, cls.MODELS_DIR, cls.EXPORTS_DIR]:
            directory.mkdir(parents=True, exist_ok=True)


Config.ensure_directories()