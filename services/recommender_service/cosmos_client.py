"""
services/recommender_service/cosmos_client.py
Quản lý kết nối tới Azure Cosmos DB NoSQL (Point-Read O(1) < 10ms),
In-memory TTL Cache, nạp Model Artifacts (`item_similarity.npz`, `svd_recommender.pkl`)
và làm giàu thông tin sản phẩm (Product Metadata Enrichment) từ PostgreSQL / Parquet.
"""

import logging
import os
import pickle
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("recommender_service.cosmos_client")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=ROOT_DIR / ".env")


class TTLCache:
    """Bộ nhớ đệm In-memory với thời gian sống (TTL = 30 phút mặc định) giảm tải RU/s cho Cosmos DB."""

    def __init__(self, ttl_seconds: int = 1800, max_size: int = 5000):
        self.ttl = ttl_seconds
        self.max_size = max_size
        self._store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if not entry:
            return None
        expires_at, val = entry
        if time.time() > expires_at:
            self._store.pop(key, None)
            return None
        return val

    def set(self, key: str, value: Any):
        if len(self._store) >= self.max_size:
            # Xóa phần tử cũ nhất
            oldest_key = next(iter(self._store))
            self._store.pop(oldest_key, None)
        self._store[key] = (time.time() + self.ttl, value)

    def clear(self):
        self._store.clear()


