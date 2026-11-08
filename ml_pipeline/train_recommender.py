"""
ml_pipeline/train_recommender.py
Huấn luyện mô hình Hybrid Item Similarity và Matrix Factorization SVD.
Sau khi hoàn tất, tự động upload model artifacts lên Azure Blob Storage (container: model-artifacts).
"""

import pickle
import logging
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.decomposition import TruncatedSVD
from azure.storage.blob import BlobServiceClient
from .config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class RecommenderTrainer:
    def __init__(self, config=Config):
        self.config = config
        self.config.ensure_directories()

    def load_data(self):
        if not self.config.PROCESSED_PRODUCTS_PARQUET.exists() or not self.config.PROCESSED_INTERACTIONS_PARQUET.exists():
            raise FileNotFoundError("Thiếu dữ liệu sạch. Vui lòng chạy etl_extractor.py trước!")

        df_products = pd.read_parquet(self.config.PROCESSED_PRODUCTS_PARQUET)
        df_interactions = pd.read_parquet(self.config.PROCESSED_INTERACTIONS_PARQUET)
        return df_products, df_interactions

    def train_item_similarity(self, df_products: pd.DataFrame, df_interactions: pd.DataFrame, i2idx: dict):
        """Model 1: Item-to-Item Similarity (TF-IDF Content + Co-occurrence hành vi)."""
        logger.info("[TRAIN 1/2] Huấn luyện Model 1: Item-to-Item Hybrid Similarity...")

        # 1. TF-IDF trích xuất từ dữ liệu sản phẩm trong DB
        tfidf = TfidfVectorizer(max_features=2500, stop_words="english")
        tfidf_mat = tfidf.fit_transform(df_products["content_raw"].fillna(""))
        content_sim = cosine_similarity(tfidf_mat)

        # 2. Ma trận đồng tương tác (Co-occurrence) dựa trên lịch sử mua/xem cùng giỏ
        n_items = len(i2idx)
        co_matrix = np.zeros((n_items, n_items), dtype=np.float32)

        user_grouped = df_interactions.groupby("user_id")["product_id"].apply(list)
        for item_list in user_grouped:
            if len(item_list) > 1:
                indices = [i2idx[p] for p in item_list if p in i2idx]
                for a in indices:
                    for b in indices:
                        if a != b:
                            co_matrix[a, b] += 1.0

        co_norms = np.linalg.norm(co_matrix, axis=1, keepdims=True)
        co_norms[co_norms == 0] = 1.0
        co_sim = (co_matrix @ co_matrix.T) / (co_norms @ co_norms.T)
        np.fill_diagonal(co_sim, 1.0)

        # Trộn theo tỷ lệ Hybrid
        alpha = self.config.HYBRID_ALPHA
        hybrid_sim = alpha * co_sim + (1.0 - alpha) * content_sim
        np.fill_diagonal(hybrid_sim, 1.0)

        np.savez_compressed(self.config.ITEM_SIMILARITY_PATH, similarity=hybrid_sim)
        logger.info(f"   -> Đã lưu ma trận tương đồng tại: {self.config.ITEM_SIMILARITY_PATH}")
        return hybrid_sim

    def train_svd(self, df_interactions: pd.DataFrame, u2idx: dict, i2idx: dict):
        """Model 2: Matrix Factorization TruncatedSVD trên ma trận thưa User-Item."""
        logger.info("[TRAIN 2/2] Huấn luyện Model 2: TruncatedSVD Matrix Factorization...")

        rows = [u2idx[u] for u in df_interactions["user_id"]]
        cols = [i2idx[i] for i in df_interactions["product_id"]]
        ratings = df_interactions["rating"].values

        R_mat = csr_matrix((ratings, (rows, cols)), shape=(len(u2idx), len(i2idx)))
        actual_k = min(self.config.ML_SVD_FACTORS, min(R_mat.shape) - 1)

        svd = TruncatedSVD(n_components=actual_k, random_state=self.config.ML_RANDOM_STATE)
        P = svd.fit_transform(R_mat)
        Q = svd.components_.T

        artifacts = {
            "P": P,
            "Q": Q,
            "user2idx": u2idx,
            "idx2user": {v: k for k, v in u2idx.items()},
            "item2idx": i2idx,
            "idx2item": {v: k for k, v in i2idx.items()},
            "k_factors": actual_k,
            "model_version": "v1.0-svd"
        }

        with open(self.config.SVD_MODEL_PATH, "wb") as f:
            pickle.dump(artifacts, f)

        logger.info(f"   -> Đã lưu SVD model tại: {self.config.SVD_MODEL_PATH}")
        return artifacts

    def upload_artifacts_to_azure(self):
        """Tự động đồng bộ các file model mới lên Azure Blob Storage (container: model-artifacts)."""
        conn_str = self.config.AZURE_STORAGE_CONNECTION_STRING
        if not conn_str or "your_storage_account" in conn_str:
            logger.info("Bỏ qua đồng bộ Cloud: Chưa cấu hình connection string Blob Storage.")
            return

        logger.info("Đang đồng bộ model artifacts lên Azure Blob Storage...")
        try:
            blob_service = BlobServiceClient.from_connection_string(conn_str)
            container_client = blob_service.get_container_client(self.config.BLOB_CONTAINER_MODEL_ARTIFACTS)

            for local_path in [self.config.ITEM_SIMILARITY_PATH, self.config.SVD_MODEL_PATH]:
                blob_client = container_client.get_blob_client(local_path.name)
                with open(local_path, "rb") as data:
                    blob_client.upload_blob(data, overwrite=True)
                logger.info(f"   -> Đã upload '{local_path.name}' lên container '{self.config.BLOB_CONTAINER_MODEL_ARTIFACTS}'.")
        except Exception as e:
            logger.error(f"Lỗi khi upload artifacts lên Azure Blob: {str(e)}")

    def run(self):
        logger.info("=== BẮT ĐẦU HUẤN LUYỆN PIPELINE ===")
        df_products, df_interactions = self.load_data()

        user_list = df_interactions["user_id"].unique()
        item_list = df_products["product_id"].unique()

        u2idx = {u: i for i, u in enumerate(user_list)}
        i2idx = {it: i for i, it in enumerate(item_list)}

        self.train_item_similarity(df_products, df_interactions, i2idx)
        self.train_svd(df_interactions, u2idx, i2idx)
        self.upload_artifacts_to_azure()
        logger.info("=== HUẤN LUYỆN VÀ ĐỒNG BỘ ARTIFACTS HOÀN TẤT ===")


if __name__ == "__main__":
    trainer = RecommenderTrainer()
    trainer.run()