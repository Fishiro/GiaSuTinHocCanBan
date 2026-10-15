# File: main.py
# Mô tả: Entrypoint nhận 6 tham số dòng lệnh của BTC, xuất tệp submission.csv chuẩn UTF-8.

import os
import sys
import csv
import json
import argparse
from mcp_excel_engine import ContestPipelineEngine


def parse_args():
    parser = argparse.ArgumentParser(
        description="AI2026 Bảng C - Chủ đề 2: Hỏi đáp Excel")
    parser.add_argument("--xlsx-dir", required=True,
                        help="Thư mục chứa các tệp .xlsx")
    parser.add_argument("--queries", required=True,
                        help="Đường dẫn tệp queries.json")
    parser.add_argument("--output", required=True,
                        help="Đường dẫn tệp kết quả submission.csv")
    parser.add_argument("--openrouter-key", default=None,
                        help="Khóa API OpenRouter do BTC cấp")
    parser.add_argument(
        "--openrouter-model", default="qwen/qwen3.7-flash", help="Model ID trên OpenRouter")
    parser.add_argument("--openrouter-base-url",
                        default="https://openrouter.ai/api/v1", help="Base URL OpenRouter")
    return parser.parse_args()


def main():
    args = parse_args()

    # Khởi tạo Engine ưu tiên tham số dòng lệnh của BTC, nếu không có mới lấy từ .env
    engine = ContestPipelineEngine(
        xlsx_dir=args.xlsx_dir,
        provider="openrouter" if args.openrouter_key else None,
        api_key=args.openrouter_key,
        base_url=args.openrouter_base_url,
        model=args.openrouter_model,
    )

    with open(args.queries, "r", encoding="utf-8") as f:
        queries = json.load(f)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    results = []

    for item in queries:
        q_id = str(item.get("id", "")).strip()
        file_name = str(item.get("file_name")
                        or item.get("file name") or "").strip()
        query_text = str(item.get("query", "")).strip()

        try:
            res = engine.solve_question(
                query_id=q_id,
                file_name=file_name,
                query_text=query_text,
                include_natural=False,  # Tắt sinh giải thích dài dòng khi chạy CLI để tiết kiệm token
            )
            answer = res["answer"]
            print(
                f"[OK] {q_id} -> {answer} | Tokens: {res['token_usage']['total_tokens']} "
                f"| Cost: ${res['token_usage']['cost_usd']:.6f} | Time: {res['elapsed_seconds']}s",
                file=sys.stdout,
            )
        except Exception as e:
            print(f"[ERROR] {q_id}: {e}", file=sys.stderr)
            answer = "0"

        results.append((q_id, answer))

    # Ghi tệp CSV UTF-8 với đúng 2 cột id,answer (csv.writer tự động bọc ngoặc kép khi có dấu phẩy)
    with open(args.output, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "answer"])
        writer.writerows(results)

    print(
        f"=== HOÀN TẤT {len(results)} CÂU HỎI | TỔNG CHI PHÍ: ${engine.tracker.total_cost_usd:.6f} ===",
        file=sys.stdout,
    )


if __name__ == "__main__":
    main()
