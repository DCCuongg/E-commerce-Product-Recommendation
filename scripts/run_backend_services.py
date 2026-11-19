"""
scripts/run_backend_services.py
Khởi chạy đồng thời 3 Backend Microservices (Ports 8001, 8002, 8003) và FaaS (Port 7071)
trong môi trường phát triển cục bộ.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
os.chdir(ROOT_DIR)


def cleanup_temp_files():
    """Xóa file SQLite rác nếu từng sinh ra khi chạy test lúc chưa bật Docker."""
    stray_db = ROOT_DIR / "data" / "test_backend.db"
    if stray_db.exists():
        try:
            stray_db.unlink()
            print("[Cleanup] Đã xóa file rác: data/test_backend.db")
        except OSError as exc:
            print(f"[Cleanup] Không thể xóa data/test_backend.db: {exc}")


def ensure_model_artifacts():
    """Đảm bảo models/svd_recommender.pkl và models/item_similarity.npz tồn tại trước khi serve."""
    svd_path = ROOT_DIR / "models" / "svd_recommender.pkl"
    sim_path = ROOT_DIR / "models" / "item_similarity.npz"

    if svd_path.exists() and sim_path.exists():
        print("[Models] Đã xác nhận đủ model artifacts (item_similarity.npz & svd_recommender.pkl).")
        return

    print("[Models] Thiếu model artifacts. Đang chạy sync/pipeline tạo model...")
    sync_script = ROOT_DIR / "scripts" / "sync_models_to_dev.py"
    if sync_script.exists():
        subprocess.run([sys.executable, str(sync_script)], check=False)

    if not svd_path.exists():
        subprocess.run([sys.executable, "-m", "ml_pipeline.pipeline_runner", "--dry-run"], check=False)


def main():
    cleanup_temp_files()
    ensure_model_artifacts()

    services = [
        {
            "name": "AuthService (8001)",
            "cmd": [sys.executable, "-m", "uvicorn", "services.auth_service.main:app", "--host", "0.0.0.0", "--port", "8001"],
        },
        {
            "name": "OrderService (8002)",
            "cmd": [sys.executable, "-m", "uvicorn", "services.order_service.main:app", "--host", "0.0.0.0", "--port", "8002"],
        },
        {
            "name": "RecommenderService (8003)",
            "cmd": [sys.executable, "-m", "uvicorn", "services.recommender_service.main:app", "--host", "0.0.0.0", "--port", "8003"],
        },
        {
            "name": "FaaS LogInteraction (7071)",
            "cmd": [
                sys.executable,
                "-m",
                "uvicorn",
                "azure_functions.LogInteractionFunction:create_standalone_faas_app",
                "--factory",
                "--host",
                "0.0.0.0",
                "--port",
                "7071",
            ],
        },
    ]

    processes = []
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT_DIR)

    print("\n=== KHỞI ĐỘNG HỆ THỐNG BACKEND MICROSERVICES & FAAS ===")
    for svc in services:
        print(f" -> Starting {svc['name']}...")
        proc = subprocess.Popen(svc["cmd"], cwd=str(ROOT_DIR), env=env)
        processes.append((svc["name"], proc))
        time.sleep(0.5)

    print("\nTất cả service đã khởi động. Nhấn Ctrl+C để dừng toàn bộ.\n")

    def shutdown_handler(signum, frame):
        print("\nĐang dừng toàn bộ services...")
        for name, proc in processes:
            if proc.poll() is None:
                proc.terminate()
        for name, proc in processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    while True:
        for name, proc in processes:
            ret = proc.poll()
            if ret is not None:
                print(f"[Cảnh báo] {name} đã thoát với mã lỗi {ret}.")
        time.sleep(2)


if __name__ == "__main__":
    main()