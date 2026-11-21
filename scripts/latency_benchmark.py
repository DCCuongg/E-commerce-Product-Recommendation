"""
scripts/latency_benchmark.py
Kịch bản đo kiểm hiệu năng và độ trễ hệ thống (Rubric Tiêu chí 3.3 & 5.1):
1. Network Latency: Bắn 100 requests đồng thời tới API (Southeast Asia vs East US / Local vs Cloud)
   để tính toán P50, P90, P99, Mean, Min, Max Latency và RPS.
2. Storage Latency: Đo tốc độ đọc O(1) trên Azure Cosmos DB và ghi/đọc trên Azure Blob Storage.
3. Xuất báo cáo JSON và biểu đồ PNG tự động vào thư mục exports/.
"""

import argparse
import asyncio
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
import httpx
import numpy as np
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=ROOT_DIR / ".env")
EXPORTS_DIR = ROOT_DIR / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


def compute_percentiles(latencies_ms: list[float]) -> dict:
    if not latencies_ms:
        return {"count": 0, "min_ms": 0, "mean_ms": 0, "p50_ms": 0, "p90_ms": 0, "p99_ms": 0, "max_ms": 0}
    arr = np.array(latencies_ms, dtype=np.float64)
    return {
        "count": len(latencies_ms),
        "min_ms": round(float(np.min(arr)), 2),
        "mean_ms": round(float(np.mean(arr)), 2),
        "p50_ms": round(float(np.percentile(arr, 50)), 2),
        "p90_ms": round(float(np.percentile(arr, 90)), 2),
        "p99_ms": round(float(np.percentile(arr, 99)), 2),
        "max_ms": round(float(np.max(arr)), 2),
    }


async def benchmark_http_endpoint(
    label: str,
    url: str,
    num_requests: int = 100,
    concurrency: int = 10,
) -> dict:
    """Gửi N requests bất đồng bộ tới endpoint và đo độ trễ phản hồi."""
    semaphore = asyncio.Semaphore(concurrency)
    latencies_ms: list[float] = []
    status_codes: dict[int, int] = {}
    errors: int = 0

    async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
        # Warm-up 3 requests để thiết lập TCP/TLS Connection Pool
        for _ in range(3):
            try:
                await client.get(url)
            except Exception:
                pass

        async def single_call():
            nonlocal errors
            async with semaphore:
                t0 = time.perf_counter()
                try:
                    resp = await client.get(url)
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    latencies_ms.append(elapsed_ms)
                    status_codes[resp.status_code] = status_codes.get(resp.status_code, 0) + 1
                except Exception:
                    errors += 1

        t_start = time.perf_counter()
        await asyncio.gather(*(single_call() for _ in range(num_requests)))
        total_wall_sec = max(time.perf_counter() - t_start, 1e-6)

    stats = compute_percentiles(latencies_ms)
    stats.update({
        "label": label,
        "url": url,
        "total_requests": num_requests,
        "concurrency": concurrency,
        "errors": errors,
        "status_codes": status_codes,
        "rps": round(len(latencies_ms) / total_wall_sec, 2),
    })
    return stats


def benchmark_storage_layers(iterations: int = 30) -> dict:
    """Đo độ trễ truy xuất trực tiếp tầng lưu trữ Cosmos DB và Azure Blob Storage."""
    storage_results = {}

    # 1. Cosmos DB Read Latency
    cosmos_endpoint = os.getenv("COSMOS_DB_ENDPOINT", "")
    cosmos_key = os.getenv("COSMOS_DB_PRIMARY_KEY", "")
    if cosmos_endpoint and cosmos_key and "<COSMOS" not in cosmos_key:
        try:
            from azure.cosmos import CosmosClient

            client = CosmosClient(cosmos_endpoint, credential=cosmos_key, connection_verify=False)
            db = client.get_database_client(os.getenv("COSMOS_DB_DATABASE_NAME", "ecommerce_recommender_db"))
            container = db.get_container_client(os.getenv("COSMOS_CONTAINER_METADATA", "system_metadata"))

            cosmos_latencies = []
            for _ in range(iterations):
                t0 = time.perf_counter()
                container.read_item(item="popular_items", partition_key="popular_items")
                cosmos_latencies.append((time.perf_counter() - t0) * 1000.0)
            storage_results["cosmos_db_point_read"] = compute_percentiles(cosmos_latencies)
        except Exception as exc:
            storage_results["cosmos_db_point_read"] = {"error": str(exc)}

    # 2. Azure Blob Storage Write/Read Latency
    blob_conn = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    if blob_conn and "<AZURITE" not in blob_conn:
        try:
            from azure.storage.blob import BlobServiceClient

            blob_service = BlobServiceClient.from_connection_string(blob_conn)
            container = blob_service.get_container_client(
                os.getenv("BLOB_CONTAINER_INTERACTION_LOGS", "interaction-logs")
            )
            sample_payload = json.dumps({"user_id": "BENCH_USER", "product_id": "B001", "action": "click"}).encode("utf-8")

            write_latencies = []
            read_latencies = []
            for i in range(iterations):
                blob_client = container.get_blob_client(f"benchmark/probe_{i % 5}.jsonl")
                t0 = time.perf_counter()
                blob_client.upload_blob(sample_payload, overwrite=True)
                write_latencies.append((time.perf_counter() - t0) * 1000.0)

                t1 = time.perf_counter()
                blob_client.download_blob().readall()
                read_latencies.append((time.perf_counter() - t1) * 1000.0)

            storage_results["blob_storage_write"] = compute_percentiles(write_latencies)
            storage_results["blob_storage_read"] = compute_percentiles(read_latencies)
        except Exception as exc:
            storage_results["blob_storage"] = {"error": str(exc)}

    return storage_results


