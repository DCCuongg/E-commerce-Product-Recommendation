# scripts/verify_dev_env.py
import os
import urllib3
import psycopg2
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
from azure.cosmos import CosmosClient

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv(".env")

def test_postgresql():
    print("--- [1/3] Kiểm tra PostgreSQL ---")
    try:
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST"),
            port=os.getenv("POSTGRES_PORT"),
            dbname=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            sslmode="disable"
        )
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM products;")
        prod_count = cur.fetchone()[0]
        cur.execute("SELECT id, name, price, stock_quantity FROM products LIMIT 1;")
        sample = cur.fetchone()
        
        print(f"  [PASS] Kết nối thành công!")
        print(f"  [DATA] Tổng sản phẩm: {prod_count}")
        if sample:
            print(f"  [SAMPLE] SP: ID={sample[0]} | Tên={sample[1][:30]}... | Giá={sample[2]} | Kho={sample[3]}")
        else:
            print(f"  [WARN] Chưa có dòng dữ liệu nào trong bảng products.")
        conn.close()
    except Exception as e:
        print(f"  [FAIL] Lỗi PostgreSQL: {e}")

def test_azurite():
    print("\n--- [2/3] Kiểm tra Azurite (Blob Storage) ---")
    try:
        conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        blob_service = BlobServiceClient.from_connection_string(conn_str)
        containers = [c.name for c in blob_service.list_containers()]
        print(f"  [PASS] Kết nối thành công!")
        print(f"  [CONTAINERS] Danh sách: {containers}")
        
        # Kiểm tra file model trong container model-artifacts
        model_client = blob_service.get_container_client("model-artifacts")
        blobs = [b.name for b in model_client.list_blobs()]
        print(f"  [ARTIFACTS] Model files đã nạp: {blobs}")
    except Exception as e:
        print(f"  [FAIL] Lỗi Azurite: {e}")

def test_cosmos_db():
    print("\n--- [3/3] Kiểm tra Azure Cosmos DB NoSQL ---")
    try:
        client = CosmosClient(
            os.getenv("COSMOS_DB_ENDPOINT"),
            credential=os.getenv("COSMOS_DB_PRIMARY_KEY"),
            connection_verify=False
        )
        db = client.get_database_client(os.getenv("COSMOS_DB_DATABASE_NAME"))
        
        # Test 1: Đọc system_metadata
        meta_c = db.get_container_client("system_metadata")
        meta_doc = meta_c.read_item(item="popular_items", partition_key="popular_items")
        print(f"  [PASS] Kết nối thành công!")
        print(f"  [METADATA] Cold-start fallback items: {len(meta_doc.get('popular_product_ids', []))} IDs")
        
        # Test 2: Đọc 1 item recommendation
        item_c = db.get_container_client("item_recommendations")
        query = "SELECT TOP 1 * FROM c"
        recs = list(item_c.query_items(query=query, enable_cross_partition_query=True))
        if recs:
            first_rec = recs[0]
            print(f"  [RECOMMENDER] Đã đọc gợi ý mua kèm cho SP: {first_rec.get('product_id')}")
            print(f"  [RECOMMENDER] Top 1 bundle: {first_rec.get('frequently_bought_together', [])[0]}")
    except Exception as e:
        print(f"  [FAIL] Lỗi Cosmos DB: {e}")

if __name__ == "__main__":
    test_postgresql()
    test_azurite()
    test_cosmos_db()