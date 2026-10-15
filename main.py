# File: main.py
# Mô tả: Entrypoint hỗ trợ ghi đè trực tiếp (Live Overwrite) sau từng câu hỏi,
#        bảo toàn dữ liệu khi Eject model giữa chừng hoặc nhấn Ctrl+C.

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
    parser.add_argument(
        "--openrouter-key", default=None, help="Khóa API OpenRouter do BTC cấp"
    )
    parser.add_argument(
        "--openrouter-model", default=None, help="Model ID trên OpenRouter"
    )
    parser.add_argument(
        "--openrouter-base-url", default=None, help="Base URL OpenRouter"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Bỏ qua các câu đã có đáp án hợp lệ (khác 0/rỗng) trong submission.csv để test tiếp",
    )
    return parser.parse_args()


def load_existing_answers(output_path: str) -> dict:
    """Đọc dữ liệu sẵn có từ submission.csv (nếu có) để không làm mất kết quả cũ khi chạy lại."""
    existing = {}
    if not os.path.exists(output_path):
        return existing
    try:
        with open(output_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                q_id = (row.get("id") or "").strip()
                ans = (row.get("answer") or "").strip()
                if q_id:
                    existing[q_id] = ans
    except Exception:
        pass
    return existing


def save_submission_live(output_path: str, ordered_ids: list, answers_map: dict):
    """
    Ghi đè trực tiếp toàn bộ bảng kết quả xuống tệp submission.csv ngay lập tức.
    Sử dụng flush() và os.fsync() để ép hệ điều hành ghi thẳng xuống ổ cứng.
    """
    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "answer"])
        for q_id in ordered_ids:
            writer.writerow([q_id, answers_map.get(q_id, "0")])
        f.flush()
        os.fsync(f.fileno())


def is_valid_saved_answer(ans: str) -> bool:
    """Kiểm tra xem đáp án đã lưu trước đó có hợp lệ để bỏ qua khi dùng --resume hay không."""
    if not ans or ans == "0":
        return False
    # Nếu đáp án cũ bị dính log suy nghĩ (VD: "* R17: ...") thì coi như chưa hợp lệ để chạy lại
    if ans.startswith("*") or "R1" in ans or "R2" in ans:
        return False
    return True


def main():
    args = parse_args()
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

    # 1. Nạp danh sách ID theo đúng thứ tự trong queries.json và khôi phục dữ liệu cũ (nếu có)
    ordered_ids = []
    seen_ids = set()
    for item in queries:
        q_id = str(item.get("id", "")).strip()
        if q_id and q_id not in seen_ids:
            ordered_ids.append(q_id)
            seen_ids.add(q_id)

    existing_answers = load_existing_answers(args.output)
    answers_map = {
        q_id: existing_answers.get(q_id, "0") for q_id in ordered_ids
    }

    # Ghi khởi tạo ngay lập tức để đảm bảo file luôn tồn tại hợp lệ trên ổ đĩa
    save_submission_live(args.output, ordered_ids, answers_map)
    completed_count = 0

    # 2. Chạy từng câu và ghi đè trực tiếp ngay sau khi có kết quả
    try:
        for item in queries:
            q_id = str(item.get("id", "")).strip()
            file_name = str(
                item.get("file_name") or item.get("file name") or ""
            ).strip()
            query_text = str(item.get("query", "")).strip()

            if not q_id:
                continue

            # Nếu bật --resume và câu này đã có kết quả tốt trong file CSV thì bỏ qua
            if args.resume and is_valid_saved_answer(answers_map.get(q_id, "0")):
                print(
                    f"[SKIP - ĐÃ CÓ DỮ LIỆU] {q_id} -> {answers_map[q_id]}",
                    file=sys.stdout,
                )
                completed_count += 1
                continue

            try:
                res = engine.solve_question(
                    query_id=q_id,
                    file_name=file_name,
                    query_text=query_text,
                    include_natural=False,
                )
                answer = (
                    str(res["answer"]).replace(
                        "\r", " ").replace("\n", " ").strip()
                )
                answers_map[q_id] = answer
                completed_count += 1

                # GHI ĐÈ TRỰC TIẾP XUỐNG FILE NGAY SAU KHI XONG CÂU HỎI NÀY
                save_submission_live(args.output, ordered_ids, answers_map)

                print(
                    f"[OK - ĐÃ GHI FILE] {q_id} -> {answer} | "
                    f"Tokens: {res['token_usage']['total_tokens']} | "
                    f"Cost: ${res['token_usage']['cost_usd']:.6f} | "
                    f"Time: {res['elapsed_seconds']}s",
                    file=sys.stdout,
                )
            except Exception as e:
                err_msg = str(e)
                print(f"[ERROR] {q_id}: {err_msg}", file=sys.stderr)
                # Vẫn lưu lại file ngay cả khi câu hiện tại lỗi
                save_submission_live(args.output, ordered_ids, answers_map)

                # Nếu người dùng vừa bấm Eject model trên LM Studio (mất kết nối/400/404/503) -> Dừng an toàn
                if engine.provider == "local" and any(
                    k in err_msg.lower()
                    for k in [
                        "connection",
                        "refused",
                        "aborted",
                        "disconnected",
                        "no models loaded",
                        "model not found",
                    ]
                ):
                    print(
                        "\n⚠️ [DỪNG AN TOÀN] Phát hiện LM Studio đã Eject model hoặc ngắt kết nối. "
                        f"Toàn bộ dữ liệu đã chạy được ghi đè an toàn vào '{args.output}'.",
                        file=sys.stdout,
                    )
                    break

    except KeyboardInterrupt:
        save_submission_live(args.output, ordered_ids, answers_map)
        print(
            f"\n⏹️ [TẠM DỪNG BỞI NGƯỜI DÙNG] Đã lưu trực tiếp toàn bộ tiến độ hiện tại vào '{args.output}'.",
            file=sys.stdout,
        )

    total_tokens = (
        engine.tracker.total_prompt_tokens + engine.tracker.total_completion_tokens
    )
    print(
        f"=== ĐÃ XỬ LÝ {completed_count}/{len(ordered_ids)} CÂU HỎI | "
        f"TỔNG TOKEN: {total_tokens} | TỔNG CHI PHÍ: ${engine.tracker.total_cost_usd:.6f} ===",
        file=sys.stdout,
    )


if __name__ == "__main__":
    main()