def export_chart(network_results: list[dict], output_png: Path):
    """Vẽ biểu đồ cột P50, P90, P99 phục vụ chèn vào Báo cáo Word & Slide."""
    try:
        import matplotlib.pyplot as plt

        labels = [r["label"] for r in network_results]
        p50 = [r["p50_ms"] for r in network_results]
        p90 = [r["p90_ms"] for r in network_results]
        p99 = [r["p99_ms"] for r in network_results]

        x = np.arange(len(labels))
        width = 0.25

        fig, ax = plt.subplots(figsize=(9, 5))
        rects1 = ax.bar(x - width, p50, width, label="P50 (Median)", color="#2563eb")
        rects2 = ax.bar(x, p90, width, label="P90", color="#f59e0b")
        rects3 = ax.bar(x + width, p99, width, label="P99 (Tail)", color="#dc2626")

        ax.set_ylabel("Latency (ms)")
        ax.set_title("So sánh độ trễ phản hồi API (P50 / P90 / P99 - 100 Requests)")
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.legend()
        ax.grid(axis="y", linestyle="--", alpha=0.5)

        for rects in (rects1, rects2, rects3):
            for rect in rects:
                h = rect.get_height()
                ax.annotate(
                    f"{h:.1f}",
                    xy=(rect.get_x() + rect.get_width() / 2, h),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )

        plt.tight_layout()
        plt.savefig(output_png, dpi=180)
        plt.close(fig)
        print(f"[Chart] Đã xuất biểu đồ độ trễ tại: {output_png}")
    except ImportError:
        print("[Chart] Bỏ qua vẽ biểu đồ (chưa cài đặt matplotlib).")


async def main():
    parser = argparse.ArgumentParser(description="Benchmark Latency giữa các Region & Storage")
    parser.add_argument(
        "--sea-url",
        type=str,
        default="http://localhost:8003/api/v1/recommendations/popular/trending",
        help="URL endpoint khu vực Southeast Asia (hoặc Local)",
    )
    parser.add_argument(
        "--eastus-url",
        type=str,
        default="",
        help="URL endpoint khu vực East US (nếu triển khai đa vùng để đối chiếu)",
    )
    parser.add_argument("--requests", type=int, default=100, help="Tổng số request mỗi kịch bản")
    parser.add_argument("--concurrency", type=int, default=10, help="Số luồng đồng thời")
    args = parser.parse_args()

    print(f"=== BẮT ĐẦU ĐO ĐỘ TRỄ HỆ THỐNG ({args.requests} REQUESTS / KỊCH BẢN) ===\n")

    targets = [("Southeast Asia (Primary)", args.sea_url)]
    if args.eastus_url:
        targets.append(("East US (Cross-Region)", args.eastus_url))

    network_results = []
    for label, url in targets:
        print(f" -> Đang đo Network Latency [{label}]: {url}")
        res = await benchmark_http_endpoint(label, url, num_requests=args.requests, concurrency=args.concurrency)
        network_results.append(res)
        print(
            f"    P50={res['p50_ms']}ms | P90={res['p90_ms']}ms | P99={res['p99_ms']}ms | "
            f"Mean={res['mean_ms']}ms | RPS={res['rps']}"
        )

    print("\n -> Đang đo Storage Latency (Cosmos DB & Blob Storage)...")
    storage_results = benchmark_storage_layers(iterations=30)
    for k, v in storage_results.items():
        if "p50_ms" in v:
            print(f"    {k}: P50={v['p50_ms']}ms | P90={v['p90_ms']}ms | P99={v['p99_ms']}ms")
        else:
            print(f"    {k}: {v}")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "network_latency": network_results,
        "storage_latency": storage_results,
    }

    out_json = EXPORTS_DIR / "latency_benchmark_results.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n[Report] Đã lưu chi tiết số liệu tại: {out_json}")

    export_chart(network_results, EXPORTS_DIR / "latency_benchmark_chart.png")


if __name__ == "__main__":
    asyncio.run(main())