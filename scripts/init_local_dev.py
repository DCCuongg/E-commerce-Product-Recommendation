import os
import sys
import json
import urllib3
import time
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv
from huggingface_hub import hf_hub_download
from azure.storage.blob import BlobServiceClient
from azure.cosmos import CosmosClient, PartitionKey

# Tắt cảnh báo SSL do kết nối với Cosmos DB Emulator cục bộ
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv(".env")

# ------------------------------------------------------------------------------
# 1. TẢI DATASET TỪ HUGGING FACE HUB
# ------------------------------------------------------------------------------
def fetch_data_from_huggingface():
    repo_id = os.getenv("HF_DATASET_REPO", "cuongduongok/amazon-musical-instruments-clean")
    files_to_download = [
        "training_interactions.parquet",
        "training_products.parquet",
        "web_products.parquet"
    ]
    target_dir = os.path.abspath("data/processed")
    os.makedirs(target_dir, exist_ok=True)

    print(f"\n[1/4] Đang đồng bộ dữ liệu từ HF ({repo_id})...")
    downloaded_paths = {}

    for file_name in files_to_download:
        dest_file = os.path.join(target_dir, file_name)
        if os.path.exists(dest_file):
            print(f"   ✓ File đã tồn tại cục bộ: {file_name}")
            downloaded_paths[file_name] = dest_file
            continue

        try:
            downloaded_path = hf_hub_download(
                repo_id=repo_id,
                filename=file_name,
                repo_type="dataset",
                local_dir=target_dir
            )
            downloaded_paths[file_name] = downloaded_path
            print(f"   ✓ Đã tải thành công: {file_name}")
        except Exception as e:
            print(f"   [-] Không thể tải {file_name}: {e}")

    return downloaded_paths

# ------------------------------------------------------------------------------
# 2. KHỞI TẠO AZURE BLOB STORAGE (AZURITE)
# ------------------------------------------------------------------------------
def init_azurite_storage(downloaded_files):
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    print("\n[2/4] Đang khởi tạo Azure Blob Storage Emulator (Azurite)...")
    
    try:
        blob_service = BlobServiceClient.from_connection_string(conn_str)
        containers = [
            os.getenv("BLOB_CONTAINER_RAW_DATA", "raw-data"),
            os.getenv("BLOB_CONTAINER_PROCESSED_DATA", "processed-data"),
            os.getenv("BLOB_CONTAINER_MODEL_ARTIFACTS", "model-artifacts"),
            os.getenv("BLOB_CONTAINER_INTERACTION_LOGS", "interaction-logs"),
        ]

        for container in containers:
            try:
                blob_service.create_container(container)
                print(f"   ✓ Đã tạo container: '{container}'")
            except Exception:
                print(f"   ✓ Container '{container}' đã sẵn sàng.")

        # Upload các file Parquet tải từ HF vào container processed-data
        proc_container = blob_service.get_container_client(os.getenv("BLOB_CONTAINER_PROCESSED_DATA", "processed-data"))
        for fname, fpath in downloaded_files.items():
            if os.path.exists(fpath):
                with open(fpath, "rb") as f_data:
                    proc_container.upload_blob(name=fname, data=f_data, overwrite=True)
                print(f"   -> Đã đồng bộ '{fname}' lên container 'processed-data'")

    except Exception as e:
        print(f"[-] Lỗi kết nối Azurite: {e}")

