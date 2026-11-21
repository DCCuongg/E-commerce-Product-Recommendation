"""
services/recommender_service/realtime_updater.py
Near-Real-Time Speed Layer: Cập nhật gợi ý cá nhân hóa trên Cosmos DB cho từng user
khi thỏa mãn đồng thời 2 điều kiện:
1. Thời gian từ lần cập nhật gần nhất trên Cosmos DB > 30 giây (Cooldown).
2. Số lượng log tương tác mới phát sinh sau lần cập nhật đó > 10 sự kiện.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import scipy.sparse as sp
from azure.cosmos import CosmosClient
from azure.storage.blob import BlobServiceClient

logger = logging.getLogger("recommender_service.realtime")

ACTION_WEIGHTS = {
    "view": 1.0,
    "click": 2.0,
    "add_to_cart": 3.0,
    "checkout": 4.0,
    "purchase": 5.0,
    "rating": 5.0,
}


def _parse_iso_utc(ts_str: Optional[str]) -> Optional[datetime]:
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


class UserRealtimeRecUpdater:
    def __init__(self, rec_client: Any, min_new_logs: int = 10, cooldown_seconds: int = 30):
        self.rec_client = rec_client
        self.min_new_logs = min_new_logs
        self.cooldown_seconds = cooldown_seconds

        # Chốt chặn nhanh trên RAM để tránh tốn RU đọc Cosmos nếu user spam liên tục trong < 30s
        self._memory_last_updated: Dict[str, datetime] = {}

        self._user_container = None
        self._blob_container = None
        self._init_clients()

    def _init_clients(self):
        endpoint = os.getenv("COSMOS_DB_ENDPOINT")
        key = os.getenv("COSMOS_DB_PRIMARY_KEY")
        db_name = os.getenv("COSMOS_DB_DATABASE_NAME", "ecommerce_recommender_db")
        user_coll = os.getenv("COSMOS_CONTAINER_USER_RECS", "user_recommendations")

        if endpoint and key:
            try:
                client = CosmosClient(
                    url=endpoint,
                    credential=key,
                    connection_verify=False,
                    enable_endpoint_discovery=False,
                )
                db = client.get_database_client(db_name)
                self._user_container = db.get_container_client(user_coll)
            except Exception as e:
                logger.warning("Không khởi tạo được Cosmos user_container cho realtime updater: %s", e)

        conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        logs_coll = os.getenv("BLOB_CONTAINER_INTERACTION_LOGS", "interaction-logs")
        if conn_str:
            try:
                blob_svc = BlobServiceClient.from_connection_string(conn_str)
                self._blob_container = blob_svc.get_container_client(logs_coll)
            except Exception as e:
                logger.warning("Không khởi tạo được Blob container cho realtime updater: %s", e)

    def _get_last_cosmos_updated_at(self, user_id: str) -> Optional[datetime]:
        if self._user_container is None:
            return self._memory_last_updated.get(user_id)
        try:
            doc = self._user_container.read_item(item=user_id, partition_key=user_id)
            dt = _parse_iso_utc(doc.get("updated_at"))
            if dt:
                self._memory_last_updated[user_id] = dt
            return dt
        except Exception:
            return self._memory_last_updated.get(user_id)

    def _collect_user_events(
        self, user_id: str, since_dt: Optional[datetime]
    ) -> Tuple[int, Dict[str, float]]:
        """
        Quét log tương tác của `user_id` từ Blob Storage (và file local fallback):
        - Đếm số log mới có timestamp > `since_dt`.
        - Tổng hợp trọng số toàn bộ lịch sử tương tác {product_id: max_weight} để tính gợi ý.
        """
        new_logs_count = 0
        item_weights: Dict[str, float] = {}
        raw_lines: List[str] = []

        # 1. Đọc từ Azure Blob Storage / Azurite (quét các blob phân vùng gần nhất)
        if self._blob_container is not None:
            try:
                now_utc = datetime.now(timezone.utc)
                # Quét log của hôm nay và hôm qua (hoặc toàn bộ nếu chưa từng cập nhật)
                prefixes = (
                    [
                        f"logs/year={now_utc:%Y}/month={now_utc:%m}/day={now_utc:%d}/",
                        f"logs/year={(now_utc - timedelta(days=1)):%Y}/month={(now_utc - timedelta(days=1)):%m}/day={(now_utc - timedelta(days=1)):%d}/",
                    ]
                    if since_dt is not None
                    else ["logs/"]
                )
                seen_blobs = set()
                for prefix in prefixes:
                    for blob_props in self._blob_container.list_blobs(name_starts_with=prefix):
                        if blob_props.name in seen_blobs:
                            continue
                        seen_blobs.add(blob_props.name)
                        content = self._blob_container.get_blob_client(blob_props.name).download_blob().readall()
                        raw_lines.extend(content.decode("utf-8", errors="ignore").splitlines())
            except Exception as e:
                logger.warning("Lỗi đọc interaction-logs từ Blob Storage: %s", e)

        # 2. Bổ sung từ local fallback log nếu có
        local_log_path = os.path.abspath("data/raw/interaction_logs.jsonl")
        if os.path.exists(local_log_path):
            try:
                with open(local_log_path, "r", encoding="utf-8") as f:
                    raw_lines.extend(f.read().splitlines())
            except Exception:
                pass

        for line in raw_lines:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue

            if str(ev.get("user_id") or "") != user_id:
                continue

            pid = str(ev.get("product_id") or ev.get("item_id") or "")
            if not pid:
                continue

            action = str(ev.get("action") or "view").lower()
            weight = float(ev.get("rating") or ev.get("value") or ACTION_WEIGHTS.get(action, 1.0))
            item_weights[pid] = max(item_weights.get(pid, 0.0), weight)

            ev_dt = _parse_iso_utc(ev.get("ingested_at") or ev.get("timestamp"))
            if since_dt is None or (ev_dt is not None and ev_dt > since_dt):
                new_logs_count += 1

        return new_logs_count, item_weights

    def _compute_top_k_from_history(
        self, item_weights: Dict[str, float], top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """Tính Top-K cá nhân hóa trên RAM bằng Hybrid Similarity + SVD Folding-In."""
        catalog_map = getattr(self.rec_client, "catalog_map", {}) or {}
        sim_matrix = getattr(self.rec_client, "hybrid_sim", None)
        svd_data = getattr(self.rec_client, "svd_data", None)

        if not item_weights or sim_matrix is None or not catalog_map:
            return []

        # Lấy ánh xạ item_id -> index từ svd_data hoặc catalog_map
        sim_item_ids: List[str] = []
        if isinstance(svd_data, dict):
            item_to_idx = svd_data.get("item_to_idx") or svd_data.get("item2idx") or {}
            if not item_to_idx and svd_data.get("item_ids") is not None:
                item_to_idx = {str(it): i for i, it in enumerate(svd_data["item_ids"])}
            if item_to_idx:
                idx_to_item = {int(idx): str(pid) for pid, idx in item_to_idx.items()}
                sim_item_ids = [idx_to_item[i] for i in sorted(idx_to_item.keys())]

        if not sim_item_ids:
            sim_item_ids = list(catalog_map.keys())

        id_to_idx = {pid: i for i, pid in enumerate(sim_item_ids)}
        n_items = min(sim_matrix.shape[0], len(sim_item_ids))
        combined_scores = np.zeros(n_items, dtype=np.float32)
        user_vec = np.zeros(n_items, dtype=np.float32)

        for pid, w in item_weights.items():
            idx = id_to_idx.get(pid)
            if idx is None or idx >= n_items:
                continue
            user_vec[idx] = float(w)
            row = sim_matrix[idx].toarray().ravel() if sp.issparse(sim_matrix) else np.asarray(sim_matrix[idx]).ravel()
            combined_scores += float(w) * row[:n_items]

        # SVD Folding-In nếu có ma trận V
        if isinstance(svd_data, dict) and np.any(user_vec > 0):
            raw_v = svd_data.get("item_factors") if svd_data.get("item_factors") is not None else svd_data.get("Vt")
            if raw_v is not None:
                V = np.asarray(raw_v, dtype=np.float32)
                if V.shape[0] != n_items and V.shape[1] == n_items:
                    V = V.T
                if V.shape[0] == n_items:
                    svd_scores = (user_vec @ V) @ V.T
                    if np.max(np.abs(svd_scores)) > 0:
                        svd_scores /= np.max(np.abs(svd_scores))
                    if np.max(np.abs(combined_scores)) > 0:
                        combined_scores /= np.max(np.abs(combined_scores))
                    combined_scores = 0.65 * combined_scores + 0.35 * svd_scores

        # Loại trừ các sản phẩm user đã tương tác
        for pid in item_weights.keys():
            idx = id_to_idx.get(pid)
            if idx is not None and idx < n_items:
                combined_scores[idx] = -1e9

        recs: List[Dict[str, Any]] = []
        for cand_idx in np.argsort(combined_scores)[::-1]:
            cand_idx = int(cand_idx)
            score_val = float(combined_scores[cand_idx])
            if score_val <= -1e8:
                break
            cand_pid = sim_item_ids[cand_idx]
            if cand_pid in catalog_map:
                item_doc = dict(catalog_map[cand_pid])
                item_doc["score"] = round(score_val, 4)
                item_doc["rank"] = len(recs) + 1
                item_doc["recommendation_type"] = "near_realtime_personalized"
                recs.append(item_doc)
                if len(recs) >= top_k:
                    break
        return recs

    def refresh_if_eligible(self, user_id: str, top_k: int = 10) -> Dict[str, Any]:
        now_utc = datetime.now(timezone.utc)

        # 1. Kiểm tra điều kiện thời gian (> 30 giây kể từ lần cập nhật trước trên Cosmos DB)
        last_updated = self._get_last_cosmos_updated_at(user_id)
        if last_updated is not None:
            elapsed = (now_utc - last_updated).total_seconds()
            if elapsed <= self.cooldown_seconds:
                return {
                    "status": "skipped",
                    "reason": "cooldown_active",
                    "user_id": user_id,
                    "elapsed_seconds": round(elapsed, 2),
                    "retry_after_seconds": round(self.cooldown_seconds - elapsed, 2),
                    "updated_at": last_updated.isoformat(),
                }

        # 2. Kiểm tra điều kiện số lượng log mới (> 10 sự kiện sau mốc `last_updated`)
        new_logs_count, item_weights = self._collect_user_events(user_id, since_dt=last_updated)
        if new_logs_count <= self.min_new_logs:
            return {
                "status": "skipped",
                "reason": "insufficient_new_logs",
                "user_id": user_id,
                "new_logs_count": new_logs_count,
                "required_greater_than": self.min_new_logs,
                "updated_at": last_updated.isoformat() if last_updated else None,
            }

        # 3. Tính lại gợi ý Top-K và cập nhật lên Cosmos DB
        recs = self._compute_top_k_from_history(item_weights, top_k=top_k)
        if not recs:
            fallback = self.rec_client.get_trending_recommendations(top_k=top_k)
            recs = fallback.get("recommendations", [])

        now_iso = now_utc.isoformat()
        model_version = getattr(self.rec_client, "model_version", "v1.0-svd")

        if self._user_container is not None:
            self._user_container.upsert_item(
                {
                    "id": user_id,
                    "user_id": user_id,
                    "strategy": "near_realtime_hybrid",
                    "interaction_count": len(item_weights),
                    "new_logs_processed": new_logs_count,
                    "model_version": model_version,
                    "recommendations": recs,
                    "updated_at": now_iso,
                }
            )

        self._memory_last_updated[user_id] = now_utc

        # Xóa cache trên RAM của rec_client (nếu có) để lần GET kế tiếp lấy ngay bản mới
        for cache_attr in ("_user_cache", "user_cache", "cache"):
            cache_obj = getattr(self.rec_client, cache_attr, None)
            if isinstance(cache_obj, dict):
                cache_obj.pop(user_id, None)

        return {
            "status": "updated",
            "reason": "policy_satisfied",
            "user_id": user_id,
            "new_logs_count": new_logs_count,
            "updated_at": now_iso,
            "count": len(recs),
            "recommendations": recs,
        }