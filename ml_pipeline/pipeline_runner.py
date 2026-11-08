"""
ml_pipeline/pipeline_runner.py
Entrypoint điều phối toàn bộ chu trình Tự động hóa ML:
1. ETL từ PostgreSQL & Blob Storage
2. Huấn luyện Mô hình & đẩy artifacts lên Blob Storage
3. Cập nhật Precomputed Recommendations vào Cosmos DB
"""

import sys
import logging
from .etl_extractor import ETLExtractor
from .train_recommender import RecommenderTrainer
from .export_to_cosmos import CosmosDBExporter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PipelineRunner")


def run_pipeline():
    logger.info(">>> [BƯỚC 1/3] CHẠY ETL TỪ DATABASE VÀ BLOB STORAGE <<<")
    etl = ETLExtractor()
    etl.run()

    logger.info(">>> [BƯỚC 2/3] HUẤN LUYỆN MÔ HÌNH VÀ SYNC ARTIFACTS <<<")
    trainer = RecommenderTrainer()
    trainer.run()

    logger.info(">>> [BƯỚC 3/3] XUẤT PRECOMPUTED RECS VÀO COSMOS DB <<<")
    exporter = CosmosDBExporter()
    exporter.run(dry_run=False)

    logger.info(">>> TOÀN BỘ PIPELINE ĐÃ HOÀN TẤT THÀNH CÔNG <<<")


if __name__ == "__main__":
    try:
        run_pipeline()
    except Exception as e:
        logger.error(f"Pipeline gặp sự cố nghiêm trọng: {str(e)}", exc_info=True)
        sys.exit(1)