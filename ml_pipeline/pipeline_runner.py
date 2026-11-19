"""
ml_pipeline/pipeline_runner.py
Entrypoint điều phối toàn bộ chu trình Tự động hóa ML:
1. ETL từ PostgreSQL & Blob Storage
2. Huấn luyện Mô hình & đẩy artifacts lên Blob Storage
3. Cập nhật Precomputed Recommendations vào Cosmos DB
"""

import argparse
import sys
import logging
from .etl_extractor import ETLExtractor
from .train_recommender import RecommenderTrainer
from .export_to_cosmos import CosmosDBExporter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PipelineRunner")


def run_pipeline(dry_run: bool = False, model_version: str | None = None):
    logger.info(">>> [BƯỚC 1/3] CHẠY ETL TỪ DATABASE VÀ BLOB STORAGE <<<")
    etl = ETLExtractor()
    etl.run()

    logger.info(">>> [BƯỚC 2/3] HUẤN LUYỆN MÔ HÌNH VÀ SYNC ARTIFACTS <<<")
    trainer = RecommenderTrainer(model_version=model_version)
    trainer.run()

    logger.info(">>> [BƯỚC 3/3] XUẤT PRECOMPUTED RECS VÀO COSMOS DB <<<")
    exporter = CosmosDBExporter()
    exporter.run(dry_run=dry_run)

    logger.info(">>> TOÀN BỘ PIPELINE ĐÃ HOÀN TẤT THÀNH CÔNG <<<")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chạy toàn bộ luồng ETL -> Train -> Cosmos DB")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ xuất JSON cục bộ, không ghi lên Cosmos DB")
    parser.add_argument("--model-version", type=str, default=None, help="Nhãn phiên bản model (vd: v1.0-svd, v2.0-svd)")
    args = parser.parse_args()

    try:
        run_pipeline(dry_run=args.dry_run, model_version=args.model_version)
    except Exception as e:
        logger.error(f"Pipeline gặp sự cố nghiêm trọng: {str(e)}", exc_info=True)
        sys.exit(1)