"""
services/recommender_service/main.py
Microservice 3: Model Serving API (Port 8003 - Hỗ trợ Blue/Green Deployment trên AKS).
Các Endpoint chính:
- GET /health: Kiểm tra sức khỏe pod & trạng thái nạp Model trên RAM (Readiness/Liveness Probe).
- GET /api/v1/recommendations/popular/trending: Danh sách sản phẩm thịnh hành (Cold-Start).
- GET /api/v1/recommendations/{user_id}: Gợi ý cá nhân hóa Top-K cho người dùng.
- POST /api/v1/recommendations/{user_id}/refresh: Cập nhật gợi ý cá nhân hóa lên Cosmos DB theo chính sách (>10 logs & >30s).
- GET /api/v1/products/{product_id}/frequently-bought-together: Gợi ý sản phẩm thường mua cùng.
- POST /api/v1/recommendations/reload: Nạp lại Model Artifacts & làm mới Cache không gián đoạn dịch vụ.
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field

from .cosmos_client import RecommenderCosmosClient
from .realtime_updater import UserRealtimeRecUpdater

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [RecommenderService] %(message)s",
)
logger = logging.getLogger("recommender_service")

rec_client = RecommenderCosmosClient()
realtime_updater = UserRealtimeRecUpdater(
    rec_client=rec_client,
    min_new_logs=10,       # Phải > 10 log mới
    cooldown_seconds=30,   # Phải > 30 giây từ lần cập nhật trước
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ghi nhận trạng thái khởi tạo Cosmos DB, danh mục sản phẩm và ma trận model khi pod khởi động."""
    logger.info(
        "Khởi động Recommender Service | Slot=%s | Model=%s | Source=%s | Cosmos=%s | Catalog=%d | SVD=%s | Sim=%s",
        rec_client.deployment_slot,
        rec_client.model_version,
        rec_client.model_source,
        rec_client.cosmos_connected,
        len(rec_client.catalog_map),
        rec_client.svd_data is not None,
        rec_client.hybrid_sim is not None,
    )
    yield
    logger.info("Đang tắt Recommender Service (Slot=%s)...", rec_client.deployment_slot)


