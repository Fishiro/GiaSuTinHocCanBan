# File: main.py
# Mô tả: Entrypoint chuẩn cho hệ thống chấm thi AI2026 Bảng C (Hỗ trợ Docker CLI, OpenRouter & Local LM Studio).

import os
import sys
import csv
import json
import argparse
from mcp_excel_engine import ContestPipelineEngine


def parse_args():
    parser = argparse.ArgumentParser(
        description="AI2026 Bảng C - Chủ đề 2: Hỏi đáp trên bảng tính Excel"
    )
    # Hỗ trợ cả khi chạy tự động từ Docker lẫn chạy test nhanh trên máy
    parser.add_argument(
        "--xlsx-dir",
        default=os.getenv("CONTEST_XLSX_DIR", "./test_xlsx"),
        help="Thư mục chứa các tệp .xlsx",
    )
    parser.add_argument(
        "--queries",
        default=os.getenv("CONTEST_QUERIES_FILE", "./queries.json"),
        help="Đường dẫn tệp queries.json",
    )
    parser.add_argument(
        "--output",
        default=os.getenv("CONTEST_OUTPUT_CSV", "./submission.csv"),
        help="Đường dẫn tệp kết quả submission.csv",
    )
    # Đặt default=None để không ghi đè cấu hình Local (.env) khi không truyền từ dòng lệnh
    parser.add_argument(
        "--openrouter-key", default=None, help="Khóa API OpenRouter do BTC cấp"
    )
    parser.add_argument(
        "--openrouter-model", default=None, help="Model ID trên OpenRouter (qwen/qwen3.7-flash)"
    )
    parser.add_argument(
        "--openrouter-base-url", default=None, help="Base URL OpenRouter"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Nếu BTC truyền --openrouter-key qua CLI -> Bắt buộc dùng chế độ openrouter
    cli_provider = "openrouter" if args.openrouter_key else None

    engine = ContestPipelineEngine(
        xlsx_dir=args.xlsx_dir,
        provider=cli_provider,
        api_key=args.openrouter_key,
        base_url=args.openrouter_base_url,
        model=args.openrouter_model,
    )

    print(
        f"[INIT] Provider: {engine.provider.upper()} | Model: {engine.model} | "
        f"Base URL: {engine.base_url} | XLSX Dir: {args.xlsx_dir}",
        file=sys.stdout,
    )

    if not os.path.exists(args.queries):
        print(
            f"[FATAL] Không tìm thấy tệp câu hỏi: {args.queries}", file=sys.stderr)
        sys.exit(1)

    with open(args.queries, "r", encoding="utf-8") as f:
        queries = json.load(f)

    out_dir = os.path.dirname(os.path.abspath(args.output))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    results = []
    seen_ids = set()

    for item in queries:
        q_id = str(item.get("id", "")).strip()
        # Hỗ trợ cả khóa "file_name" (trong bộ dữ liệu) và "file name" (trong đề PDF)
        file_name = str(
            item.get("file_name") or item.get("file name") or ""
        ).strip()
        query_text = str(item.get("query", "")).strip()

        if not q_id or q_id in seen_ids:
            continue
        seen_ids.add(q_id)

        try:
            res = engine.solve_question(
                query_id=q_id,
                file_name=file_name,
                query_text=query_text,
                include_natural=False,  # Tắt sinh câu giải thích dài dòng khi chạy CLI để tiết kiệm token
            )
            answer = str(res["answer"]).replace(
                "\r", " ").replace("\n", " ").strip()
            print(
                f"[OK] {q_id} -> {answer} | Tokens: {res['token_usage']['total_tokens']} "
                f"| Cost: ${res['token_usage']['cost_usd']:.6f} | Time: {res['elapsed_seconds']}s",
                file=sys.stdout,
            )
        except Exception as e:
            print(f"[ERROR] {q_id}: {e}", file=sys.stderr)
            answer = "0"

        results.append((q_id, answer))

    # Xuất tệp CSV UTF-8 chuẩn với đúng 2 cột id,answer
    with open(args.output, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "answer"])
        writer.writerows(results)

    total_tokens = (
        engine.tracker.total_prompt_tokens + engine.tracker.total_completion_tokens
    )
    print(
        f"=== HOÀN TẤT {len(results)}/{len(queries)} CÂU HỎI | "
        f"TỔNG TOKEN: {total_tokens} | TỔNG CHI PHÍ: ${engine.tracker.total_cost_usd:.6f} ===",
        file=sys.stdout,
    )


if __name__ == "__main__":
    main()
