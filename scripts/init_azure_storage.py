"""
scripts/init_azure_storage.py
Mục đích: Tự động khởi tạo hạ tầng Cloud Storage & NoSQL Database cho dự án E-commerce Recommender.
Không cần thao tác thủ công trên giao diện Azure Portal.
"""

import os
import sys
from dotenv import load_dotenv
from azure.core.exceptions import ResourceExistsError, HttpResponseError
from azure.storage.blob import BlobServiceClient
from azure.cosmos import CosmosClient, PartitionKey, ThroughputProperties

# Nạp biến môi trường từ .env
load_dotenv()

# Lấy cấu hình Azure Blob Storage
BLOB_CONN_STR = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
BLOB_CONTAINERS = [
    os.getenv("BLOB_CONTAINER_RAW_DATA", "raw-data"),
    os.getenv("BLOB_CONTAINER_PROCESSED_DATA", "processed-data"),
    os.getenv("BLOB_CONTAINER_MODEL_ARTIFACTS", "model-artifacts"),
    os.getenv("BLOB_CONTAINER_INTERACTION_LOGS", "interaction-logs"),
]

# Lấy cấu hình Azure Cosmos DB
COSMOS_ENDPOINT = os.getenv("COSMOS_DB_ENDPOINT")
COSMOS_KEY = os.getenv("COSMOS_DB_PRIMARY_KEY")
COSMOS_DB_NAME = os.getenv("COSMOS_DB_DATABASE_NAME", "ecommerce_recommender_db")
COSMOS_THROUGHPUT = int(os.getenv("COSMOS_DATABASE_THROUGHPUT", "400"))

COSMOS_CONTAINERS_CONFIG = [
    {
        "id": os.getenv("COSMOS_CONTAINER_USER_RECS", "user_recommendations"),
        "partition_key": "/user_id",
    },
    {
        "id": os.getenv("COSMOS_CONTAINER_ITEM_RECS", "item_recommendations"),
        "partition_key": "/product_id",
    },
    {
        "id": os.getenv("COSMOS_CONTAINER_METADATA", "system_metadata"),
        "partition_key": "/id",
    },
]


def init_blob_storage():
    """Khởi tạo các Containers trong Azure Blob Storage."""
    print("\n--- [1/2] ĐANG KHỞI TẠO AZURE BLOB STORAGE CONTAINERS ---")
    if not BLOB_CONN_STR or "your_storage_account" in BLOB_CONN_STR:
        print("[-] Lỗi: Chưa cung cấp AZURE_STORAGE_CONNECTION_STRING hợp lệ trong file .env")
        return False

    try:
        blob_service_client = BlobServiceClient.from_connection_string(BLOB_CONN_STR)
        for container_name in BLOB_CONTAINERS:
            try:
                container_client = blob_service_client.create_container(container_name)
                print(f"[+] Đã tạo thành công Blob Container: '{container_name}'")
            except ResourceExistsError:
                print(f"[*] Blob Container '{container_name}' đã tồn tại từ trước (Bỏ qua).")
        return True
    except Exception as e:
        print(f"[-] Khởi tạo Blob Storage thất bại: {str(e)}")
        return False


def init_cosmos_db():
    """Khởi tạo Database và các Containers trong Azure Cosmos DB NoSQL."""
    print("\n--- [2/2] ĐANG KHỞI TẠO AZURE COSMOS DB NOSQL ---")
    if not COSMOS_ENDPOINT or not COSMOS_KEY or "your-cosmos-account" in COSMOS_ENDPOINT:
        print("[-] Lỗi: Chưa cấu hình COSMOS_DB_ENDPOINT hoặc COSMOS_DB_PRIMARY_KEY trong .env")
        return False

    try:
        cosmos_client = CosmosClient(COSMOS_ENDPOINT, credential=COSMOS_KEY)

        # 1. Tạo Database cấp phát thông lượng dùng chung (Shared Throughput)
        try:
            database = cosmos_client.create_database(
                id=COSMOS_DB_NAME,
                offer_throughput=ThroughputProperties(auto_upgrade_max_throughput=False, offer_throughput=COSMOS_THROUGHPUT)
            )
            print(f"[+] Đã tạo Database Cosmos DB: '{COSMOS_DB_NAME}' với thông lượng {COSMOS_THROUGHPUT} RU/s.")
        except ResourceExistsError:
            database = cosmos_client.get_database_client(COSMOS_DB_NAME)
            print(f"[*] Database Cosmos DB '{COSMOS_DB_NAME}' đã tồn tại từ trước.")

        # 2. Tạo từng Container với Partition Key tương ứng
        for c_config in COSMOS_CONTAINERS_CONFIG:
            container_id = c_config["id"]
            pk_path = c_config["partition_key"]
            try:
                database.create_container(
                    id=container_id,
                    partition_key=PartitionKey(path=pk_path)
                )
                print(f"[+] Đã tạo Cosmos Container: '{container_id}' (Partition Key: {pk_path})")
            except ResourceExistsError:
                print(f"[*] Cosmos Container '{container_id}' đã tồn tại từ trước (Bỏ qua).")

        return True
    except HttpResponseError as http_err:
        print(f"[-] Lỗi HTTP kết nối Cosmos DB: {http_err.message}")
        return False
    except Exception as e:
        print(f"[-] Khởi tạo Cosmos DB thất bại: {str(e)}")
        return False


if __name__ == "__main__":
    print("==================================================================")
    print("KHỞI TẠO HẠ TẦNG LƯU TRỮ VÀ DATABASE TỰ ĐỘNG BẰNG PYTHON CODE")
    print("==================================================================")
    blob_ok = init_blob_storage()
    cosmos_ok = init_cosmos_db()

    if blob_ok and cosmos_ok:
        print("\n[V] TOÀN BỘ HẠ TẦNG ĐÃ ĐƯỢC THIẾT LẬP THÀNH CÔNG, SẴN SÀNG CHO BƯỚC ETL.")
    else:
        print("\n[X] QUÁ TRÌNH KHỞI TẠO CÓ LỖI, VUI LÒNG KIỂM TRA LẠI THÔNG TIN CREDENTIALS TRONG FILE .ENV.")
        sys.exit(1)