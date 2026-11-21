"""
ml_pipeline/pipeline_runner.py
Entrypoint điều phối toàn bộ chu trình Tự động hóa ML:
1. ETL từ PostgreSQL & Blob Storage
2. Huấn luyện Mô hình & đẩy artifacts lên Blob Storage
3. Cập nhật Precomputed Recommendations vào Cosmos DB
4. Gửi tín hiệu Hot-Reload sang Recommender Service để dùng model mới ngay lập tức
"""

import argparse
import logging
import os
import sys
import urllib.request

from .etl_extractor import ETLExtractor
from .export_to_cosmos import CosmosDBExporter
from .train_recommender import RecommenderTrainer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PipelineRunner")


def notify_recommender_reload():
    rec_url = os.getenv("RECOMMENDER_SERVICE_URL", "http://localhost:8003").rstrip("/")
    reload_endpoint = f"{rec_url}/api/v1/recommendations/reload"
    try:
        req = urllib.request.Request(reload_endpoint, data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            logger.info(f"Đã kích hoạt Hot-Reload Recommender Service ({resp.status}): {body}")
    except Exception as exc:
        logger.warning(f"Không thể gọi reload trực tiếp tới {reload_endpoint} ({exc}). Service sẽ tự đồng bộ theo chu kỳ.")


def run_pipeline(dry_run: bool = False, model_version: str | None = None, force: bool = False):
    logger.info(">>> [BƯỚC 1/3] CHẠY ETL TỪ DATABASE VÀ BLOB STORAGE <<<")
    etl = ETLExtractor()
    etl.run()

    logger.info(">>> [BƯỚC 2/3] HUẤN LUYỆN MÔ HÌNH VÀ SYNC ARTIFACTS <<<")
    trainer = RecommenderTrainer(model_version=model_version)
    trained = trainer.run(force=force)
    if not trained and not force:
        logger.info("Pipeline dừng sớm theo chính sách Cooldown / Ngưỡng dữ liệu tối thiểu.")
        return

    logger.info(">>> [BƯỚC 3/3] XUẤT PRECOMPUTED RECS VÀO COSMOS DB <<<")
    exporter = CosmosDBExporter()
    exporter.run(dry_run=dry_run, force=force)

    notify_recommender_reload()
    logger.info(">>> TOÀN BỘ PIPELINE ĐÃ HOÀN TẤT THÀNH CÔNG <<<")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chạy toàn bộ luồng ETL -> Train -> Cosmos DB")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ xuất JSON cục bộ, không ghi lên Cosmos DB")
    parser.add_argument("--model-version", type=str, default=None, help="Nhãn phiên bản model (vd: v1.0-svd, v2.0-svd)")
    parser.add_argument("--force", action="store_true", help="Ép chạy retrain & export ngay lập tức")
    args = parser.parse_args()

    try:
        run_pipeline(dry_run=args.dry_run, model_version=args.model_version, force=args.force)
    except Exception as e:
        logger.error(f"Pipeline gặp sự cố nghiêm trọng: {str(e)}", exc_info=True)
        sys.exit(1)