# ------------------------------------------------------------------------------
# 3. KHỞI TẠO AZURE COSMOS DB NOSQL EMULATOR
# ------------------------------------------------------------------------------
def init_cosmos_db(web_products_path):
    endpoint = os.getenv("COSMOS_DB_ENDPOINT", "http://localhost:8081/")
    key = os.getenv("COSMOS_DB_PRIMARY_KEY")
    db_name = os.getenv("COSMOS_DB_DATABASE_NAME", "ecommerce_recommender_db")

    print("\n[3/4] Đang kết nối Azure Cosmos DB Emulator (chờ emulator sẵn sàng)...")
    cosmos_client = None
    
    # Retry tối đa 12 lần (mỗi lần cách 5s = 60s) để đợi emulator boot xong
    for attempt in range(1, 13):
        try:
            cosmos_client = CosmosClient(endpoint, credential=key, connection_verify=False)
            # Thử tạo/lấy database để kiểm tra kết nối thực tế
            db = cosmos_client.create_database_if_not_exists(
                id=db_name,
                offer_throughput=int(os.getenv("COSMOS_DATABASE_THROUGHPUT", 400))
            )
            print(f"   ✓ Đã kết nối Cosmos DB thành công (lần thử {attempt})!")
            break
        except Exception as e:
            print(f"   ⏳ Cosmos emulator đang khởi động... thử lại sau 5s ({attempt}/12)")
            time.sleep(5)
    else:
        print("[-] Không thể kết nối tới Cosmos DB Emulator sau 60s.")
        return

    # Tạo 3 container
    try:
        meta_c = db.create_container_if_not_exists(
            id=os.getenv("COSMOS_CONTAINER_METADATA", "system_metadata"),
            partition_key=PartitionKey(path="/id")
        )
        db.create_container_if_not_exists(
            id=os.getenv("COSMOS_CONTAINER_USER_RECS", "user_recommendations"),
            partition_key=PartitionKey(path="/id")
        )
        db.create_container_if_not_exists(
            id=os.getenv("COSMOS_CONTAINER_ITEM_RECS", "item_recommendations"),
            partition_key=PartitionKey(path="/id")
        )
        print("   ✓ Đã tạo thành công 3 containers: system_metadata, user_recommendations, item_recommendations")

        # Nạp dữ liệu Cold-Start
        popular_items = []
        if web_products_path and os.path.exists(web_products_path):
            df_web = pd.read_parquet(web_products_path)
            popular_items = df_web.sort_values(
                by=["rating_count", "rating"], ascending=[False, False]
            ).head(10)["product_id"].tolist()

        metadata_doc = {
            "id": "popular_items",
            "category": "Musical_Instruments",
            "popular_product_ids": popular_items,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        meta_c.upsert_item(metadata_doc)
        print("   ✓ Đã nạp metadata Cold-Start vào system_metadata.")
    except Exception as e:
        print(f"[-] Lỗi tạo container/nạp dữ liệu Cosmos: {e}")

# ------------------------------------------------------------------------------
# 4. KIỂM TRA POSTGRESQL & LOCAL SEED
# ------------------------------------------------------------------------------
def verify_postgres_seed():
    print("\n[4/4] Kiểm tra PostgreSQL & Dữ liệu Seed từ Local...")
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            dbname=os.getenv("POSTGRES_DB", "ecommerce_shop_db"),
            user=os.getenv("POSTGRES_USER", "postgres_admin"),
            password=os.getenv("POSTGRES_PASSWORD", "YourSecurePasswordHere123!"),
            sslmode=os.getenv("POSTGRES_SSL_MODE", "disable")
        )
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM products;")
        count_products = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users;")
        count_users = cursor.fetchone()[0]
        print(f"   ✓ Kết nối PostgreSQL thành công!")
        print(f"   ✓ Bảng 'products': Đã nạp {count_products} sản phẩm từ seed_products.sql")
        print(f"   ✓ Bảng 'users': Đã nạp {count_users} người dùng mẫu.")
        conn.close()
    except Exception as e:
        print(f"   [-] Kiểm tra PostgreSQL: {e}")

# ------------------------------------------------------------------------------
# 5. TỰ ĐỘNG THỰC THI SQL VÀO POSTGRESQL TỪ LOCAL
# ------------------------------------------------------------------------------
def verify_and_seed_postgres():
    print("\n[4/4] Khởi tạo bảng & Nạp dữ liệu vào PostgreSQL...")
    import psycopg2

    try:
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            dbname=os.getenv("POSTGRES_DB", "ecommerce_shop_db"),
            user=os.getenv("POSTGRES_USER", "postgres_admin"),
            password=os.getenv("POSTGRES_PASSWORD", "YourSecurePasswordHere123!"),
            sslmode="disable"
        )
        conn.autocommit = True
        cursor = conn.cursor()

        # Danh sách các file SQL cần chạy theo đúng thứ tự phụ thuộc
        sql_files = [
            "scripts/sql/01_init_auth_db.sql",
            "scripts/sql/02_init_order_db.sql",
            "scripts/sql/03_seed_auth.sql",
            "scripts/sql/seed_products.sql"
        ]

        for rel_path in sql_files:
            file_path = os.path.abspath(rel_path)
            # Fallback kiểm tra nếu file seed nằm ở thư mục data/processed
            if not os.path.exists(file_path) and "seed_products" in rel_path:
                file_path = os.path.abspath("data/processed/seed_products.sql")

            if os.path.exists(file_path):
                print(f"   ⏳ Đang thực thi {os.path.basename(file_path)}...")
                with open(file_path, "r", encoding="utf-8") as f:
                    sql_content = f.read()
                    cursor.execute(sql_content)
                print(f"   ✓ Đã thực thi xong: {os.path.basename(file_path)}")
            else:
                print(f"   ⚠️ Không tìm thấy file: {file_path}")

        # Kiểm tra lại số lượng bản ghi thực tế
        cursor.execute("SELECT COUNT(*) FROM users;")
        count_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM products;")
        count_products = cursor.fetchone()[0]

        print(f"\n   ✓ Kết nối PostgreSQL thành công!")
        print(f"   ✓ Bảng 'users': Đã có {count_users} người dùng.")
        print(f"   ✓ Bảng 'products': Đã nạp thành công {count_products} sản phẩm!")

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"   [-] Lỗi thực thi SQL vào PostgreSQL: {e}")

if __name__ == "__main__":
    downloaded_files = fetch_data_from_huggingface()
    init_azurite_storage(downloaded_files)
    init_cosmos_db(downloaded_files.get("web_products.parquet"))
    verify_and_seed_postgres() # Đổi tên hàm tại đây
    verify_postgres_seed()
    print("\n🚀 HOÀN TẤT THIẾT LẬP MÔI TRƯỜNG DEV CỤC BỘ!")