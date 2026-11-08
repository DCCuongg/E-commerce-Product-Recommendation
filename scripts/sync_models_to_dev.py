import os
import urllib3
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv
from huggingface_hub import hf_hub_download
from azure.storage.blob import BlobServiceClient
from azure.cosmos import CosmosClient, PartitionKey

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv(".env")

# ------------------------------------------------------------------------------
# 1. TẢI MODEL ARTIFACTS TỪ HUGGING FACE
# ------------------------------------------------------------------------------
def fetch_models_from_hf():
    model_repo = os.getenv("HF_MODEL_REPO", "cuongduongok/amazon-musical-recommender-models")
    target_dir = os.path.abspath("models")
    os.makedirs(target_dir, exist_ok=True)
    
    model_files = ["item_similarity.npz", "svd_recommender.pkl"]
    downloaded_models = {}

    print(f"\n[1/3] Đang tải Model Artifacts từ HF ({model_repo})...")
    for fname in model_files:
        dest_file = os.path.join(target_dir, fname)
        if os.path.exists(dest_file):
            print(f"   ✓ Đã có sẵn cục bộ: {fname}")
            downloaded_models[fname] = dest_file
            continue
        try:
            path = hf_hub_download(
                repo_id=model_repo,
                filename=fname,
                repo_type="model",
                local_dir=target_dir
            )
            downloaded_models[fname] = path
            print(f"   ✓ Tải thành công: {fname}")
        except Exception as e:
            print(f"   [-] Không thể tải {fname}: {e}")

    return downloaded_models

# ------------------------------------------------------------------------------
# 2. ĐẨY MODEL LÊN AZURE BLOB (AZURITE - CONTAINER model-artifacts)
# ------------------------------------------------------------------------------
def upload_models_to_azurite(downloaded_models):
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    container_name = os.getenv("BLOB_CONTAINER_MODEL_ARTIFACTS", "model-artifacts")

    print(f"\n[2/3] Đang đẩy Model lên Azurite (container: {container_name})...")
    try:
        blob_service = BlobServiceClient.from_connection_string(conn_str)
        container_client = blob_service.get_container_client(container_name)
        try:
            container_client.create_container()
        except Exception:
            pass

        for fname, fpath in downloaded_models.items():
            if os.path.exists(fpath):
                with open(fpath, "rb") as b_data:
                    container_client.upload_blob(name=fname, data=b_data, overwrite=True)
                print(f"   ✓ Đã đẩy '{fname}' vào container '{container_name}'")
    except Exception as e:
        print(f"[-] Lỗi đẩy Model vào Azurite: {e}")

# ------------------------------------------------------------------------------
# 3. TIỀN TÍNH TOÁN ITEM-TO-ITEM BUNDLES VÀ NẠP VÀO COSMOS DB
# ------------------------------------------------------------------------------
def sync_item_recommendations_to_cosmos():
    sim_path = os.path.join("models", "item_similarity.npz")
    prod_path = os.path.join("data", "processed", "web_products.parquet")

    if not os.path.exists(sim_path) or not os.path.exists(prod_path):
        print("⚠️ Thiếu file item_similarity.npz hoặc web_products.parquet để tạo Item recs.")
        return

    print("\n[3/3] Đang tính toán Bundles Item-to-Item và nạp vào Cosmos DB...")
    sim_data = np.load(sim_path)
    sim_matrix = sim_data["similarity"]
    df_web = pd.read_parquet(prod_path)
    item_list = df_web["product_id"].tolist()

    endpoint = os.getenv("COSMOS_DB_ENDPOINT", "https://localhost:8081/")
    key = os.getenv("COSMOS_DB_PRIMARY_KEY")
    db_name = os.getenv("COSMOS_DB_DATABASE_NAME", "ecommerce_recommender_db")

    try:
        cosmos_client = CosmosClient(endpoint, credential=key, connection_verify=False)
        db = cosmos_client.get_database_client(db_name)
        item_container = db.get_container_client(os.getenv("COSMOS_CONTAINER_ITEM_RECS", "item_recommendations"))

        current_time = datetime.now(timezone.utc).isoformat()
        n_items = min(len(item_list), sim_matrix.shape[0])

        for i in range(n_items):
            p_id = str(item_list[i])
            scores = sim_matrix[i].copy()
            scores[i] = -1.0  # Không gợi ý chính nó
            top_5_idx = np.argsort(scores)[::-1][:5]

            bundles = []
            for idx in top_5_idx:
                if idx < len(item_list):
                    score_val = float(scores[idx])
                    bundles.append({
                        "product_id": str(item_list[idx]),
                        "similarity_score": round(score_val, 3),
                        "bundle_type": "co-purchase" if score_val > 0.6 else "content_match"
                    })

            doc = {
                "id": p_id,
                "product_id": p_id,
                "frequently_bought_together": bundles,
                "updated_at": current_time
            }
            item_container.upsert_item(doc)

        print(f"   ✓ Đã nạp thành công {n_items} sản phẩm kèm danh sách 'Thường mua cùng' vào Cosmos DB!")
    except Exception as e:
        print(f"[-] Lỗi nạp item_recommendations: {e}")

if __name__ == "__main__":
    downloaded_models = fetch_models_from_hf()
    upload_models_to_azurite(downloaded_models)
    sync_item_recommendations_to_cosmos()