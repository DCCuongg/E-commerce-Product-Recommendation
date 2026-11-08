"""
ml_pipeline/export_to_cosmos.py
Tính toán trước (Precompute) kết quả gợi ý và đẩy trực tiếp lên Azure Cosmos DB:
1. `user_recommendations`: Top 10 sản phẩm cá nhân hóa cho từng user.
2. `item_recommendations`: Top 5 sản phẩm thường mua kèm (Bundle).
3. `system_metadata`: Top 10 sản phẩm thịnh hành (Fallback khi gặp người dùng mới).
"""

import json
import pickle
import logging
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from azure.cosmos import CosmosClient
from .config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class CosmosDBExporter:
    def __init__(self, config=Config):
        self.config = config
        self.config.ensure_directories()
        self.cosmos_client = None
        self.database_client = None

    def init_cosmos(self) -> bool:
        if not self.config.COSMOS_ENDPOINT or not self.config.COSMOS_KEY or "your-cosmos-account" in self.config.COSMOS_ENDPOINT:
            logger.warning("Chưa cấu hình Azure Cosmos DB credentials. Chạy chế độ Dry-run lưu JSON cục bộ.")
            return False

        try:
            self.cosmos_client = CosmosClient(self.config.COSMOS_ENDPOINT, credential=self.config.COSMOS_KEY)
            self.database_client = self.cosmos_client.get_database_client(self.config.COSMOS_DATABASE_NAME)
            return True
        except Exception as e:
            logger.error(f"Kết nối Cosmos DB thất bại: {str(e)}")
            return False

    def run(self, dry_run: bool = False):
        logger.info("=== BẮT ĐẦU TÍNH TOÁN VÀ XUẤT DỮ LIỆU SANG COSMOS DB ===")
        with open(self.config.SVD_MODEL_PATH, "rb") as f:
            svd_data = pickle.load(f)

        sim_data = np.load(self.config.ITEM_SIMILARITY_PATH)
        hybrid_sim = sim_data["similarity"]

        df_products = pd.read_parquet(self.config.PROCESSED_PRODUCTS_PARQUET)
        df_interactions = pd.read_parquet(self.config.PROCESSED_INTERACTIONS_PARQUET)

        now_iso = datetime.now(timezone.utc).isoformat()

        # ----------------------------------------------------------------------
        # 1. USER RECOMMENDATIONS (Container: user_recommendations)
        # ----------------------------------------------------------------------
        logger.info("[COSMOS 1/3] Tính toán Top-10 Personalization cho từng User...")
        P, Q = svd_data["P"], svd_data["Q"]
        user2idx = svd_data["user2idx"]
        idx2item = svd_data["idx2item"]
        user_history = df_interactions.groupby("user_id")["product_id"].apply(set).to_dict()

        user_docs = []
        for uid, u_idx in user2idx.items():
            scores = P[u_idx] @ Q.T
            seen = user_history.get(uid, set())
            ranked = np.argsort(scores)[::-1]

            recs = []
            rank = 1
            for it_idx in ranked:
                pid = idx2item[it_idx]
                if pid not in seen:
                    recs.append({"product_id": pid, "score": round(float(scores[it_idx]), 4), "rank": rank})
                    rank += 1
                if len(recs) >= self.config.ML_TOP_K_RECOMMENDATIONS:
                    break

            user_docs.append({
                "id": uid,
                "user_id": uid,
                "recommendations": recs,
                "model_version": svd_data.get("model_version", "v1.0-svd"),
                "updated_at": now_iso
            })

        # ----------------------------------------------------------------------
        # 2. ITEM BUNDLES (Container: item_recommendations)
        # ----------------------------------------------------------------------
        logger.info("[COSMOS 2/3] Tính toán Top-5 Bundle Mua Cùng cho từng Sản phẩm...")
        item2idx = svd_data["item2idx"]
        cat_map = dict(zip(df_products["product_id"], df_products["category"]))

        item_docs = []
        for pid, it_idx in item2idx.items():
            sims = hybrid_sim[it_idx].copy()
            sims[it_idx] = -1.0
            top_indices = np.argsort(sims)[::-1][: self.config.TOP_K_BUNDLES]

            bundles = []
            base_cat = cat_map.get(pid, "")
            for b_idx in top_indices:
                b_pid = idx2item[b_idx]
                b_cat = cat_map.get(b_pid, "")
                bundles.append({
                    "product_id": b_pid,
                    "similarity_score": round(float(sims[b_idx]), 4),
                    "bundle_type": "accessory" if (base_cat and b_cat and base_cat != b_cat) else "co-purchase"
                })

            item_docs.append({
                "id": pid,
                "product_id": pid,
                "frequently_bought_together": bundles,
                "updated_at": now_iso
            })

        # ----------------------------------------------------------------------
        # 3. POPULAR FALLBACK (Container: system_metadata)
        # ----------------------------------------------------------------------
        logger.info("[COSMOS 3/3] Tính toán Top Trending cho Cold-Start Fallback...")
        df_popular = df_products.sort_values(by=["rating_count", "rating"], ascending=[False, False]).head(10)
        popular_items = [
            {"product_id": str(r["product_id"]), "name": str(r["name"]), "price": float(r["price"]), "rank": idx}
            for idx, (_, r) in enumerate(df_popular.iterrows(), start=1)
        ]
        meta_doc = {
            "id": "popular_items",
            "type": "cold_start_fallback",
            "items": popular_items,
            "updated_at": now_iso
        }

        # Lưu bản JSON mẫu cục bộ để kiểm tra / mock test
        with open(self.config.EXPORTS_DIR / "user_recs_sample.json", "w", encoding="utf-8") as f:
            json.dump(user_docs[:20], f, indent=2, ensure_ascii=False)
        with open(self.config.EXPORTS_DIR / "item_recs_sample.json", "w", encoding="utf-8") as f:
            json.dump(item_docs[:20], f, indent=2, ensure_ascii=False)

        # Đẩy lên Cosmos DB nếu có kết nối
        if dry_run or not self.init_cosmos():
            logger.info("Chế độ Dry-run: Dữ liệu đã lưu tại exports/.")
            return

        self._batch_upsert(self.config.COSMOS_CONTAINER_USER_RECS, user_docs)
        self._batch_upsert(self.config.COSMOS_CONTAINER_ITEM_RECS, item_docs)
        self._batch_upsert(self.config.COSMOS_CONTAINER_METADATA, [meta_doc])
        logger.info("=== CẬP NHẬT COSMOS DB THÀNH CÔNG ===")

    def _batch_upsert(self, container_name: str, documents: list):
        logger.info(f"Đang đồng bộ {len(documents)} tài liệu vào Container '{container_name}'...")
        container = self.database_client.get_container_client(container_name)
        for doc in documents:
            try:
                container.upsert_item(body=doc)
            except Exception as e:
                logger.error(f"Lỗi khi upsert ID {doc.get('id')}: {str(e)}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    exporter = CosmosDBExporter()
    exporter.run(dry_run=args.dry_run)