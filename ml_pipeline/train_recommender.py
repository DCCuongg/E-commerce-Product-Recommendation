"""
ml_pipeline/train_recommender.py
Huấn luyện mô hình Hybrid Item Similarity và Matrix Factorization TruncatedSVD.
Tự động ghi model_manifest.json và upload model artifacts lên Azure Blob Storage (container: model-artifacts).
"""

import json
import logging
import pickle
import time

import numpy as np
import pandas as pd
from azure.storage.blob import BlobServiceClient
from scipy.sparse import csr_matrix
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class RecommenderTrainer:
    def __init__(self, config=Config, model_version: str | None = None):
        self.config = config
        self.model_version = model_version or self.config.MODEL_VERSION
        self.config.ensure_directories()

    def _is_cooldown_passed(self) -> bool:
        """Kiểm tra xem đã đủ 1 tuần (RETRAIN_COOLDOWN_SECONDS) kể từ lần train trước chưa."""
        state_file = self.config.DATA_DIR / "last_train_timestamp.txt"
        if not state_file.exists():
            return True
        try:
            last_run = float(state_file.read_text(encoding="utf-8").strip())
            elapsed = time.time() - last_run
            if elapsed < self.config.RETRAIN_COOLDOWN_SECONDS:
                remaining_days = (self.config.RETRAIN_COOLDOWN_SECONDS - elapsed) / 86400
                logger.info(
                    f"Bỏ qua train: Chưa đủ chu kỳ 1 tuần (còn {remaining_days:.2f} ngày)."
                )
                return False
        except ValueError:
            pass
        return True

    def _record_train_timestamp(self):
        state_file = self.config.DATA_DIR / "last_train_timestamp.txt"
        state_file.write_text(str(time.time()), encoding="utf-8")

    def load_data(self):
        if not self.config.PROCESSED_PRODUCTS_PARQUET.exists() or not self.config.PROCESSED_INTERACTIONS_PARQUET.exists():
            raise FileNotFoundError("Thiếu dữ liệu sạch. Vui lòng chạy etl_extractor.py trước!")

        df_products = pd.read_parquet(self.config.PROCESSED_PRODUCTS_PARQUET)
        df_interactions = pd.read_parquet(self.config.PROCESSED_INTERACTIONS_PARQUET)
        return df_products, df_interactions

    def train_item_similarity(self, df_products: pd.DataFrame, df_interactions: pd.DataFrame, i2idx: dict):
        """Model 1: Item-to-Item Similarity (TF-IDF Content + Co-occurrence hành vi)."""
        logger.info("[TRAIN 1/2] Huấn luyện Model 1: Item-to-Item Hybrid Similarity...")

        tfidf = TfidfVectorizer(max_features=2500, stop_words="english")
        tfidf_mat = tfidf.fit_transform(df_products["content_raw"].fillna(""))
        content_sim = cosine_similarity(tfidf_mat)

        n_items = len(i2idx)
        co_matrix = np.zeros((n_items, n_items), dtype=np.float32)

        user_grouped = df_interactions.groupby("user_id")["product_id"].apply(list)
        for item_list in user_grouped:
            unique_indices = list({i2idx[p] for p in item_list if p in i2idx})
            if len(unique_indices) > 1:
                for a in unique_indices:
                    for b in unique_indices:
                        if a != b:
                            co_matrix[a, b] += 1.0

        co_norms = np.linalg.norm(co_matrix, axis=1, keepdims=True)
        co_norms[co_norms == 0] = 1.0
        co_sim = (co_matrix @ co_matrix.T) / (co_norms @ co_norms.T)
        np.fill_diagonal(co_sim, 1.0)

        alpha = self.config.HYBRID_ALPHA if len(df_interactions) > 10 else 0.0
        hybrid_sim = alpha * co_sim + (1.0 - alpha) * content_sim
        np.fill_diagonal(hybrid_sim, 1.0)

        np.savez_compressed(
            self.config.ITEM_SIMILARITY_PATH,
            similarity=hybrid_sim,
            item_ids=np.array(list(i2idx.keys())),
        )
        logger.info(f"   -> Đã lưu ma trận tương đồng tại: {self.config.ITEM_SIMILARITY_PATH}")
        return hybrid_sim

    def train_svd(self, df_interactions: pd.DataFrame, u2idx: dict, i2idx: dict, force: bool = False):
        """Model 2: Matrix Factorization TruncatedSVD trên ma trận thưa User-Item."""
        logger.info(f"[TRAIN 2/2] Huấn luyện Model 2: TruncatedSVD ({self.model_version})...")

        rows = [u2idx[u] for u in df_interactions["user_id"]]
        cols = [i2idx[i] for i in df_interactions["product_id"]]
        ratings = df_interactions["rating"].values

        R_mat = csr_matrix((ratings, (rows, cols)), shape=(len(u2idx), len(i2idx)))
        if (not force and len(df_interactions) <= self.config.MIN_INTERACTIONS_TO_TRAIN) or min(R_mat.shape) <= 1:
            logger.warning(
                f"Số tương tác ({len(df_interactions)}) <= {self.config.MIN_INTERACTIONS_TO_TRAIN} "
                "hoặc ma trận quá nhỏ, bỏ qua TruncatedSVD."
            )
            P = np.zeros((len(u2idx), 1), dtype=np.float32)
            Q = np.zeros((len(i2idx), 1), dtype=np.float32)
            actual_k = 1
        else:
            max_possible_k = min(R_mat.shape) - 1
            actual_k = max(1, min(self.config.ML_SVD_FACTORS, max_possible_k))
            svd = TruncatedSVD(n_components=actual_k, random_state=self.config.ML_RANDOM_STATE)
            P = svd.fit_transform(R_mat)
            Q = svd.components_.T

        trained_at = time.time()
        artifacts = {
            "P": P,
            "Q": Q,
            "user2idx": u2idx,
            "idx2user": {v: k for k, v in u2idx.items()},
            "item2idx": i2idx,
            "idx2item": {v: k for k, v in i2idx.items()},
            "k_factors": actual_k,
            "model_version": self.model_version,
            "trained_at": trained_at,
        }

        with open(self.config.SVD_MODEL_PATH, "wb") as f:
            pickle.dump(artifacts, f)

        manifest_path = self.config.MODELS_DIR / "model_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "model_version": self.model_version,
                    "trained_at": trained_at,
                    "source": "ml_pipeline_updated",
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        logger.info(
            f"   -> Đã lưu SVD model ({self.model_version}, k={actual_k}) tại: {self.config.SVD_MODEL_PATH}"
        )
        logger.info(f"   -> Đã cập nhật manifest tại: {manifest_path}")
        return artifacts

    def run(self, force: bool = False) -> bool:
        if not force and not self._is_cooldown_passed():
            return False

        df_products, df_interactions = self.load_data()
        if not force and len(df_interactions) <= self.config.MIN_INTERACTIONS_TO_TRAIN:
            logger.info(
                f"Bỏ qua train: Số lượng log tương tác hiện tại ({len(df_interactions)}) "
                f"chưa vượt qua ngưỡng tối thiểu ({self.config.MIN_INTERACTIONS_TO_TRAIN})."
            )
            return False

        logger.info(f"=== BẮT ĐẦU HUẤN LUYỆN PIPELINE (VERSION={self.model_version}) ===")
        user_list = df_interactions["user_id"].astype(str).unique()
        item_list = df_products["product_id"].astype(str).unique()

        u2idx = {u: i for i, u in enumerate(user_list)}
        i2idx = {it: i for i, it in enumerate(item_list)}

        self.train_item_similarity(df_products, df_interactions, i2idx)
        self.train_svd(df_interactions, u2idx, i2idx, force=force)
        self.upload_artifacts_to_azure()
        self._record_train_timestamp()
        logger.info("=== HUẤN LUYỆN VÀ ĐỒNG BỘ ARTIFACTS HOÀN TẤT ===")
        return True

    def upload_artifacts_to_azure(self):
        """Tự động đồng bộ các file model mới lên Azure Blob Storage (container: model-artifacts)."""
        conn_str = self.config.AZURE_STORAGE_CONNECTION_STRING
        if not conn_str or "your_storage_account" in conn_str or "<AZURITE" in conn_str:
            logger.info("Bỏ qua đồng bộ Cloud: Chưa cấu hình connection string Blob Storage.")
            return

        logger.info("Đang đồng bộ model artifacts lên Azure Blob Storage...")
        manifest_path = self.config.MODELS_DIR / "model_manifest.json"
        files_to_upload = [
            self.config.ITEM_SIMILARITY_PATH,
            manifest_path,
            self.config.SVD_MODEL_PATH,  # Upload sau cùng để kích hoạt đồng bộ nguyên vẹn ở Recommender Service
        ]

        try:
            blob_service = BlobServiceClient.from_connection_string(conn_str)
            container_client = blob_service.get_container_client(self.config.BLOB_CONTAINER_MODEL_ARTIFACTS)

            for local_path in files_to_upload:
                if not local_path.exists():
                    logger.warning(f"   -> Bỏ qua '{local_path.name}' vì file không tồn tại.")
                    continue
                blob_client = container_client.get_blob_client(local_path.name)
                with open(local_path, "rb") as data:
                    blob_client.upload_blob(data, overwrite=True)
                logger.info(
                    f"   -> Đã upload '{local_path.name}' lên container '{self.config.BLOB_CONTAINER_MODEL_ARTIFACTS}'."
                )
        except Exception as e:
            logger.error(f"Lỗi khi upload artifacts lên Azure Blob: {str(e)}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Bỏ qua kiểm tra chu kỳ 1 tuần và ngưỡng 100 tương tác")
    args = parser.parse_args()

    trainer = RecommenderTrainer()
    trainer.run(force=args.force)