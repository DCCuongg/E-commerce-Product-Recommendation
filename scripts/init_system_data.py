"""
scripts/init_system_data.py
Khởi tạo dữ liệu hệ thống toàn diện khi chạy Docker Compose:
1. Đăng ký/đồng bộ tài khoản mẫu qua auth-service API (đúng chuẩn mã hóa mật khẩu).
2. Sinh dữ liệu mẫu về đơn hàng, giao dịch thanh toán, đánh giá (reviews), giỏ hàng
   và clickstream logs cho chính các user của hệ thống (idempotent).
3. Dùng pre-trained models (item_similarity.npz & svd_recommender.pkl) tính Top-K
   gợi ý cá nhân hóa từ lịch sử của từng user hệ thống và nạp lên Azure Cosmos DB.
"""

import json
import math
import os
import pickle
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import scipy.sparse as sp
import urllib3
from azure.cosmos import CosmosClient, PartitionKey
from azure.storage.blob import BlobServiceClient
from huggingface_hub import hf_hub_download

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _ensure_dependencies():
    """Đảm bảo container có sẵn psycopg2 và bcrypt để thao tác PostgreSQL."""
    for pkg, mod in [("psycopg2-binary", "psycopg2"), ("bcrypt", "bcrypt")]:
        try:
            __import__(mod)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])


_ensure_dependencies()
import bcrypt  # noqa: E402
import psycopg2  # noqa: E402
from psycopg2.extras import Json  # noqa: E402


# ------------------------------------------------------------------------------
# HELPER CHUYỂN ĐỔI KIỂU DỮ LIỆU JSON AN TOÀN
# ------------------------------------------------------------------------------
def _to_json_safe(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating, float)):
        fval = float(val)
        return None if (math.isnan(fval) or math.isinf(fval)) else fval
    if isinstance(val, (np.bool_, bool)):
        return bool(val)
    if isinstance(val, np.ndarray):
        return [_to_json_safe(x) for x in val.tolist()]
    if isinstance(val, list):
        return [_to_json_safe(x) for x in val]
    if isinstance(val, dict):
        return {str(k): _to_json_safe(v) for k, v in val.items()}
    try:
        if pd.isna(val):
            return None
    except Exception:
        pass
    return val


def _normalize_product_record(row: Dict[str, Any]) -> Dict[str, Any]:
    clean = {k: _to_json_safe(v) for k, v in row.items()}
    pid = str(clean.get("product_id") or clean.get("id") or clean.get("asin") or "")
    large_urls = clean.get("large_urls")
    if isinstance(large_urls, str):
        try:
            parsed = json.loads(large_urls)
            large_urls = parsed if isinstance(parsed, list) else [large_urls]
        except Exception:
            large_urls = [large_urls] if large_urls else []
    elif not isinstance(large_urls, list):
        large_urls = []

    thumb = (
        clean.get("thumbnail_url")
        or clean.get("thumb_url")
        or clean.get("image_url")
        or (large_urls[0] if large_urls else None)
    )

    clean["product_id"] = pid
    clean["name"] = str(clean.get("name") or clean.get("title") or pid)
    clean["category"] = clean.get("category") or clean.get("main_category")
    clean["price"] = float(clean.get("price") or 0.0)
    clean["thumbnail_url"] = thumb
    clean["thumb_url"] = clean.get("thumb_url") or thumb
    clean["image_url"] = clean.get("image_url") or thumb
    clean["hi_res_url"] = clean.get("hi_res_url") or (large_urls[0] if large_urls else thumb)
    clean["large_urls"] = large_urls
    clean["stock_quantity"] = int(clean.get("stock_quantity") or 100)
    clean["rating"] = float(clean.get("rating") or clean.get("average_rating") or 4.6)
    clean["rating_count"] = int(clean.get("rating_count") or clean.get("rating_number") or 0)
    return clean


def _get_pg_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "ecommerce_shop_db"),
        user=os.getenv("POSTGRES_USER", "postgres_admin"),
        password=os.getenv("POSTGRES_PASSWORD", "YourSecurePasswordHere123!"),
        sslmode=os.getenv("POSTGRES_SSL_MODE", "disable"),
    )


