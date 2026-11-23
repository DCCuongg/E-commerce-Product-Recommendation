"""
services/recommender_service/cosmos_client.py
Truy vấn O(1) từ Azure Cosmos DB kết hợp Model Serving trên RAM:
- Chính sách mặc định: Tự động tải model & catalog từ Hugging Face Hub nếu local/Blob chưa có.
- Chính sách cập nhật: Tự động phát hiện và hot-reload model mới nhất khi ML Pipeline cập nhật lên Azure Blob hoặc Local.
"""

import json
import logging
import os
import pickle
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import scipy.sparse as sp
import urllib3
from azure.cosmos import CosmosClient
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=ROOT_DIR / ".env")

logger = logging.getLogger("RecommenderClient")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _is_placeholder(val: str) -> bool:
    if not val:
        return True
    markers = ("<AZURITE", "<COSMOS", "<REPLACE", "<YOUR_", "your_storage_account", "your-cosmos-account")
    return any(m in val for m in markers)


class RecommenderCosmosClient:
    def __init__(self):
        self._lock = threading.RLock()

        self.models_dir = ROOT_DIR / "models"
        self.processed_dir = ROOT_DIR / "data" / "processed"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        self.svd_path = self.models_dir / "svd_recommender.pkl"
        self.sim_path = self.models_dir / "item_similarity.npz"
        self.manifest_path = self.models_dir / "model_manifest.json"
        self.web_parquet_path = self.processed_dir / "web_products.parquet"
        self.clean_parquet_path = self.processed_dir / "clean_products.parquet"

        # Hugging Face defaults
        self.hf_model_repo = os.getenv("HF_MODEL_REPO", "cuongduongok/amazon-musical-recommender-models")
        self.hf_dataset_repo = os.getenv("HF_DATASET_REPO", "cuongduongok/amazon-musical-instruments-clean")
        self.hf_token = os.getenv("HF_TOKEN") or os.getenv("HF_WRITE_MODELS_TOKEN") or None

        # Azure Blob Storage
        self.blob_conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
        self.blob_model_container = os.getenv("BLOB_CONTAINER_MODEL_ARTIFACTS", "model-artifacts")

        # Azure Cosmos DB
        self.cosmos_endpoint = os.getenv("COSMOS_DB_ENDPOINT", "")
        self.cosmos_key = os.getenv("COSMOS_DB_PRIMARY_KEY", "")
        self.cosmos_db_name = os.getenv("COSMOS_DB_DATABASE_NAME", "ecommerce_recommender_db")
        self.user_container_name = os.getenv("COSMOS_CONTAINER_USER_RECS", "user_recommendations")
        self.item_container_name = os.getenv("COSMOS_CONTAINER_ITEM_RECS", "item_recommendations")
        self.meta_container_name = os.getenv("COSMOS_CONTAINER_METADATA", "system_metadata")
        self.cosmos_ssl_verify = os.getenv("COSMOS_SSL_VERIFY", "false").lower() == "true"

        self.deployment_slot = os.getenv("DEPLOYMENT_SLOT", "blue")
        self.model_version = os.getenv("MODEL_VERSION", "v1.0-svd")
        self.model_source = "uninitialized"

        # Trạng thái theo dõi cập nhật model mới
        self.check_interval_sec = int(os.getenv("MODEL_CHECK_INTERVAL_SECONDS", "60"))
        self._last_checked_at = 0.0
        self._loaded_local_mtime = 0.0
        self._loaded_blob_mtime = 0.0

        # Cosmos clients
        self.cosmos_connected = False
        self.user_container = None
        self.item_container = None
        self.meta_container = None

        # In-memory artifacts & cache
        self.svd_data: Optional[Dict[str, Any]] = None
        self.hybrid_sim: Any = None
        self.sim_item_ids: List[str] = []
        self.catalog_map: Dict[str, Dict[str, Any]] = {}
        self.popular_product_ids: List[str] = []
        self._cache: Dict[str, tuple[float, Any]] = {}
        self._cache_ttl = 300.0

        self.reload_all(force_download=False)

    # --------------------------------------------------------------------------
    # 1. KẾT NỐI COSMOS DB
    # --------------------------------------------------------------------------
    def _init_cosmos(self) -> bool:
        if _is_placeholder(self.cosmos_endpoint) or _is_placeholder(self.cosmos_key):
            logger.warning("Cosmos DB chưa cấu hình key thực -> Chạy chế độ In-Memory Serving.")
            self.cosmos_connected = False
            return False

        try:
            client = CosmosClient(
                self.cosmos_endpoint,
                credential=self.cosmos_key,
                connection_verify=self.cosmos_ssl_verify,
            )
            db = client.get_database_client(self.cosmos_db_name)
            self.user_container = db.get_container_client(self.user_container_name)
            self.item_container = db.get_container_client(self.item_container_name)
            self.meta_container = db.get_container_client(self.meta_container_name)
            # Ping nhẹ kiểm tra container tồn tại
            self.meta_container.read()
            self.cosmos_connected = True
            logger.info(f"Đã kết nối Azure Cosmos DB: {self.cosmos_db_name}")
            return True
        except Exception as exc:
            logger.warning(f"Không thể kết nối Cosmos DB ({exc}) -> Fallback sang In-Memory Serving.")
            self.cosmos_connected = False
            return False

    # --------------------------------------------------------------------------
    # 2. ĐỒNG BỘ MODEL & CATALOG (AZURE BLOB -> LOCAL -> HUGGING FACE DEFAULT)
    # --------------------------------------------------------------------------
    def _sync_from_azure_blob(self, force: bool = False) -> bool:
        """Kiểm tra và tải model (và catalog nếu có) mới nhất từ Azure Blob Storage."""
        if _is_placeholder(self.blob_conn_str):
            return False

        try:
            from azure.storage.blob import BlobServiceClient

            blob_service = BlobServiceClient.from_connection_string(self.blob_conn_str)
            container = blob_service.get_container_client(self.blob_model_container)
            if not container.exists():
                return False

            svd_blob = container.get_blob_client("svd_recommender.pkl")
            sim_blob = container.get_blob_client("item_similarity.npz")
            if not (svd_blob.exists() and sim_blob.exists()):
                return False

            props = svd_blob.get_blob_properties()
            remote_ts = props.last_modified.timestamp()

            # Chỉ tải lại nếu Blob có bản mới hơn bản đang giữ trên RAM hoặc local thiếu file
            need_download = (
                force
                or not self.svd_path.exists()
                or not self.sim_path.exists()
                or remote_ts > self._loaded_blob_mtime
            )
            if not need_download:
                return False

            logger.info("Phát hiện model mới trên Azure Blob Storage -> Đang tải về...")
            with open(self.svd_path, "wb") as f:
                f.write(svd_blob.download_blob().readall())
            with open(self.sim_path, "wb") as f:
                f.write(sim_blob.download_blob().readall())

            manifest_blob = container.get_blob_client("model_manifest.json")
            if manifest_blob.exists():
                with open(self.manifest_path, "wb") as f:
                    f.write(manifest_blob.download_blob().readall())

            # Nếu pipeline có đẩy kèm web_products.parquet lên Blob thì tải đồng bộ luôn
            web_pq_blob = container.get_blob_client("web_products.parquet")
            if web_pq_blob.exists() and (force or not self.web_parquet_path.exists()):
                with open(self.web_parquet_path, "wb") as f:
                    f.write(web_pq_blob.download_blob().readall())

            self._loaded_blob_mtime = remote_ts
            self.model_source = "azure_blob_latest"
            return True
        except Exception as exc:
            logger.warning(f"Bỏ qua đồng bộ Azure Blob ({exc}).")
            return False

    def _download_default_from_hf(self, force: bool = False) -> bool:
        """Chính sách mặc định: Tải model & catalog chuẩn còn thiếu từ Hugging Face Hub."""
        try:
            from huggingface_hub import hf_hub_download

            downloaded_model = False
            downloaded_catalog = False

            if force or not self.svd_path.exists():
                logger.info(f"Đang tải svd_recommender.pkl mặc định từ Hugging Face ({self.hf_model_repo})...")
                cached_svd = hf_hub_download(
                    repo_id=self.hf_model_repo,
                    filename="svd_recommender.pkl",
                    repo_type="model",
                    token=self.hf_token,
                )
                self.svd_path.write_bytes(Path(cached_svd).read_bytes())
                downloaded_model = True

            if force or not self.sim_path.exists():
                logger.info(f"Đang tải item_similarity.npz mặc định từ Hugging Face ({self.hf_model_repo})...")
                cached_sim = hf_hub_download(
                    repo_id=self.hf_model_repo,
                    filename="item_similarity.npz",
                    repo_type="model",
                    token=self.hf_token,
                )
                self.sim_path.write_bytes(Path(cached_sim).read_bytes())
                downloaded_model = True

            if force or (not self.web_parquet_path.exists() and not self.clean_parquet_path.exists()):
                logger.info(f"Đang tải web_products.parquet mặc định từ Hugging Face ({self.hf_dataset_repo})...")
                cached_pq = hf_hub_download(
                    repo_id=self.hf_dataset_repo,
                    filename="web_products.parquet",
                    repo_type="dataset",
                    token=self.hf_token,
                )
                self.web_parquet_path.write_bytes(Path(cached_pq).read_bytes())
                downloaded_catalog = True

            if downloaded_model and self.model_source == "uninitialized":
                self.model_source = "huggingface_default"
            return downloaded_model or downloaded_catalog
        except Exception as exc:
            logger.error(f"Lỗi khi tải model/dataset từ Hugging Face: {exc}")
            return False

    def _load_catalog_to_ram(self):
        """Nạp danh mục sản phẩm vào RAM từ file Parquet mới nhất (ETL local, Blob hoặc HF default)."""
        candidate_files = [self.clean_parquet_path, self.web_parquet_path]
        existing = [p for p in candidate_files if p.exists()]
        if not existing:
            self.catalog_map = {}
            self.popular_product_ids = []
            return

        # Chọn file Parquet mới nhất trên ổ đĩa
        latest_pq = max(existing, key=lambda p: p.stat().st_mtime)
        df = pd.read_parquet(latest_pq)
        if "is_active" in df.columns:
            df = df[df["is_active"].fillna(True)].copy()

        new_catalog: Dict[str, Dict[str, Any]] = {}
        for _, row in df.iterrows():
            pid = str(row["product_id"])
            raw_large = row.get("large_urls")
            if hasattr(raw_large, "tolist"):
                large_urls = raw_large.tolist()
            elif isinstance(raw_large, list):
                large_urls = raw_large
            else:
                large_urls = []

            thumb = str(row.get("thumb_url") or row.get("thumbnail_url") or row.get("image_url") or "")
            img = str(row.get("image_url") or row.get("hi_res_url") or thumb)

            new_catalog[pid] = {
                "product_id": pid,
                "name": str(row.get("name") or ""),
                "category": str(row.get("category") or "Musical Instruments"),
                "price": float(row.get("price") or 0.0),
                "thumbnail_url": thumb,
                "thumb_url": thumb,
                "image_url": img,
                "hi_res_url": str(row.get("hi_res_url") or img),
                "large_urls": large_urls,
                "stock_quantity": int(row.get("stock_quantity") or 100),
                "rating": float(row.get("rating") or 4.5),
                "rating_count": int(row.get("rating_count") or 0),
            }

        df_sorted = df.sort_values(
            by=[c for c in ["rating_count", "rating"] if c in df.columns],
            ascending=False,
        )
        self.catalog_map = new_catalog
        self.popular_product_ids = [str(pid) for pid in df_sorted["product_id"].tolist()]
        logger.info(f"Đã nạp {len(self.catalog_map)} sản phẩm vào RAM từ {latest_pq.name}.")

    def _load_models_to_ram(self):
        """Nạp trọng số SVD và ma trận Cosine Similarity (sparse hoặc dense) vào RAM."""
        if self.svd_path.exists():
            with open(self.svd_path, "rb") as f:
                self.svd_data = pickle.load(f)
            self._loaded_local_mtime = self.svd_path.stat().st_mtime
            if isinstance(self.svd_data, dict):
                self.model_version = self.svd_data.get("model_version", self.model_version)
                item_to_idx = self.svd_data.get("item_to_idx") or self.svd_data.get("item2idx") or {}
                if not item_to_idx and self.svd_data.get("item_ids") is not None:
                    item_to_idx = {str(it): i for i, it in enumerate(self.svd_data["item_ids"])}
                if item_to_idx:
                    idx_to_item = {int(idx): str(pid) for pid, idx in item_to_idx.items()}
                    self.sim_item_ids = [idx_to_item[i] for i in sorted(idx_to_item.keys())]
                elif "idx2item" in self.svd_data:
                    idx2item = self.svd_data["idx2item"]
                    self.sim_item_ids = [str(idx2item[i]) for i in sorted(idx2item.keys())]

        if self.sim_path.exists():
            try:
                self.hybrid_sim = sp.load_npz(self.sim_path)
            except Exception:
                sim_npz = np.load(self.sim_path, allow_pickle=True)
                for k in ("similarity", "sim_matrix", "matrix", "arr_0"):
                    if k in sim_npz:
                        self.hybrid_sim = sim_npz[k]
                        break
                if "item_ids" in sim_npz:
                    self.sim_item_ids = [str(x) for x in sim_npz["item_ids"].tolist()]
                elif "product_ids" in sim_npz:
                    self.sim_item_ids = [str(x) for x in sim_npz["product_ids"].tolist()]

        if not self.sim_item_ids and self.catalog_map:
            self.sim_item_ids = list(self.catalog_map.keys())

        if self.manifest_path.exists():
            try:
                manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                self.model_version = manifest.get("model_version", self.model_version)
                self.model_source = manifest.get("source", self.model_source)
            except Exception:
                pass
        elif self.model_source == "uninitialized" and self.svd_path.exists():
            self.model_source = "local_disk"

        logger.info(
            f"Đã nạp model vào RAM: version={self.model_version}, source={self.model_source}, "
            f"svd_ready={self.svd_data is not None}, sim_ready={self.hybrid_sim is not None}"
        )

    def reload_all(self, force_download: bool = False):
        """Nạp lại toàn bộ kết nối, model artifacts, catalog và xóa cache."""
        with self._lock:
            self._init_cosmos()

            # 1. Ưu tiên kiểm tra bản mới từ Azure Blob Storage
            self._sync_from_azure_blob(force=force_download)

            # 2. Tải bổ sung bất kỳ file model hoặc catalog nào còn thiếu từ Hugging Face
            need_hf_model = not self.svd_path.exists() or not self.sim_path.exists()
            need_hf_catalog = not self.web_parquet_path.exists() and not self.clean_parquet_path.exists()
            if need_hf_model or need_hf_catalog:
                self._download_default_from_hf(force=False)

            # 3. Nạp catalog & model vào RAM
            self._load_catalog_to_ram()
            self._load_models_to_ram()

            self._cache.clear()
            self._last_checked_at = time.time()

    def check_for_model_updates(self):
        """Tự động phát hiện nếu ML Pipeline vừa cập nhật file model mới trên Local hoặc Azure Blob."""
        now = time.time()
        if now - self._last_checked_at < self.check_interval_sec:
            return

        with self._lock:
            self._last_checked_at = now
            local_updated = (
                self.svd_path.exists() and self.svd_path.stat().st_mtime > self._loaded_local_mtime
            )
            blob_updated = self._sync_from_azure_blob(force=False)

            if local_updated or blob_updated:
                if local_updated and not blob_updated:
                    self.model_source = "ml_pipeline_local_updated"
                logger.info("Phát hiện bản cập nhật model mới từ ML Pipeline -> Đang hot-reload...")
                self._load_catalog_to_ram()
                self._load_models_to_ram()
                self._cache.clear()

    def invalidate_user_cache(self, user_id: str):
        """Xóa cache gợi ý của user_id trên RAM khi Speed Layer vừa cập nhật Cosmos DB."""
        prefix = f"user:{user_id}:"
        with self._lock:
            for k in [key for key in self._cache if key.startswith(prefix)]:
                self._cache.pop(k, None)

    # --------------------------------------------------------------------------
    # 3. TRUY VẤN GỢI Ý (COSMOS DB O(1) + IN-MEMORY SVD/SIMILARITY FALLBACK)
    # --------------------------------------------------------------------------
    def _enrich_items(self, raw_items: List[Dict[str, Any]], rec_type: str, top_k: int) -> List[Dict[str, Any]]:
        results = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            pid = str(item.get("product_id") or "")
            if not pid:
                continue

            # Kết hợp dữ liệu có sẵn trong document Cosmos DB và metadata catalog trên RAM
            meta = self.catalog_map.get(pid)
            merged = {**item, **meta} if meta else dict(item)
            if not merged.get("name"):
                continue

            raw_large = merged.get("large_urls")
            if hasattr(raw_large, "tolist"):
                large_urls = raw_large.tolist()
            elif isinstance(raw_large, list):
                large_urls = raw_large
            else:
                large_urls = []

            thumb = merged.get("thumbnail_url") or merged.get("thumb_url") or merged.get("image_url")
            img = merged.get("image_url") or merged.get("hi_res_url") or thumb

            merged["product_id"] = pid
            merged["name"] = str(merged["name"])
            merged["category"] = merged.get("category") or "Musical Instruments"
            merged["price"] = float(merged.get("price") or 0.0)
            merged["thumbnail_url"] = thumb
            merged["thumb_url"] = merged.get("thumb_url") or thumb
            merged["image_url"] = img
            merged["hi_res_url"] = merged.get("hi_res_url") or img
            merged["large_urls"] = large_urls
            merged["stock_quantity"] = int(merged.get("stock_quantity") or 100)
            merged["rating"] = float(merged.get("rating") or 4.6)
            merged["rating_count"] = int(merged.get("rating_count") or 25)
            merged["score"] = round(float(item.get("score") or item.get("similarity_score") or 0.0), 4)
            merged["rank"] = len(results) + 1
            merged["recommendation_type"] = rec_type
            if "bundle_type" in item:
                merged["bundle_type"] = item["bundle_type"]

            results.append(merged)
            if len(results) >= top_k:
                break
        return results

    def get_trending_recommendations(self, top_k: int = 10) -> Dict[str, Any]:
        self.check_for_model_updates()
        cache_key = f"trending:{top_k}"
        if cache_key in self._cache and time.time() - self._cache[cache_key][0] < self._cache_ttl:
            return self._cache[cache_key][1]

        items: List[Dict[str, Any]] = []
        data_source = "in_memory_fallback"

        if self.cosmos_connected and self.meta_container is not None:
            try:
                doc = self.meta_container.read_item(item="popular_items", partition_key="popular_items")
                raw = (
                    doc.get("recommendations")
                    or doc.get("items")
                    or [{"product_id": pid, "score": 5.0} for pid in doc.get("popular_product_ids", [])]
                )
                items = self._enrich_items(raw, rec_type="popular", top_k=top_k)
                if items:
                    data_source = "cosmos_db"
            except Exception:
                pass

        if not items and self.popular_product_ids:
            raw = [
                {"product_id": pid, "score": self.catalog_map[pid].get("rating", 4.5)}
                for pid in self.popular_product_ids[: top_k * 2]
            ]
            items = self._enrich_items(raw, rec_type="popular", top_k=top_k)
            data_source = "in_memory_fallback"

        res = {
            "strategy": "cold_start_popular",
            "data_source": data_source,
            "model_version": self.model_version,
            "recommendations": items,
        }
        self._cache[cache_key] = (time.time(), res)
        return res

    def get_user_recommendations(self, user_id: str, top_k: int = 10) -> Dict[str, Any]:
        self.check_for_model_updates()
        cache_key = f"user:{user_id}:{top_k}"
        if cache_key in self._cache and time.time() - self._cache[cache_key][0] < self._cache_ttl:
            return self._cache[cache_key][1]

        # 1. Thử đọc O(1) từ Cosmos DB
        if self.cosmos_connected and self.user_container is not None:
            try:
                doc = self.user_container.read_item(item=user_id, partition_key=user_id)
                items = self._enrich_items(doc.get("recommendations", []), rec_type="personalized", top_k=top_k)
                if items:
                    res = {
                        "strategy": doc.get("strategy") or "svd_personalized",
                        "data_source": "cosmos_db",
                        "model_version": doc.get("model_version", self.model_version),
                        "recommendations": items,
                    }
                    self._cache[cache_key] = (time.time(), res)
                    return res
            except Exception:
                pass

        # 2. Tính trực tiếp từ ma trận TruncatedSVD trên RAM (HF default hoặc ML updated)
        if isinstance(self.svd_data, dict):
            user2idx = self.svd_data.get("user2idx") or self.svd_data.get("user_to_idx") or {}
            if user_id in user2idx and "P" in self.svd_data and "Q" in self.svd_data:
                u_idx = user2idx[user_id]
                P = self.svd_data["P"]
                Q = self.svd_data["Q"]
                idx2item = self.svd_data.get("idx2item") or {i: pid for i, pid in enumerate(self.sim_item_ids)}

                scores = P[u_idx] @ Q.T
                ranked_indices = np.argsort(scores)[::-1]
                raw = [
                    {"product_id": str(idx2item[int(it_idx)]), "score": float(scores[it_idx])}
                    for it_idx in ranked_indices[: top_k * 2]
                    if int(it_idx) in idx2item
                ]
                items = self._enrich_items(raw, rec_type="personalized", top_k=top_k)
                if items:
                    res = {
                        "strategy": "svd_personalized",
                        "data_source": "in_memory_svd",
                        "model_version": self.model_version,
                        "recommendations": items,
                    }
                    self._cache[cache_key] = (time.time(), res)
                    return res

        # 3. Cold-start fallback về Top Trending
        return self.get_trending_recommendations(top_k=top_k)

    def get_frequently_bought_together(self, product_id: str, top_k: int = 5) -> Dict[str, Any]:
        self.check_for_model_updates()
        cache_key = f"item:{product_id}:{top_k}"
        if cache_key in self._cache and time.time() - self._cache[cache_key][0] < self._cache_ttl:
            return self._cache[cache_key][1]

        # 1. Thử đọc O(1) từ Cosmos DB
        if self.cosmos_connected and self.item_container is not None:
            try:
                doc = self.item_container.read_item(item=product_id, partition_key=product_id)
                items = self._enrich_items(
                    doc.get("frequently_bought_together", []), rec_type="bundle", top_k=top_k
                )
                if items:
                    res = {
                        "data_source": "cosmos_db",
                        "model_version": doc.get("model_version", self.model_version),
                        "frequently_bought_together": items,
                    }
                    self._cache[cache_key] = (time.time(), res)
                    return res
            except Exception:
                pass

        # 2. Tính từ ma trận Hybrid Item Similarity trên RAM (hỗ trợ cả sparse & dense)
        item2idx = {pid: i for i, pid in enumerate(self.sim_item_ids)}
        if not item2idx and isinstance(self.svd_data, dict):
            item2idx = self.svd_data.get("item2idx") or self.svd_data.get("item_to_idx") or {}
        idx2item = {int(i): str(pid) for pid, i in item2idx.items()}

        if self.hybrid_sim is not None and product_id in item2idx:
            it_idx = int(item2idx[product_id])
            if it_idx < self.hybrid_sim.shape[0]:
                sims = (
                    self.hybrid_sim[it_idx].toarray().ravel()
                    if sp.issparse(self.hybrid_sim)
                    else np.asarray(self.hybrid_sim[it_idx]).ravel().copy()
                )
                sims[it_idx] = -1.0
                top_indices = np.argsort(sims)[::-1][: top_k * 3]
                base_cat = self.catalog_map.get(product_id, {}).get("category", "")
                raw = []
                for b_idx in top_indices:
                    b_idx_int = int(b_idx)
                    sim_val = float(sims[b_idx_int])
                    if sim_val <= 0 or b_idx_int not in idx2item:
                        continue
                    b_pid = idx2item[b_idx_int]
                    b_cat = self.catalog_map.get(b_pid, {}).get("category", "")
                    raw.append({
                        "product_id": b_pid,
                        "similarity_score": sim_val,
                        "bundle_type": "accessory" if (base_cat and b_cat and base_cat != b_cat) else "co-purchase",
                    })
                items = self._enrich_items(raw, rec_type="bundle", top_k=top_k)
                if items:
                    res = {
                        "data_source": "in_memory_similarity",
                        "model_version": self.model_version,
                        "frequently_bought_together": items,
                    }
                    self._cache[cache_key] = (time.time(), res)
                    return res

        # 3. Fallback cùng danh mục từ catalog trên RAM
        target_cat = self.catalog_map.get(product_id, {}).get("category")
        same_cat_pids = [
            pid for pid in self.popular_product_ids
            if pid != product_id and (not target_cat or self.catalog_map[pid].get("category") == target_cat)
        ]
        if len(same_cat_pids) < top_k:
            same_cat_pids.extend(
                [pid for pid in self.popular_product_ids if pid != product_id and pid not in same_cat_pids]
            )

        raw_fb = [
            {"product_id": pid, "similarity_score": 0.5, "bundle_type": "co-purchase"}
            for pid in same_cat_pids[: top_k * 2]
        ]
        items = self._enrich_items(raw_fb, rec_type="bundle", top_k=top_k)
        res = {
            "data_source": "fallback_catalog",
            "model_version": self.model_version,
            "frequently_bought_together": items,
        }
        self._cache[cache_key] = (time.time(), res)
        return res