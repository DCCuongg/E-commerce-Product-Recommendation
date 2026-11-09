"""
services/recommender_service/main.py
Microservice 3: Model Serving API (Port 8003 - Hỗ trợ Blue/Green Deployment trên AKS).
Các Endpoint chính:
- GET /api/v1/recommendations/{user_id}: Gợi ý cá nhân hóa Top-K cho người dùng (kèm Cold-Start Fallback).
- GET /api/v1/products/{product_id}/frequently-bought-together: Gợi ý Top-5 sản phẩm thường mua cùng (Bundle).
- GET /api/v1/recommendations/popular/trending: Danh sách sản phẩm thịnh hành.
- POST /api/v1/recommendations/reload: Nạp lại Model Artifacts và xóa Cache không gián đoạn dịch vụ.
"""

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .cosmos_client import RecommenderCosmosClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [RecommenderService] %(message)s",
)
logger = logging.getLogger("recommender_service")

# Biến định danh phiên bản phục vụ kiểm thử Blue/Green Deployment trên AKS
DEPLOYMENT_SLOT = os.getenv("DEPLOYMENT_SLOT", "blue")
MODEL_VERSION = os.getenv("MODEL_VERSION", "v1.0-svd")

rec_client = RecommenderCosmosClient()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Khởi tạo kết nối Cosmos DB, nạp danh mục sản phẩm và ma trận tương đồng vào RAM khi pod khởi động."""
    logger.info(
        f"Đang khởi động Recommender Service (Slot={DEPLOYMENT_SLOT}, Model={MODEL_VERSION})..."
    )
    rec_client.initialize()
    yield


app = FastAPI(
    title="E-Commerce Recommender Serving API",
    description=(
        "Model Serving API truy vấn O(1) từ Azure Cosmos DB kết hợp Hybrid Cosine Similarity & TruncatedSVD "
        "(Port 8003 - Hỗ trợ Blue/Green Deployment)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------------------
# PYDANTIC RESPONSE SCHEMAS
# ------------------------------------------------------------------------------
class RecommendedItemSchema(BaseModel):
    product_id: str
    name: str
    category: Optional[str] = None
    price: float
    thumbnail_url: Optional[str] = None
    image_url: Optional[str] = None
    stock_quantity: int = 100
    rating: float = 4.6
    rating_count: int = 25
    score: Optional[float] = None
    rank: int = 1
    recommendation_type: Optional[str] = None


class UserRecommendationResponse(BaseModel):
    user_id: str
    strategy: str
    data_source: str
    model_version: str
    deployment_slot: str
    latency_ms: float
    count: int
    recommendations: List[RecommendedItemSchema]


class BundleItemSchema(BaseModel):
    product_id: str
    name: str
    category: Optional[str] = None
    price: float
    thumbnail_url: Optional[str] = None
    image_url: Optional[str] = None
    stock_quantity: int = 100
    rating: float = 4.6
    rating_count: int = 25
    similarity_score: float
    bundle_type: str
    rank: int = 1


class ItemBundleResponse(BaseModel):
    product_id: str
    data_source: str
    model_version: str
    deployment_slot: str
    latency_ms: float
    count: int
    frequently_bought_together: List[BundleItemSchema]


# ------------------------------------------------------------------------------
# 1. HEALTH CHECK (PHỤC VỤ KUBERNETES READINESS / LIVENESS PROBE CHO BLUE/GREEN)
# ------------------------------------------------------------------------------
@app.get("/health", tags=["Health & Blue-Green Info"])
def health_check():
    return {
        "service": "recommender_service",
        "status": "healthy",
        "port": 8003,
        "deployment_slot": DEPLOYMENT_SLOT,
        "model_version": rec_client.model_version or MODEL_VERSION,
        "cosmos_db_connected": rec_client.cosmos_connected,
        "item_similarity_loaded": rec_client.item_sim_matrix is not None,
        "svd_model_loaded": rec_client.svd_artifacts is not None,
        "catalog_products_cached": len(rec_client.product_catalog),
    }


# ------------------------------------------------------------------------------
# 2. ENDPOINT GỢI Ý TOP-K CÁ NHÂN HÓA CHO NGƯỜI DÙNG
# ------------------------------------------------------------------------------
@app.get(
    "/api/v1/recommendations/popular/trending",
    response_model=UserRecommendationResponse,
    tags=["Recommendations"],
)
def get_trending_recommendations(
    top_k: int = Query(default=10, ge=1, le=50, description="Số lượng sản phẩm gợi ý"),
):
    """Lấy danh sách Top-K sản phẩm thịnh hành nhất (Dùng cho khách vãng lai / Cold-Start)."""
    t0 = time.perf_counter()
    items = rec_client.get_popular_items(top_k=top_k)
    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    return UserRecommendationResponse(
        user_id="anonymous",
        strategy="cold_start_popular",
        data_source="cosmos_db" if rec_client.cosmos_connected else "in_memory_fallback",
        model_version=rec_client.model_version,
        deployment_slot=DEPLOYMENT_SLOT,
        latency_ms=latency_ms,
        count=len(items),
        recommendations=[RecommendedItemSchema(**it) for it in items],
    )


@app.get(
    "/api/v1/recommendations/{user_id}",
    response_model=UserRecommendationResponse,
    tags=["Recommendations"],
)
def get_recommendations_for_user(
    user_id: str,
    top_k: int = Query(default=10, ge=1, le=50, description="Số lượng sản phẩm gợi ý"),
):
    """
    Trả về danh sách Top-K sản phẩm gợi ý cá nhân hóa cho `user_id` (Màn hình Trang chủ):
    - Đọc O(1) từ Azure Cosmos DB (`user_recommendations`) hoặc ma trận SVD.
    - Tự động fallback về Top Trending (`system_metadata`) nếu là người dùng mới (Cold-start).
    """
    t0 = time.perf_counter()
    items, strategy, source = rec_client.get_user_recommendations(
        user_id=user_id, top_k=top_k
    )
    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    return UserRecommendationResponse(
        user_id=user_id,
        strategy=strategy,
        data_source=source,
        model_version=rec_client.model_version,
        deployment_slot=DEPLOYMENT_SLOT,
        latency_ms=latency_ms,
        count=len(items),
        recommendations=[RecommendedItemSchema(**it) for it in items],
    )


# ------------------------------------------------------------------------------
# 3. ENDPOINT GỢI Ý SẢN PHẨM THƯỜNG ĐƯỢC MUA CÙNG (ITEM-TO-ITEM BUNDLES)
# ------------------------------------------------------------------------------
@app.get(
    "/api/v1/products/{product_id}/frequently-bought-together",
    response_model=ItemBundleResponse,
    tags=["Item-to-Item Bundles"],
)
def get_frequently_bought_together(
    product_id: str,
    top_k: int = Query(default=5, ge=1, le=20, description="Số lượng sản phẩm mua kèm"),
):
    """
    Trả về danh sách Top-5 sản phẩm thường được mua cùng với `product_id`
    (Phục vụ khối 'Sản phẩm thường được mua cùng' tại Trang chi tiết sản phẩm).
    """
    t0 = time.perf_counter()
    bundles, source = rec_client.get_item_bundles(product_id=product_id, top_k=top_k)
    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    return ItemBundleResponse(
        product_id=product_id,
        data_source=source,
        model_version=rec_client.model_version,
        deployment_slot=DEPLOYMENT_SLOT,
        latency_ms=latency_ms,
        count=len(bundles),
        frequently_bought_together=[BundleItemSchema(**b) for b in bundles],
    )


@app.get(
    "/api/v1/recommendations/item/{product_id}",
    response_model=ItemBundleResponse,
    tags=["Item-to-Item Bundles"],
)
def get_item_recommendations_alias(
    product_id: str,
    top_k: int = Query(default=5, ge=1, le=20),
):
    """Alias cho endpoint `/api/v1/products/{product_id}/frequently-bought-together`."""
    return get_frequently_bought_together(product_id=product_id, top_k=top_k)


# ------------------------------------------------------------------------------
# 4. ENDPOINT HOT-RELOAD MODEL ARTIFACTS & CLEAR CACHE
# ------------------------------------------------------------------------------
@app.post("/api/v1/recommendations/reload", tags=["Admin & MLOps"])
def reload_models_and_cache():
    """Nạp lại Model Artifacts từ Azure Blob / Local và làm mới bộ nhớ đệm."""
    rec_client.cache.clear()
    rec_client.initialize()
    return {
        "status": "reloaded",
        "model_version": rec_client.model_version,
        "deployment_slot": DEPLOYMENT_SLOT,
        "cosmos_connected": rec_client.cosmos_connected,
        "catalog_size": len(rec_client.product_catalog),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.recommender_service.main:app", host="0.0.0.0", port=8003, reload=True
    )