# ------------------------------------------------------------------------------
# BƯỚC 1: TẠO NGƯỜI DÙNG MẪU QUA API ĐĂNG KÝ CỦA AUTH-SERVICE
# ------------------------------------------------------------------------------
SYSTEM_SAMPLE_USERS = [
    {
        "id": "U_ADMIN_01",
        "username": "admin",
        "email": "admin@ecommerce.local",
        "password": "Password123!",
        "role": "admin",
        "keywords": ["drum", "percussion", "cymbal", "stand"],
    },
    {
        "id": "U_TEST_01",
        "username": "cuongduong",
        "email": "cuong@ecommerce.local",
        "password": "Password123!",
        "role": "customer",
        "keywords": ["guitar", "string", "pedal", "amp"],
    },
    {
        "id": "U_TEST_02",
        "username": "testuser",
        "email": "test@ecommerce.local",
        "password": "Password123!",
        "role": "customer",
        "keywords": ["microphone", "audio", "cable", "mixer"],
    },
    {
        "id": "U_CUST_03",
        "username": "minhanh_music",
        "email": "minhanh@ecommerce.local",
        "password": "Password123!",
        "role": "customer",
        "keywords": ["keyboard", "piano", "midi", "sustain"],
    },
    {
        "id": "U_CUST_04",
        "username": "hoangnam_studio",
        "email": "hoangnam@ecommerce.local",
        "password": "Password123!",
        "role": "customer",
        "keywords": ["violin", "ukulele", "tuner", "capo"],
    },
]