class RecommenderCosmosClient:
    """
    Client quản lý:
    1. Truy vấn Point-Read O(1) từ 3 Containers trên Azure Cosmos DB:
       - `user_recommendations`
       - `item_recommendations`
       - `system_metadata` (Cold-start fallback `popular_items`)
    2. Fallback tính toán trực tiếp từ Model Artifacts (`svd_recommender.pkl` & `item_similarity.npz`)
       khi Cosmos DB chưa khởi chạy hoặc user/item chưa được tiền tính toán.
    3. Ghép nối thông tin chi tiết sản phẩm (tên, giá, ảnh, danh mục) từ PostgreSQL hoặc SQL seed.
    """

    def __init__(self):
        self.cosmos_endpoint = os.getenv("COSMOS_DB_ENDPOINT", "https://localhost:8081/")
        self.cosmos_key = os.getenv("COSMOS_DB_PRIMARY_KEY", "")
        self.database_name = os.getenv("COSMOS_DB_DATABASE_NAME", "ecommerce_recommender_db")

        self.container_user_name = os.getenv("COSMOS_CONTAINER_USER_RECS", "user_recommendations")
        self.container_item_name = os.getenv("COSMOS_CONTAINER_ITEM_RECS", "item_recommendations")
        self.container_meta_name = os.getenv("COSMOS_CONTAINER_METADATA", "system_metadata")

        self.cosmos_connected = False
        self.client = None
        self.db = None
        self.user_container = None
        self.item_container = None
        self.meta_container = None

        # In-memory cache (TTL 30 phút theo đặc tả README Tiêu chí 3.4)
        self.cache = TTLCache(ttl_seconds=int(os.getenv("RECOMMENDER_CACHE_TTL", "1800")))

        # Model Artifacts trong RAM
        self.models_dir = ROOT_DIR / "models"
        self.item_sim_matrix: Optional[np.ndarray] = None
        self.svd_artifacts: Optional[Dict[str, Any]] = None
        self.model_version: str = os.getenv("MODEL_VERSION", "v1.0-svd")

        # Từ điển tra cứu nhanh thông tin sản phẩm {product_id: dict}
        self.product_catalog: Dict[str, Dict[str, Any]] = {}
        self.ordered_product_ids: List[str] = []

    def initialize(self):
        """Khởi tạo kết nối Cosmos DB, nạp danh mục sản phẩm và nạp Model Artifacts vào RAM."""
        self._load_product_catalog()
        self._load_model_artifacts()
        self._connect_cosmos()

    # --------------------------------------------------------------------------
    # 1. NẠP DANH MỤC SẢN PHẨM (TỪ POSTGRESQL HOẶC SEED_PRODUCTS.SQL / PARQUET)
    # --------------------------------------------------------------------------
    def _load_product_catalog(self):
        """Nạp danh mục 1,000 sản phẩm vào RAM để làm giàu JSON trả về với tốc độ O(1)."""
        loaded = False

        # Ưu tiên 1: Đọc từ PostgreSQL
        try:
            from sqlalchemy import create_engine, text

            pg_host = os.getenv("POSTGRES_HOST", "localhost")
            pg_port = os.getenv("POSTGRES_PORT", "5432")
            pg_db = os.getenv("POSTGRES_DB", "ecommerce_shop_db")
            pg_user = os.getenv("POSTGRES_USER", "postgres_admin")
            pg_pass = os.getenv("POSTGRES_PASSWORD", "YourSecurePasswordHere123!")
            pg_ssl = os.getenv("POSTGRES_SSL_MODE", "disable")
            db_url = os.getenv(
                "DATABASE_URL",
                f"postgresql+psycopg2://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}?sslmode={pg_ssl}",
            )
            eng = create_engine(db_url, connect_args={"connect_timeout": 3})
            with eng.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT id, name, category, price, image_url, stock_quantity, description FROM products"
                    )
                ).fetchall()
                if rows:
                    for r in rows:
                        pid = str(r[0])
                        self.product_catalog[pid] = {
                            "product_id": pid,
                            "name": str(r[1]),
                            "category": str(r[2]) if r[2] else "Musical Instruments",
                            "price": float(r[3]) if r[3] is not None else 0.0,
                            "thumbnail_url": str(r[4]) if r[4] else "",
                            "image_url": str(r[4]) if r[4] else "",
                            "stock_quantity": int(r[5]) if r[5] is not None else 100,
                            "description": str(r[6]) if r[6] else "",
                            "rating": 4.6,
                            "rating_count": 25,
                        }
                    self.ordered_product_ids = list(self.product_catalog.keys())
                    loaded = True
                    logger.info(
                        f"Đã nạp {len(self.product_catalog)} sản phẩm từ PostgreSQL vào bộ nhớ đệm."
                    )
        except Exception as exc:
            logger.debug(f"Chưa đọc được products từ PostgreSQL ({exc}), thử đọc từ Parquet/SQL...")

        # Ưu tiên 2: Đọc từ file Parquet cục bộ nếu có
        if not loaded:
            for pq_name in ["web_products.parquet", "clean_products.parquet", "training_products.parquet"]:
                pq_path = ROOT_DIR / "data" / "processed" / pq_name
                if pq_path.exists():
                    try:
                        import pandas as pd

                        df = pd.read_parquet(pq_path)
                        for _, row in df.iterrows():
                            pid = str(row.get("product_id") or row.get("id"))
                            img = str(row.get("thumbnail_url") or row.get("image_url") or "")
                            self.product_catalog[pid] = {
                                "product_id": pid,
                                "name": str(row.get("name", pid)),
                                "category": str(row.get("category", "Musical Instruments")),
                                "price": float(row.get("price", 19.99)),
                                "thumbnail_url": img,
                                "image_url": img,
                                "stock_quantity": int(row.get("stock_quantity", 100)),
                                "description": str(row.get("description", "")),
                                "rating": float(row.get("rating", 4.6)),
                                "rating_count": int(row.get("rating_count", 25)),
                            }
                        self.ordered_product_ids = list(self.product_catalog.keys())
                        loaded = True
                        logger.info(
                            f"Đã nạp {len(self.product_catalog)} sản phẩm từ '{pq_name}'."
                        )
                        break
                    except Exception as exc:
                        logger.warning(f"Lỗi đọc {pq_name}: {exc}")

        # Ưu tiên 3: Parse trực tiếp từ scripts/sql/seed_products.sql (luôn có sẵn trong repo)
        if not loaded:
            sql_seed = ROOT_DIR / "scripts" / "sql" / "seed_products.sql"
            if sql_seed.exists():
                try:
                    content = sql_seed.read_text(encoding="utf-8")
                    pattern = re.compile(
                        r"VALUES\s*\(\s*'([^']+)'\s*,\s*'((?:[^']|'')*)'\s*,\s*'((?:[^']|'')*)'\s*,\s*([0-9.]+)\s*,\s*'([^']*)'\s*,\s*(\d+)\s*,\s*'((?:[^']|'')*)'\s*\)",
                        re.DOTALL,
                    )
                    for match in pattern.finditer(content):
                        pid, name, cat, price, img, stock, desc = match.groups()
                        self.product_catalog[pid] = {
                            "product_id": pid,
                            "name": name.replace("''", "'"),
                            "category": cat.replace("''", "'"),
                            "price": float(price),
                            "thumbnail_url": img,
                            "image_url": img,
                            "stock_quantity": int(stock),
                            "description": desc.replace("''", "'"),
                            "rating": 4.6,
                            "rating_count": 25,
                        }
                    self.ordered_product_ids = list(self.product_catalog.keys())
                    logger.info(
                        f"Đã nạp {len(self.product_catalog)} sản phẩm từ 'scripts/sql/seed_products.sql'."
                    )
                except Exception as exc:
                    logger.warning(f"Không thể parse seed_products.sql: {exc}")

    # --------------------------------------------------------------------------
    # 2. NẠP MODEL ARTIFACTS (TỪ LOCAL HOẶC AZURE BLOB STORAGE)
    # --------------------------------------------------------------------------
    def _load_model_artifacts(self):
        """Tải `item_similarity.npz` và `svd_recommender.pkl` từ ổ đĩa hoặc Azure Blob Storage."""
        self.models_dir.mkdir(parents=True, exist_ok=True)
        sim_path = self.models_dir / "item_similarity.npz"
        svd_path = self.models_dir / "svd_recommender.pkl"

        # Nếu thiếu file cục bộ và đã cấu hình Azure Blob Storage -> tự động tải về
        conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
        if conn_str and "<AZURITE_" not in conn_str and "your_storage_account" not in conn_str:
            container_name = os.getenv("BLOB_CONTAINER_MODEL_ARTIFACTS", "model-artifacts")
            for target_path in [sim_path, svd_path]:
                if not target_path.exists():
                    try:
                        from azure.storage.blob import BlobServiceClient

                        blob_service = BlobServiceClient.from_connection_string(conn_str)
                        blob_client = blob_service.get_container_client(container_name).get_blob_client(
                            target_path.name
                        )
                        with open(target_path, "wb") as f:
                            f.write(blob_client.download_blob().readall())
                        logger.info(f"Đã tải '{target_path.name}' từ Azure Blob Storage.")
                    except Exception as exc:
                        logger.debug(f"Không tải được '{target_path.name}' từ Blob: {exc}")

        if sim_path.exists():
            try:
                data = np.load(sim_path)
                self.item_sim_matrix = data["similarity"]
                logger.info(
                    f"Đã nạp ma trận tương đồng sản phẩm: shape={self.item_sim_matrix.shape}"
                )
            except Exception as exc:
                logger.warning(f"Lỗi đọc item_similarity.npz: {exc}")

        if svd_path.exists():
            try:
                with open(svd_path, "rb") as f:
                    self.svd_artifacts = pickle.load(f)
                self.model_version = self.svd_artifacts.get("model_version", "v1.0-svd")
                logger.info(f"Đã nạp mô hình SVD ({self.model_version}).")
            except Exception as exc:
                logger.warning(f"Lỗi đọc svd_recommender.pkl: {exc}")

    # --------------------------------------------------------------------------
    # 3. KẾT NỐI AZURE COSMOS DB NOSQL
    # --------------------------------------------------------------------------
    def _connect_cosmos(self):
        if (
            not self.cosmos_endpoint
            or not self.cosmos_key
            or "<COSMOS_" in self.cosmos_key
            or "your-cosmos-account" in self.cosmos_endpoint
        ):
            logger.info(
                "Chưa cấu hình khóa thực tế cho Cosmos DB -> Sử dụng chế độ In-Memory Model Serving."
            )
            self.cosmos_connected = False
            return

        try:
            from azure.cosmos import CosmosClient

            self.client = CosmosClient(
                self.cosmos_endpoint,
                credential=self.cosmos_key,
                connection_verify=False,
            )
            self.db = self.client.get_database_client(self.database_name)
            self.user_container = self.db.get_container_client(self.container_user_name)
            self.item_container = self.db.get_container_client(self.container_item_name)
            self.meta_container = self.db.get_container_client(self.container_meta_name)

            # Kiểm tra kết nối nhanh
            self.db.read()
            self.cosmos_connected = True
            logger.info(
                f"Đã kết nối thành công tới Azure Cosmos DB ('{self.database_name}')."
            )
        except Exception as exc:
            self.cosmos_connected = False
            logger.warning(
                f"Cosmos DB chưa sẵn sàng ({exc}) -> Tự động chuyển sang chế độ In-Memory Model Fallback."
            )

    # --------------------------------------------------------------------------
    # 4. LÀM GIÀU METADATA SẢN PHẨM (ENRICH PRODUCT DETAILS)
    # --------------------------------------------------------------------------
    def enrich_product(self, product_id: str, extra_fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        base = self.product_catalog.get(
            str(product_id),
            {
                "product_id": str(product_id),
                "name": f"Musical Instrument {product_id}",
                "category": "Musical Instruments",
                "price": 29.99,
                "thumbnail_url": "",
                "image_url": "",
                "stock_quantity": 100,
                "description": "",
                "rating": 4.5,
                "rating_count": 10,
            },
        ).copy()
        if extra_fields:
            base.update(extra_fields)
        return base

    # --------------------------------------------------------------------------
    # 5. TRUY VẤN GỢI Ý CHO USER (PERSONALIZED RECOMMENDATIONS & COLD-START)
    # --------------------------------------------------------------------------
    def get_popular_items(self, top_k: int = 10) -> List[Dict[str, Any]]:
        """Lấy danh sách Top-K sản phẩm thịnh hành phục vụ Cold-Start Fallback."""
        cache_key = f"popular:{top_k}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        results: List[Dict[str, Any]] = []

        # 1. Thử đọc Point-Read O(1) từ Cosmos DB container `system_metadata`
        if self.cosmos_connected and self.meta_container:
            try:
                doc = self.meta_container.read_item(
                    item="popular_items", partition_key="popular_items"
                )
                # Hỗ trợ cả 2 schema: `items` (export_to_cosmos.py) và `popular_product_ids` (init_local_dev.py)
                if "items" in doc and isinstance(doc["items"], list):
                    for idx, item in enumerate(doc["items"][:top_k], start=1):
                        pid = str(item.get("product_id"))
                        results.append(
                            self.enrich_product(
                                pid,
                                {
                                    "score": float(item.get("score", round(5.0 - idx * 0.05, 2))),
                                    "rank": int(item.get("rank", idx)),
                                    "recommendation_type": "cold_start_popular",
                                },
                            )
                        )
                elif "popular_product_ids" in doc and isinstance(doc["popular_product_ids"], list):
                    for idx, pid in enumerate(doc["popular_product_ids"][:top_k], start=1):
                        results.append(
                            self.enrich_product(
                                str(pid),
                                {
                                    "score": round(5.0 - idx * 0.05, 2),
                                    "rank": idx,
                                    "recommendation_type": "cold_start_popular",
                                },
                            )
                        )
            except Exception as exc:
                logger.debug(f"Không đọc được popular_items từ Cosmos DB: {exc}")

        # 2. Fallback từ danh mục sản phẩm trong RAM nếu Cosmos chưa có
        if not results and self.ordered_product_ids:
            for idx, pid in enumerate(self.ordered_product_ids[:top_k], start=1):
                results.append(
                    self.enrich_product(
                        pid,
                        {
                            "score": round(4.95 - idx * 0.04, 2),
                            "rank": idx,
                            "recommendation_type": "cold_start_popular",
                        },
                    )
                )

        self.cache.set(cache_key, results)
        return results

    def get_user_recommendations(
        self, user_id: str, top_k: int = 10
    ) -> Tuple[List[Dict[str, Any]], str, str]:
        """
        Trả về `(recommendations_list, strategy, source)`:
        - Bước 1: Kiểm tra In-memory Cache.
        - Bước 2: Point-Read $O(1)$ vào Cosmos DB `user_recommendations` theo `user_id`.
        - Bước 3: Nếu chưa có trong Cosmos, kiểm tra vector tiềm ẩn trong `svd_recommender.pkl` ($P_u \cdot Q^T$).
        - Bước 4: Nếu user mới hoàn toàn (Cold-start), fallback về Top Popular Items (`system_metadata`).
        """
        cache_key = f"user_rec:{user_id}:{top_k}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached["items"], cached["strategy"], "memory_cache"

        # 1. Truy vấn O(1) từ Cosmos DB container `user_recommendations`
        if self.cosmos_connected and self.user_container:
            try:
                doc = self.user_container.read_item(item=user_id, partition_key=user_id)
                raw_recs = doc.get("recommendations", [])
                if raw_recs:
                    enriched = [
                        self.enrich_product(
                            str(r["product_id"]),
                            {
                                "score": float(r.get("score", 4.8)),
                                "rank": int(r.get("rank", idx)),
                                "recommendation_type": "svd_personalized",
                            },
                        )
                        for idx, r in enumerate(raw_recs[:top_k], start=1)
                    ]
                    self.cache.set(
                        cache_key,
                        {"items": enriched, "strategy": "svd_personalized"},
                    )
                    return enriched, "svd_personalized", "cosmos_db"
            except Exception:
                # User không tồn tại trong container user_recommendations -> chuyển sang bước tiếp theo
                pass

        # 2. Suy luận trực tiếp từ ma trận SVD (nếu user_id có trong tập huấn luyện SVD)
        if self.svd_artifacts:
            u2idx = self.svd_artifacts.get("user2idx", {})
            idx2item = self.svd_artifacts.get("idx2item", {})
            P = self.svd_artifacts.get("P")
            Q = self.svd_artifacts.get("Q")

            if user_id in u2idx and P is not None and Q is not None:
                u_idx = u2idx[user_id]
                scores = P[u_idx] @ Q.T
                top_indices = np.argsort(scores)[::-1][:top_k]
                enriched = []
                for rank_idx, it_idx in enumerate(top_indices, start=1):
                    pid = str(idx2item.get(it_idx, self.ordered_product_ids[it_idx]))
                    enriched.append(
                        self.enrich_product(
                            pid,
                            {
                                "score": round(float(scores[it_idx]), 4),
                                "rank": rank_idx,
                                "recommendation_type": "svd_personalized",
                            },
                        )
                    )
                self.cache.set(
                    cache_key, {"items": enriched, "strategy": "svd_personalized"}
                )
                return enriched, "svd_personalized", "svd_model_memory"

        # 3. Cold-Start Fallback: Trả về danh sách sản phẩm phổ biến nhất
        popular = self.get_popular_items(top_k=top_k)
        return (
            popular,
            "cold_start_popular",
            "cosmos_db" if self.cosmos_connected else "in_memory_fallback",
        )

    # --------------------------------------------------------------------------
    # 6. TRUY VẤN SẢN PHẨM THƯỜNG MUA CÙNG (ITEM-TO-ITEM BUNDLES)
    # --------------------------------------------------------------------------
    def get_item_bundles(
        self, product_id: str, top_k: int = 5
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Trả về danh sách Top-K sản phẩm thường được mua cùng (`frequently_bought_together`):
        - Bước 1: Kiểm tra In-memory Cache.
        - Bước 2: Point-Read $O(1)$ vào Cosmos DB `item_recommendations` theo `product_id`.
        - Bước 3: Fallback tính trực tiếp từ ma trận `item_similarity.npz` trong RAM.
        """
        cache_key = f"item_bundle:{product_id}:{top_k}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached, "memory_cache"

        # 1. Truy vấn Point-Read O(1) từ Cosmos DB container `item_recommendations`
        if self.cosmos_connected and self.item_container:
            try:
                doc = self.item_container.read_item(
                    item=product_id, partition_key=product_id
                )
                raw_bundles = doc.get("frequently_bought_together", [])
                if raw_bundles:
                    enriched = [
                        self.enrich_product(
                            str(b["product_id"]),
                            {
                                "similarity_score": float(b.get("similarity_score", 0.85)),
                                "bundle_type": str(b.get("bundle_type", "co-purchase")),
                                "rank": idx,
                            },
                        )
                        for idx, b in enumerate(raw_bundles[:top_k], start=1)
                    ]
                    self.cache.set(cache_key, enriched)
                    return enriched, "cosmos_db"
            except Exception:
                pass

        # 2. Fallback tra cứu trực tiếp trên ma trận `item_similarity.npz`
        if (
            self.item_sim_matrix is not None
            and self.ordered_product_ids
            and product_id in self.product_catalog
        ):
            try:
                item_idx = self.ordered_product_ids.index(product_id)
                if item_idx < self.item_sim_matrix.shape[0]:
                    sims = self.item_sim_matrix[item_idx].copy()
                    sims[item_idx] = -1.0  # Loại trừ chính nó
                    top_indices = np.argsort(sims)[::-1][:top_k]

                    base_cat = self.product_catalog[product_id].get("category", "")
                    enriched = []
                    for rank_idx, idx in enumerate(top_indices, start=1):
                        if idx < len(self.ordered_product_ids):
                            b_pid = self.ordered_product_ids[idx]
                            b_cat = self.product_catalog.get(b_pid, {}).get("category", "")
                            sim_score = round(float(sims[idx]), 4)
                            bundle_type = (
                                "accessory"
                                if (base_cat and b_cat and base_cat != b_cat)
                                else ("co-purchase" if sim_score > 0.6 else "content_match")
                            )
                            enriched.append(
                                self.enrich_product(
                                    b_pid,
                                    {
                                        "similarity_score": sim_score,
                                        "bundle_type": bundle_type,
                                        "rank": rank_idx,
                                    },
                                )
                            )
                    if enriched:
                        self.cache.set(cache_key, enriched)
                        return enriched, "item_similarity_matrix"
            except ValueError:
                pass

        # 3. Fallback cuối: Lấy các sản phẩm cùng danh mục hoặc phổ biến
        popular_fallback = [
            self.enrich_product(
                p["product_id"],
                {
                    "similarity_score": round(0.75 - i * 0.05, 3),
                    "bundle_type": "category_match",
                    "rank": i,
                },
            )
            for i, p in enumerate(self.get_popular_items(top_k=top_k + 1), start=1)
            if p["product_id"] != product_id
        ][:top_k]

        return popular_fallback, "fallback_catalog"
