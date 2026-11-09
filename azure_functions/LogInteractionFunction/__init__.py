"""
azure_functions/LogInteractionFunction/__init__.py
FaaS (Function as a Service - Azure Functions HTTP Trigger):
Tiếp nhận bất đồng bộ các sự kiện tương tác của người dùng từ Web Frontend
(view, click, add_to_cart, rating, purchase) và ghi trực tiếp dưới dạng JSONL
vào Azure Blob Storage (container: `interaction-logs` phân vùng theo ngày)
để phục vụ chu trình ETL & Retraining tự động (`ml_pipeline/etl_extractor.py`).
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=ROOT_DIR / ".env")

logger = logging.getLogger("LogInteractionFunction")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [FaaS] %(message)s")

# Quy tắc ánh xạ hành vi Implicit Feedback sang thang điểm [1.0 - 5.0] (Theo README Tiêu chí 3.2)
ACTION_IMPLICIT_SCORES: Dict[str, float] = {
    "click": 1.0,
    "view": 2.0,
    "search": 1.5,
    "add_to_cart": 3.5,
    "cart": 3.5,
    "checkout": 4.5,
    "purchase": 5.0,
    "rating": 5.0,
    "review": 5.0,
}

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS, GET",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-User-Id",
    "Content-Type": "application/json",
}


def normalize_interaction_payload(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chuẩn hóa payload JSON từ Web Frontend về định dạng thống nhất cho cả
    Raw Data Lake và `ml_pipeline/etl_extractor.py`.
    """
    user_id = str(body.get("user_id") or body.get("userId") or "anonymous").strip()
    product_id = str(
        body.get("product_id") or body.get("item_id") or body.get("productId") or ""
    ).strip()

    if not product_id:
        raise ValueError("Thiếu trường bắt buộc 'product_id' (hoặc 'item_id').")

    action = str(body.get("action") or body.get("event_type") or "view").lower().strip()
    raw_value = body.get("value") if body.get("value") is not None else body.get("rating")

    if raw_value is not None:
        rating_score = float(raw_value)
        rating_score = max(1.0, min(5.0, rating_score))
    else:
        rating_score = ACTION_IMPLICIT_SCORES.get(action, 2.0)

    ts = int(body.get("timestamp") or time.time())
    now_dt = datetime.fromtimestamp(ts, tz=timezone.utc)

    return {
        "user_id": user_id,
        "item_id": product_id,
        "product_id": product_id,
        "action": action,
        "value": rating_score,
        "rating": rating_score,
        "timestamp": ts,
        "ingested_at": now_dt.isoformat(),
    }


def append_event_to_blob_storage(record: Dict[str, Any]) -> Dict[str, str]:
    """
    Ghi bản ghi JSONL vào Azure Blob Storage (container: `interaction-logs`)
    theo cấu trúc phân vùng ngày: `logs/year=YYYY/month=MM/day=DD/interactions_YYYYMMDD.jsonl`.
    Đồng thời lưu bản sao vào `data/raw/interaction_logs.jsonl` để dự phòng cục bộ.
    """
    json_line = json.dumps(record, ensure_ascii=False) + "\n"
    dt = datetime.fromtimestamp(record["timestamp"], tz=timezone.utc)
    blob_path = (
        f"logs/year={dt.year:04d}/month={dt.month:02d}/day={dt.day:02d}/"
        f"interactions_{dt.strftime('%Y%m%d')}.jsonl"
    )

    # 1. Ghi dự phòng cục bộ
    local_log_dir = ROOT_DIR / "data" / "raw"
    local_log_dir.mkdir(parents=True, exist_ok=True)
    local_log_file = local_log_dir / "interaction_logs.jsonl"
    with open(local_log_file, "a", encoding="utf-8") as f:
        f.write(json_line)

    # 2. Đẩy lên Azure Blob Storage / Azurite Emulator
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING") or os.getenv("AzureWebJobsStorage", "")
    container_name = os.getenv("BLOB_CONTAINER_INTERACTION_LOGS", "interaction-logs")

    if conn_str and "<AZURITE_" not in conn_str and "your_storage_account" not in conn_str:
        try:
            from azure.storage.blob import BlobServiceClient

            blob_service = BlobServiceClient.from_connection_string(conn_str)
            container_client = blob_service.get_container_client(container_name)
            try:
                container_client.create_container()
            except Exception:
                pass

            blob_client = container_client.get_blob_client(blob_path)
            existing_content = ""
            if blob_client.exists():
                existing_content = blob_client.download_blob().readall().decode("utf-8")

            blob_client.upload_blob(
                (existing_content + json_line).encode("utf-8"), overwrite=True
            )
            return {
                "storage": "azure_blob_storage",
                "container": container_name,
                "blob_path": blob_path,
            }
        except Exception as exc:
            logger.warning(f"Không thể ghi vào Azure Blob Storage ({exc}), đã lưu vào local log.")

    return {
        "storage": "local_fallback",
        "container": container_name,
        "blob_path": str(local_log_file),
    }