def _register_via_auth_api(auth_url: str, user_cfg: Dict[str, Any]) -> bool:
    """Gọi endpoint đăng ký của auth-service để tạo user với đúng cơ chế mã hóa mật khẩu."""
    payload = json.dumps(
        {
            "username": user_cfg["username"],
            "email": user_cfg["email"],
            "password": user_cfg["password"],
        }
    ).encode("utf-8")

    for path in ["/api/v1/auth/register", "/auth/register", "/register"]:
        req = urllib.request.Request(
            url=f"{auth_url.rstrip('/')}{path}",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status in (200, 201):
                    return True
        except urllib.error.HTTPError as e:
            # 400/409 nghĩa là username/email đã tồn tại -> coi như hợp lệ
            if e.code in (400, 409):
                return True
        except Exception:
            continue
    return False


def ensure_system_users(conn):
    print("[1/4] Đang khởi tạo tài khoản hệ thống chuẩn xác thực...")
    auth_url = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8001")

    with conn.cursor() as cur:
        for u in SYSTEM_SAMPLE_USERS:
            registered_via_api = _register_via_auth_api(auth_url, u)
            hashed = bcrypt.hashpw(u["password"].encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

            # Kiểm tra xem user đã tồn tại theo username hoặc id chưa
            cur.execute("SELECT id FROM users WHERE username = %s OR id = %s;", (u["username"], u["id"]))
            row = cur.fetchone()
            if row:
                cur.execute(
                    """
                    UPDATE users
                    SET role = %s, is_disabled = FALSE, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s;
                    """,
                    (u["role"], row[0]),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO users (id, username, email, hashed_password, role, is_disabled)
                    VALUES (%s, %s, %s, %s, %s, FALSE)
                    ON CONFLICT (id) DO NOTHING;
                    """,
                    (u["id"], u["username"], u["email"], hashed, u["role"]),
                )
            mode = "auth-service API" if registered_via_api else "bcrypt DB sync"
            print(f"   ✓ User '{u['username']}' ({u['role']}) sẵn sàng ({mode}).")
    conn.commit()


# ------------------------------------------------------------------------------
# BƯỚC 2: TẢI MODEL ARTIFACTS & CATALOG TỪ HUGGING FACE
# ------------------------------------------------------------------------------
def download_artifacts() -> Dict[str, Optional[str]]:
    print("[2/4] Đang chuẩn bị dữ liệu sản phẩm & model artifacts...")
    dataset_repo = os.getenv("HF_DATASET_REPO", "cuongduongok/amazon-musical-instruments-clean")
    model_repo = os.getenv("HF_MODEL_REPO", "cuongduongok/amazon-musical-recommender-models")

    proc_dir = os.path.abspath("data/processed")
    model_dir = os.path.abspath("data/models")
    os.makedirs(proc_dir, exist_ok=True)
    os.makedirs(model_dir, exist_ok=True)

    paths: Dict[str, Optional[str]] = {"web_products": None, "svd_model": None, "item_sim": None}

    web_local = os.path.join(proc_dir, "web_products.parquet")
    if os.path.exists(web_local):
        paths["web_products"] = web_local
    else:
        try:
            paths["web_products"] = hf_hub_download(
                repo_id=dataset_repo, filename="web_products.parquet", repo_type="dataset", local_dir=proc_dir
            )
        except Exception as e:
            print(f"   [!] Không tải được web_products.parquet: {e}")

    for key_name, fname in [("svd_model", "svd_recommender.pkl"), ("item_sim", "item_similarity.npz")]:
        local_f = os.path.join(model_dir, fname)
        if os.path.exists(local_f):
            paths[key_name] = local_f
        else:
            try:
                paths[key_name] = hf_hub_download(
                    repo_id=model_repo, filename=fname, repo_type="model", local_dir=model_dir
                )
            except Exception as e:
                print(f"   [!] Không tải được {fname}: {e}")

    print("   ✓ Đã sẵn sàng model artifacts & catalog.")
    return paths


# ------------------------------------------------------------------------------
# BƯỚC 3: SINH LỊCH SỬ MUA BÁN, REVIEW, GIỎ HÀNG & CLICKSTREAM MẪU
# ------------------------------------------------------------------------------
def _pick_products_for_persona(
    pg_products: List[Dict[str, Any]],
    keywords: List[str],
    valid_model_ids: set,
    offset: int,
    count: int = 5,
) -> List[Dict[str, Any]]:
    """Chọn các sản phẩm thật trong PostgreSQL khớp với sở thích persona và nằm trong tập model."""
    matched = [
        p
        for p in pg_products
        if p["id"] in valid_model_ids
        and any(kw in f"{p['name']} {p.get('category') or ''}".lower() for kw in keywords)
    ]
    if len(matched) < count:
        fallback = [p for p in pg_products if p["id"] in valid_model_ids and p not in matched]
        start = (offset * count) % max(1, len(fallback))
        matched.extend(fallback[start : start + (count - len(matched))])
    return matched[:count]


def seed_sample_user_activities(conn, valid_model_ids: set):
    print("[3/4] Đang sinh lịch sử mua hàng, đánh giá (reviews) & tương tác mẫu cho user hệ thống...")
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, category, price FROM products WHERE is_active = TRUE ORDER BY id;")
        pg_products = [
            {"id": str(r[0]), "name": str(r[1]), "category": r[2], "price": float(r[3] or 25.0)}
            for r in cur.fetchall()
        ]

        if not pg_products:
            print("   [!] Bảng products đang trống -> Bỏ qua sinh lịch sử mẫu.")
            return

        # Lấy danh sách user thực tế từ bảng users
        cur.execute("SELECT id, username FROM users;")
        db_users = {str(r[1]): str(r[0]) for r in cur.fetchall()}

        now = datetime.now(timezone.utc)
        clickstream_events: List[Dict[str, Any]] = []
        created_orders = 0
        created_reviews = 0

        review_templates = [
            (5.0, "Chất lượng vượt mong đợi", "Sản phẩm hoàn thiện chắc chắn, âm thanh chuẩn, giao hàng nhanh."),
            (4.5, "Rất đáng tiền", "Dùng tập luyện và biểu diễn đều ổn định, đóng gói kỹ."),
            (5.0, "Hoạt động hoàn hảo", "Tương thích tốt với dàn thiết bị hiện tại của mình, sẽ ủng hộ tiếp."),
            (4.0, "Hài lòng", "Thiết kế đẹp, dễ sử dụng ngay cả với người mới bắt đầu."),
        ]

        for idx, u_cfg in enumerate(SYSTEM_SAMPLE_USERS):
            uid = db_users.get(u_cfg["username"], u_cfg["id"])
            picked = _pick_products_for_persona(pg_products, u_cfg["keywords"], valid_model_ids, offset=idx, count=5)
            if len(picked) < 3:
                continue

            # 3.1 Tạo 2 đơn hàng mẫu (DELIVERED & CONFIRMED) + order_items + payment_transactions
            order_specs = [
                ("DELIVERED", "ONLINE", "PAID", picked[0:2], now - timedelta(days=14 - idx)),
                ("CONFIRMED", "COD", "UNPAID", picked[2:3], now - timedelta(days=3)),
            ]

            for o_idx, (status, pay_method, pay_status, items, created_ts) in enumerate(order_specs, start=1):
                pay_code = f"SEED-{uid}-ORD{o_idx}"
                cur.execute("SELECT id FROM orders WHERE payment_code = %s;", (pay_code,))
                if cur.fetchone():
                    continue

                total_amount = round(sum(it["price"] for it in items), 2)
                paid_at = created_ts + timedelta(minutes=5) if pay_status == "PAID" else None

                cur.execute(
                    """
                    INSERT INTO orders (
                        user_id, total_amount, status, payment_method, payment_status,
                        payment_code, paid_at, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                    """,
                    (uid, total_amount, status, pay_method, pay_status, pay_code, paid_at, created_ts, created_ts),
                )
                order_id = cur.fetchone()[0]
                created_orders += 1

                for it in items:
                    cur.execute(
                        """
                        INSERT INTO order_items (order_id, product_id, quantity, unit_price)
                        VALUES (%s, %s, 1, %s);
                        """,
                        (order_id, it["id"], it["price"]),
                    )
                    # Ghi log sự kiện view -> add_to_cart -> purchase
                    for action, val, dt_offset in [
                        ("view", 1.0, timedelta(minutes=-20)),
                        ("add_to_cart", 3.0, timedelta(minutes=-10)),
                        ("purchase", 5.0, timedelta(0)),
                    ]:
                        ev_ts = (created_ts + dt_offset).isoformat()
                        clickstream_events.append(
                            {
                                "user_id": uid,
                                "item_id": it["id"],
                                "product_id": it["id"],
                                "action": action,
                                "value": val,
                                "timestamp": ev_ts,
                                "ingested_at": now.isoformat(),
                            }
                        )

                if pay_status == "PAID":
                    cur.execute(
                        """
                        INSERT INTO payment_transactions (
                            order_id, payment_code, provider, provider_tx_id, amount, status, raw_payload, created_at
                        )
                        VALUES (%s, %s, 'VIETQR_GATEWAY', %s, %s, 'SUCCESS', %s, %s)
                        ON CONFLICT (provider_tx_id) DO NOTHING;
                        """,
                        (
                            order_id,
                            pay_code,
                            f"TX-{pay_code}",
                            total_amount,
                            Json({"source": "system_seed", "payment_code": pay_code}),
                            paid_at,
                        ),
                    )

            # 3.2 Tạo đánh giá (reviews) cho các sản phẩm đã mua
            for r_idx, it in enumerate(picked[0:3]):
                cur.execute(
                    "SELECT id FROM reviews WHERE user_id = %s AND product_id = %s;",
                    (uid, it["id"]),
                )
                if cur.fetchone():
                    continue
                rating_val, title, comment = review_templates[(idx + r_idx) % len(review_templates)]
                cur.execute(
                    """
                    INSERT INTO reviews (user_id, product_id, rating, title, comment, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s);
                    """,
                    (uid, it["id"], rating_val, title, comment, now - timedelta(days=2)),
                )
                created_reviews += 1
                clickstream_events.append(
                    {
                        "user_id": uid,
                        "item_id": it["id"],
                        "product_id": it["id"],
                        "action": "rating",
                        "value": rating_val,
                        "rating": rating_val,
                        "timestamp": (now - timedelta(days=2)).isoformat(),
                        "ingested_at": now.isoformat(),
                    }
                )

            # 3.3 Thêm 1 sản phẩm đang quan tâm vào giỏ hàng (cart_items)
            if len(picked) >= 4:
                cart_prod = picked[3]
                cur.execute(
                    """
                    INSERT INTO cart_items (user_id, product_id, quantity)
                    VALUES (%s, %s, 1)
                    ON CONFLICT (user_id, product_id) DO NOTHING;
                    """,
                    (uid, cart_prod["id"]),
                )
                clickstream_events.append(
                    {
                        "user_id": uid,
                        "item_id": cart_prod["id"],
                        "product_id": cart_prod["id"],
                        "action": "add_to_cart",
                        "value": 3.0,
                        "timestamp": now.isoformat(),
                        "ingested_at": now.isoformat(),
                    }
                )

    conn.commit()
    print(f"   ✓ Đã sinh {created_orders} đơn hàng mẫu & {created_reviews} đánh giá mẫu vào PostgreSQL.")

    # 3.4 Đồng bộ clickstream logs lên Azurite Blob Storage & file local
    if clickstream_events:
        _push_clickstream_logs(clickstream_events)


def _push_clickstream_logs(events: List[Dict[str, Any]]):
    raw_dir = os.path.abspath("data/raw")
    os.makedirs(raw_dir, exist_ok=True)
    local_log = os.path.join(raw_dir, "interaction_logs.jsonl")
    lines = "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n"

    with open(local_log, "a", encoding="utf-8") as f:
        f.write(lines)

    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    container_name = os.getenv("BLOB_CONTAINER_INTERACTION_LOGS", "interaction-logs")
    if not conn_str:
        return

    try:
        blob_service = BlobServiceClient.from_connection_string(conn_str)
        container = blob_service.get_container_client(container_name)
        if not container.exists():
            container.create_container()

        now_utc = datetime.now(timezone.utc)
        blob_path = (
            f"logs/year={now_utc:%Y}/month={now_utc:%m}/day={now_utc:%d}/"
            f"interactions_{now_utc:%Y%m%d}.jsonl"
        )
        blob_client = container.get_blob_client(blob_path)
        if not blob_client.exists():
            blob_client.create_append_blob()
        blob_client.append_block(lines.encode("utf-8"))
        print(f"   ✓ Đã ghi {len(events)} sự kiện tương tác mẫu lên Azurite ('{container_name}/{blob_path}').")
    except Exception as e:
        print(f"   [!] Không ghi được clickstream lên Azurite (đã lưu local): {e}")


# ------------------------------------------------------------------------------
# BƯỚC 4: TÍNH GỢI Ý CÁ NHÂN HÓA CHO USER HỆ THỐNG & ĐẨY LÊN COSMOS DB
# ------------------------------------------------------------------------------
def _load_user_interaction_weights(conn) -> Dict[str, Dict[str, float]]:
    """Tổng hợp lịch sử tương tác của từng user trong PostgreSQL thành ma trận trọng số {user_id: {product_id: weight}}."""
    weights: Dict[str, Dict[str, float]] = {}

    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE is_disabled = FALSE;")
        for (uid,) in cur.fetchall():
            weights[str(uid)] = {}

        # 1. Lịch sử mua hàng (orders + order_items) -> trọng số 4.5
        cur.execute(
            """
            SELECT o.user_id, oi.product_id, SUM(oi.quantity)
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            WHERE o.status <> 'CANCELLED'
            GROUP BY o.user_id, oi.product_id;
            """
        )
        for uid, pid, qty in cur.fetchall():
            u, p = str(uid), str(pid)
            weights.setdefault(u, {})[p] = weights.get(u, {}).get(p, 0.0) + min(5.0, 4.0 + 0.5 * float(qty))

        # 2. Lịch sử đánh giá (reviews) -> cộng thêm rating
        cur.execute("SELECT user_id, product_id, AVG(rating) FROM reviews GROUP BY user_id, product_id;")
        for uid, pid, avg_rating in cur.fetchall():
            u, p = str(uid), str(pid)
            weights.setdefault(u, {})[p] = weights.get(u, {}).get(p, 0.0) + float(avg_rating)

        # 3. Sản phẩm trong giỏ hàng (cart_items) -> trọng số 3.0
        cur.execute("SELECT user_id, product_id, quantity FROM cart_items;")
        for uid, pid, qty in cur.fetchall():
            u, p = str(uid), str(pid)
            weights.setdefault(u, {})[p] = weights.get(u, {}).get(p, 0.0) + min(4.0, 2.5 + 0.5 * float(qty))

    return weights


def _load_models(artifact_paths: Dict[str, Optional[str]]) -> Tuple[Optional[dict], Any, List[str]]:
    svd_data = None
    if artifact_paths["svd_model"] and os.path.exists(artifact_paths["svd_model"]):
        with open(artifact_paths["svd_model"], "rb") as f:
            svd_data = pickle.load(f)

    sim_matrix = None
    sim_item_ids: List[str] = []

    if isinstance(svd_data, dict):
        item_to_idx = svd_data.get("item_to_idx") or svd_data.get("item2idx") or {}
        if not item_to_idx and svd_data.get("item_ids") is not None:
            item_to_idx = {str(it): i for i, it in enumerate(svd_data["item_ids"])}
        if item_to_idx:
            idx_to_item = {int(idx): str(pid) for pid, idx in item_to_idx.items()}
            sim_item_ids = [idx_to_item[i] for i in sorted(idx_to_item.keys())]

    if artifact_paths["item_sim"] and os.path.exists(artifact_paths["item_sim"]):
        try:
            sim_matrix = sp.load_npz(artifact_paths["item_sim"])
        except Exception:
            npz_obj = np.load(artifact_paths["item_sim"], allow_pickle=True)
            for k in ["similarity", "sim_matrix", "matrix", "arr_0"]:
                if k in npz_obj:
                    sim_matrix = npz_obj[k]
                    break
            if "item_ids" in npz_obj:
                sim_item_ids = [str(x) for x in npz_obj["item_ids"].tolist()]
            elif "product_ids" in npz_obj:
                sim_item_ids = [str(x) for x in npz_obj["product_ids"].tolist()]

    return svd_data, sim_matrix, sim_item_ids


def connect_cosmos_and_seed(conn, artifact_paths: Dict[str, Optional[str]]):
    endpoint = os.getenv("COSMOS_DB_ENDPOINT", "http://cosmos-emulator:8081/")
    key = os.getenv(
        "COSMOS_DB_PRIMARY_KEY",
        "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw==",
    )
    db_name = os.getenv("COSMOS_DB_DATABASE_NAME", "ecommerce_recommender_db")
    model_version = os.getenv("MODEL_VERSION", "v1.0-svd")
    top_k = 10

    print(f"[4/4] Đang kết nối Cosmos DB ({endpoint}) & đẩy gợi ý cho user hệ thống...")
    db = None
    for attempt in range(1, 25):
        try:
            client = CosmosClient(
                url=endpoint, credential=key, connection_verify=False, enable_endpoint_discovery=False
            )
            try:
                db = client.create_database_if_not_exists(id=db_name, offer_throughput=400)
            except Exception:
                db = client.create_database_if_not_exists(id=db_name)
            break
        except Exception:
            time.sleep(5)

    if db is None:
        raise RuntimeError("Không thể kết nối tới Cosmos DB Emulator.")

    meta_c = db.create_container_if_not_exists(
        id=os.getenv("COSMOS_CONTAINER_METADATA", "system_metadata"), partition_key=PartitionKey(path="/id")
    )
    user_c = db.create_container_if_not_exists(
        id=os.getenv("COSMOS_CONTAINER_USER_RECS", "user_recommendations"), partition_key=PartitionKey(path="/id")
    )
    item_c = db.create_container_if_not_exists(
        id=os.getenv("COSMOS_CONTAINER_ITEM_RECS", "item_recommendations"), partition_key=PartitionKey(path="/id")
    )

    # Xây dựng catalog_map từ web_products.parquet kết hợp bảng products của PostgreSQL
    catalog_map: Dict[str, Dict[str, Any]] = {}
    popular_ids: List[str] = []

    if artifact_paths["web_products"] and os.path.exists(artifact_paths["web_products"]):
        df_web = pd.read_parquet(artifact_paths["web_products"])
        for r in df_web.to_dict(orient="records"):
            norm = _normalize_product_record(r)
            if norm["product_id"]:
                catalog_map[norm["product_id"]] = norm

        sort_cols = [c for c in ["rating_count", "rating"] if c in df_web.columns]
        df_sorted = df_web.sort_values(by=sort_cols, ascending=[False] * len(sort_cols)) if sort_cols else df_web
        popular_ids = [
            _normalize_product_record(r)["product_id"]
            for r in df_sorted.head(20).to_dict(orient="records")
            if _normalize_product_record(r)["product_id"] in catalog_map
        ]

    # Đồng bộ giá & tồn kho thực tế từ bảng products trong PostgreSQL
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, category, price, image_url, hi_res_url, large_urls, thumb_url, stock_quantity FROM products WHERE is_active = TRUE;")
        for r in cur.fetchall():
            pid = str(r[0])
            base = catalog_map.get(pid, {})
            merged = _normalize_product_record(
                {
                    **base,
                    "product_id": pid,
                    "name": r[1],
                    "category": r[2],
                    "price": r[3],
                    "image_url": r[4],
                    "hi_res_url": r[5],
                    "large_urls": r[6],
                    "thumb_url": r[7],
                    "stock_quantity": r[8],
                }
            )
            catalog_map[pid] = merged
            if len(popular_ids) < top_k and pid not in popular_ids:
                popular_ids.append(pid)

    now_iso = datetime.now(timezone.utc).isoformat()
    popular_recs = []
    for idx, pid in enumerate(popular_ids[:top_k], start=1):
        if pid in catalog_map:
            doc = dict(catalog_map[pid])
            doc["score"] = round(float(doc.get("rating", 4.6)), 4)
            doc["rank"] = idx
            doc["recommendation_type"] = "popular_trending"
            popular_recs.append(doc)

    meta_c.upsert_item(
        {
            "id": "popular_items",
            "category": "Musical_Instruments",
            "popular_product_ids": popular_ids[:top_k],
            "recommendations": popular_recs,
            "model_version": model_version,
            "updated_at": now_iso,
        }
    )
    meta_c.upsert_item(
        {
            "id": "model_metadata",
            "model_version": model_version,
            "catalog_size": len(catalog_map),
            "status": "active",
            "updated_at": now_iso,
        }
    )

    svd_data, sim_matrix, sim_item_ids = _load_models(artifact_paths)
    item_id_to_idx = {pid: i for i, pid in enumerate(sim_item_ids)}

    # Chuẩn bị ma trận nhân tố sản phẩm V từ SVD để thực hiện Folding-In cho user mới của hệ thống
    V = None
    if isinstance(svd_data, dict):
        raw_v = svd_data.get("item_factors") if svd_data.get("item_factors") is not None else svd_data.get("Vt")
        if raw_v is not None and sim_item_ids:
            V_arr = np.asarray(raw_v, dtype=np.float32)
            if V_arr.shape[0] != len(sim_item_ids) and V_arr.shape[1] == len(sim_item_ids):
                V_arr = V_arr.T
            if V_arr.shape[0] == len(sim_item_ids):
                V = V_arr

    # Tính gợi ý cá nhân hóa cho TỪNG USER CỦA HỆ THỐNG dựa trên lịch sử PostgreSQL
    user_histories = _load_user_interaction_weights(conn)
    seeded_users = 0

    for uid, hist in user_histories.items():
        recs = []
        strategy = "cold_start_popular"

        if hist and sim_matrix is not None and item_id_to_idx:
            n_items = len(sim_item_ids)
            combined_scores = np.zeros(n_items, dtype=np.float32)
            user_vec = np.zeros(n_items, dtype=np.float32)

            for interacted_pid, weight in hist.items():
                i_idx = item_id_to_idx.get(interacted_pid)
                if i_idx is None or i_idx >= sim_matrix.shape[0]:
                    continue
                user_vec[i_idx] = float(weight)
                sim_row = (
                    sim_matrix[i_idx].toarray().ravel()
                    if sp.issparse(sim_matrix)
                    else np.asarray(sim_matrix[i_idx]).ravel()
                )
                combined_scores += float(weight) * sim_row

            # Kết hợp thêm điểm dự đoán SVD Folding-In (p_u = r_u @ V -> scores = p_u @ V.T)
            if V is not None and np.any(user_vec > 0):
                p_u = user_vec @ V
                svd_scores = p_u @ V.T
                if np.max(np.abs(svd_scores)) > 0:
                    svd_scores = svd_scores / np.max(np.abs(svd_scores))
                if np.max(np.abs(combined_scores)) > 0:
                    combined_scores = combined_scores / np.max(np.abs(combined_scores))
                combined_scores = 0.65 * combined_scores + 0.35 * svd_scores

            # Loại bỏ các sản phẩm user đã mua/tương tác để ưu tiên khám phá sản phẩm mới
            for interacted_pid in hist.keys():
                i_idx = item_id_to_idx.get(interacted_pid)
                if i_idx is not None:
                    combined_scores[i_idx] = -1e9

            top_indices = np.argsort(combined_scores)[::-1]
            for cand_idx in top_indices:
                cand_idx = int(cand_idx)
                score_val = float(combined_scores[cand_idx])
                if score_val <= -1e8:
                    break
                cand_pid = sim_item_ids[cand_idx]
                if cand_pid in catalog_map:
                    doc = dict(catalog_map[cand_pid])
                    doc["score"] = round(score_val, 4)
                    doc["rank"] = len(recs) + 1
                    doc["recommendation_type"] = "personalized_user_history"
                    recs.append(doc)
                    if len(recs) >= top_k:
                        break

            if recs:
                strategy = "hybrid_user_history"

        if not recs:
            recs = popular_recs
            strategy = "cold_start_popular"

        user_c.upsert_item(
            {
                "id": uid,
                "user_id": uid,
                "strategy": strategy,
                "interaction_count": len(hist),
                "model_version": model_version,
                "recommendations": recs,
                "updated_at": now_iso,
            }
        )
        seeded_users += 1
        print(f"   ✓ Đã tính & lưu gợi ý cho user '{uid}' (history={len(hist)} items, strategy={strategy}).")

    # Sinh dữ liệu Item-to-Item (Frequently Bought Together) cho catalog
    if sim_matrix is not None and sim_item_ids:
        max_seed_items = int(os.getenv("COSMOS_SEED_MAX_ITEMS", "500"))
        n_items = min(sim_matrix.shape[0], len(sim_item_ids), max_seed_items)
        seeded_items = 0
        for row_idx in range(n_items):
            src_pid = sim_item_ids[row_idx]
            if src_pid not in catalog_map:
                continue
            row_vec = (
                sim_matrix[row_idx].toarray().ravel()
                if sp.issparse(sim_matrix)
                else np.asarray(sim_matrix[row_idx]).ravel()
            )
            bundles = []
            for c_idx in np.argsort(row_vec)[::-1]:
                c_idx = int(c_idx)
                if c_idx == row_idx or c_idx >= len(sim_item_ids):
                    continue
                sim_score = float(row_vec[c_idx])
                if sim_score <= 0:
                    break
                target_pid = sim_item_ids[c_idx]
                if target_pid in catalog_map:
                    b_item = dict(catalog_map[target_pid])
                    b_item["similarity_score"] = round(sim_score, 4)
                    b_item["score"] = round(sim_score, 4)
                    b_item["bundle_type"] = "frequently_bought_together"
                    b_item["rank"] = len(bundles) + 1
                    bundles.append(b_item)
                    if len(bundles) >= 5:
                        break

            if bundles:
                item_c.upsert_item(
                    {
                        "id": src_pid,
                        "product_id": src_pid,
                        "model_version": model_version,
                        "frequently_bought_together": bundles,
                        "updated_at": now_iso,
                    }
                )
                seeded_items += 1

        print(f"   ✓ Đã nạp {seeded_items} sản phẩm mua kèm vào item_recommendations.")


if __name__ == "__main__":
    print("=== KHỞI TẠO DỮ LIỆU NGƯỜI DÙNG, LỊCH SỬ MẪU & GỢI Ý HỆ THỐNG ===")
    pg_conn = _get_pg_conn()
    try:
        ensure_system_users(pg_conn)
        files = download_artifacts()
        _, _, model_item_ids = _load_models(files)
        seed_sample_user_activities(pg_conn, set(model_item_ids))
        connect_cosmos_and_seed(pg_conn, files)
    finally:
        pg_conn.close()
    print("=== HOÀN TẤT KHỞI TẠO DỮ LIỆU HỆ THỐNG ===")