app = FastAPI(
    title="E-Commerce Recommender Serving API",
    description=(
        "Model Serving API độ trễ thấp: Truy vấn O(1) từ Azure Cosmos DB kết hợp "
        "In-Memory Hybrid Cosine Similarity & TruncatedSVD (Hỗ trợ Blue/Green Deployment)."
    ),
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Nén payload JSON trả về bằng Gzip (Theo Rubric Tiêu chí 3.4 - Data Compression)
app.add_middleware(GZipMiddleware, minimum_size=500)


# ------------------------------------------------------------------------------
# PYDANTIC RESPONSE SCHEMAS
# ------------------------------------------------------------------------------
class RecommendedItemSchema(BaseModel):
    product_id: str
    name: str
    category: Optional[str] = None
    price: float
    thumbnail_url: Optional[str] = None
    thumb_url: Optional[str] = None
    image_url: Optional[str] = None
    hi_res_url: Optional[str] = None
    large_urls: List[str] = Field(default_factory=list)
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
    thumb_url: Optional[str] = None
    image_url: Optional[str] = None
    hi_res_url: Optional[str] = None
    large_urls: List[str] = Field(default_factory=list)
    stock_quantity: int = 100
    rating: float = 4.6
    rating_count: int = 25
    similarity_score: float = 0.0
    score: Optional[float] = None
    bundle_type: str = "frequently_bought_together"
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
# 1. HEALTH CHECK (KUBERNETES READINESS / LIVENESS PROBE CHO BLUE/GREEN)
# ------------------------------------------------------------------------------
@app.get("/health", tags=["Health & Blue-Green Info"])
def health_check():
    svd_loaded = rec_client.svd_data is not None
    sim_loaded = rec_client.hybrid_sim is not None
    catalog_count = len(rec_client.catalog_map)

    return {
        "status": "healthy",
        "service": "recommender-service",
        "port": 8003,
        "deployment_slot": rec_client.deployment_slot,
        "model_version": rec_client.model_version,
        "model_source": rec_client.model_source,
        # Giữ cả hai bộ tên trường để tương thích ngược với mọi script kiểm thử
        "cosmos_connected": rec_client.cosmos_connected,
        "cosmos_db_connected": rec_client.cosmos_connected,
        "svd_model_loaded": svd_loaded,
        "item_similarity_loaded": sim_loaded,
        "catalog_size": catalog_count,
        "catalog_products_cached": catalog_count,
    }


# ------------------------------------------------------------------------------
# 2. ENDPOINT GỢI Ý TOP-K CÁ NHÂN HÓA & COLD-START
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
    result = rec_client.get_trending_recommendations(top_k=top_k)
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    items = result["recommendations"]

    return UserRecommendationResponse(
        user_id="anonymous",
        strategy=result["strategy"],
        data_source=result["data_source"],
        model_version=result["model_version"],
        deployment_slot=rec_client.deployment_slot,
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
    - Đọc O(1) từ Azure Cosmos DB (`user_recommendations`) hoặc tính trực tiếp từ ma trận SVD trên RAM.
    - Tự động fallback về Top Trending nếu là người dùng mới (Cold-start).
    """
    t0 = time.perf_counter()
    result = rec_client.get_user_recommendations(user_id=user_id, top_k=top_k)
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    items = result["recommendations"]

    return UserRecommendationResponse(
        user_id=user_id,
        strategy=result["strategy"],
        data_source=result["data_source"],
        model_version=result["model_version"],
        deployment_slot=rec_client.deployment_slot,
        latency_ms=latency_ms,
        count=len(items),
        recommendations=[RecommendedItemSchema(**it) for it in items],
    )


@app.post("/api/v1/recommendations/{user_id}/refresh", tags=["Recommendations"])
def refresh_user_recommendations(
    user_id: str,
    top_k: int = Query(default=10, ge=1, le=50, description="Số lượng sản phẩm gợi ý"),
):
    """
    Frontend gọi sau khi gửi log hành vi để kích hoạt cập nhật gợi ý trên Cosmos DB
    khi thỏa mãn: (1) > 30s từ lần cập nhật trước VÀ (2) > 10 log tương tác mới.
    """
    return realtime_updater.refresh_if_eligible(user_id=user_id, top_k=top_k)


# ------------------------------------------------------------------------------
# 3. ENDPOINT GỢI Ý SẢN PHẨM THƯỜNG ĐƯỢC MUA CÙNG (ITEM-TO-ITEM BUNDLES)
# ------------------------------------------------------------------------------
@app.get(
    "/api/v1/products/{product_id}/frequently-bought-together",
    response_model=ItemBundleResponse,
    tags=["Item-to-Item Bundles"],
)
@app.get(
    "/api/v1/recommendations/item/{product_id}",
    response_model=ItemBundleResponse,
    tags=["Item-to-Item Bundles"],
)
def get_frequently_bought_together(
    product_id: str,
    top_k: int = Query(default=5, ge=1, le=20, description="Số lượng sản phẩm mua kèm"),
):
    """
    Trả về danh sách Top-K sản phẩm thường được mua cùng với `product_id`
    (Phục vụ khối 'Sản phẩm thường được mua cùng' tại Trang chi tiết sản phẩm).
    """
    t0 = time.perf_counter()
    result = rec_client.get_frequently_bought_together(product_id=product_id, top_k=top_k)
    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    items = result["frequently_bought_together"]

    normalized_bundles: List[BundleItemSchema] = []
    for it in items:
        item_data: Dict[str, Any] = dict(it)
        if item_data.get("similarity_score") is None:
            item_data["similarity_score"] = float(item_data.get("score") or 0.0)
        if not item_data.get("bundle_type"):
            item_data["bundle_type"] = "frequently_bought_together"
        normalized_bundles.append(BundleItemSchema(**item_data))

    return ItemBundleResponse(
        product_id=product_id,
        data_source=result["data_source"],
        model_version=result["model_version"],
        deployment_slot=rec_client.deployment_slot,
        latency_ms=latency_ms,
        count=len(normalized_bundles),
        frequently_bought_together=normalized_bundles,
    )


# ------------------------------------------------------------------------------
# 4. ENDPOINT HOT-RELOAD MODEL ARTIFACTS & CLEAR CACHE (MLOPS)
# ------------------------------------------------------------------------------
@app.post("/api/v1/recommendations/reload", tags=["Admin & MLOps"])
def reload_models_and_cache(
    force_download: bool = Query(
        default=False,
        description="Ép tải lại model & catalog mới nhất từ Azure Blob / Hugging Face",
    ),
):
    """Nạp lại Model Artifacts và xóa Cache không gián đoạn dịch vụ."""
    logger.info("Nhận yêu cầu reload model (force_download=%s)...", force_download)
    rec_client.reload_all(force_download=force_download)
    return {
        "status": "reloaded",
        "model_version": rec_client.model_version,
        "model_source": rec_client.model_source,
        "deployment_slot": rec_client.deployment_slot,
        "cosmos_connected": rec_client.cosmos_connected,
        "catalog_size": len(rec_client.catalog_map),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.recommender_service.main:app",
        host="0.0.0.0",
        port=8003,
        reload=True,
    )