# ------------------------------------------------------------------------------
# ENTRYPOINT CHUẨN CỦA AZURE FUNCTIONS RUNTIME (azure.functions.HttpRequest)
# ------------------------------------------------------------------------------
try:
    import azure.functions as func
except ImportError:
    func = None


def main(req: "func.HttpRequest") -> "func.HttpResponse":
    """Entrypoint chính thức khi chạy trên Azure Functions (Consumption Plan / Core Tools)."""
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=CORS_HEADERS)

    if req.method == "GET":
        return func.HttpResponse(
            json.dumps(
                {
                    "function": "LogInteractionFunction",
                    "status": "ready",
                    "container": os.getenv("BLOB_CONTAINER_INTERACTION_LOGS", "interaction-logs"),
                }
            ),
            status_code=200,
            headers=CORS_HEADERS,
        )

    try:
        req_body = req.get_json()
        record = normalize_interaction_payload(req_body)
        storage_info = append_event_to_blob_storage(record)

        return func.HttpResponse(
            json.dumps(
                {
                    "status": "logged",
                    "event": record,
                    "destination": storage_info,
                },
                ensure_ascii=False,
            ),
            status_code=201,
            headers=CORS_HEADERS,
        )
    except ValueError as val_err:
        return func.HttpResponse(
            json.dumps({"error": "BAD_REQUEST", "message": str(val_err)}, ensure_ascii=False),
            status_code=400,
            headers=CORS_HEADERS,
        )
    except Exception as exc:
        logger.error(f"Lỗi khi ghi log tương tác: {exc}", exc_info=True)
        return func.HttpResponse(
            json.dumps({"error": "INTERNAL_ERROR", "message": str(exc)}, ensure_ascii=False),
            status_code=500,
            headers=CORS_HEADERS,
        )


# ------------------------------------------------------------------------------
# STANDALONE FASTAPI RUNNER (Cho phép chạy kiểm thử FaaS tại Port 7071 bằng Python thuần)
# ------------------------------------------------------------------------------
def create_standalone_faas_app():
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware

    faas_app = FastAPI(
        title="Azure Function - LogInteractionFunction (FaaS Emulator)",
        description="Hàm phi máy chủ thu thập sự kiện click/view/add-to-cart/rating ghi vào Azure Blob Storage (Port 7071).",
        version="1.0.0",
    )
    faas_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @faas_app.get("/health")
    @faas_app.get("/api/LogInteractionFunction")
    def health():
        return {
            "function": "LogInteractionFunction",
            "status": "healthy",
            "port": 7071,
            "container": os.getenv("BLOB_CONTAINER_INTERACTION_LOGS", "interaction-logs"),
        }

    @faas_app.post("/api/LogInteractionFunction", status_code=201)
    @faas_app.post("/api/v1/events/log", status_code=201)
    async def log_interaction_endpoint(request: Request):
        try:
            body = await request.json()
            record = normalize_interaction_payload(body)
            storage_info = append_event_to_blob_storage(record)
            return {
                "status": "logged",
                "event": record,
                "destination": storage_info,
            }
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err))

    return faas_app


if __name__ == "__main__":
    import uvicorn

    app = create_standalone_faas_app()
    uvicorn.run(app, host="0.0.0.0", port=7071)
