"""
scripts/run_backend_services.py
Script khởi chạy đồng thời cả 4 dịch vụ Backend phục vụ phát triển và tích hợp với Frontend:
1. Auth Service         -> http://localhost:8001 (Swagger: http://localhost:8001/docs)
2. Order/Cart Service   -> http://localhost:8002 (Swagger: http://localhost:8002/docs)
3. Recommender Service  -> http://localhost:8003 (Swagger: http://localhost:8003/docs)
4. Azure Function FaaS  -> http://localhost:7071 (Swagger: http://localhost:7071/docs)
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

SERVICES = [
    {
        "name": "Auth Service (Port 8001)",
        "cmd": [
            sys.executable,
            "-m",
            "uvicorn",
            "services.auth_service.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8001",
        ],
    },
    {
        "name": "Order/Cart Service (Port 8002)",
        "cmd": [
            sys.executable,
            "-m",
            "uvicorn",
            "services.order_service.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8002",
        ],
    },
    {
        "name": "Recommender Service (Port 8003)",
        "cmd": [
            sys.executable,
            "-m",
            "uvicorn",
            "services.recommender_service.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8003",
        ],
    },
    {
        "name": "Azure Function FaaS (Port 7071)",
        "cmd": [
            sys.executable,
            "-m",
            "azure_functions.LogInteractionFunction",
        ],
    },
]


def main():
    processes = []
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT_DIR)

    print("=" * 72)
    print("🚀 ĐANG KHỞI ĐỘNG TOÀN BỘ HỆ THỐNG BACKEND MICROSERVICES & FAAS")
    print("=" * 72)

    try:
        for svc in SERVICES:
            print(f"   [+] Starting {svc['name']}...")
            proc = subprocess.Popen(
                svc["cmd"],
                cwd=str(ROOT_DIR),
                env=env,
            )
            processes.append((svc["name"], proc))
            time.sleep(0.8)

        print("\n✅ Toàn bộ 4 dịch vụ Backend đang chạy! Nhấn Ctrl+C để dừng tất cả.\n")
        print("   • Auth Service Docs:        http://localhost:8001/docs")
        print("   • Order/Cart Service Docs:  http://localhost:8002/docs")
        print("   • Recommender Service Docs: http://localhost:8003/docs")
        print("   • FaaS Log Function Docs:   http://localhost:7071/docs")
        print("=" * 72)

        while True:
            time.sleep(2)
            for name, proc in processes:
                if proc.poll() is not None:
                    print(f"⚠️ Dịch vụ '{name}' đã dừng với mã thoát {proc.returncode}.")
                    raise KeyboardInterrupt
    except KeyboardInterrupt:
        print("\n🛑 Đang tắt toàn bộ các dịch vụ Backend...")
        for name, proc in processes:
            if proc.poll() is None:
                proc.terminate()
        for name, proc in processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("✅ Đã dừng tất cả dịch vụ an toàn.")


if __name__ == "__main__":
    main()
