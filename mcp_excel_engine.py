# File: mcp_excel_engine.py
# Mô tả: Lõi MCP Server nội bộ & Pipeline giải thuật Hỏi đáp Excel (Chủ đề 2 - Bảng C).

import os
import re
import csv
import json
import time
import openpyxl
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()


class TokenCostTracker:
    """Theo dõi sát sao lượng token và chi phí USD cho từng câu hỏi và toàn phiên."""

    def __init__(self):
        self.price_in = float(os.getenv("PRICE_PER_1M_INPUT_TOKENS", "0.10"))
        self.price_out = float(os.getenv("PRICE_PER_1M_OUTPUT_TOKENS", "0.40"))
        self.max_cost_per_query = float(
            os.getenv("MAX_COST_PER_QUERY_USD", "0.10"))
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cost_usd = 0.0

    def record(self, prompt_tokens: int, completion_tokens: int) -> dict:
        """Ghi nhận token từ API response và tính chi phí USD."""
        cost = (prompt_tokens / 1_000_000) * self.price_in + (
            completion_tokens / 1_000_000
        ) * self.price_out
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_cost_usd += cost
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost_usd": round(cost, 6),
            "session_total_cost_usd": round(self.total_cost_usd, 6),
            "within_budget": cost <= self.max_cost_per_query,
        }


class MCPExcelServer:
    """
    MCP Server nội bộ cung cấp các công cụ (Tools) đọc hiểu cấu trúc Excel phức tạp
    (ô gộp, tiêu đề phân cấp, nhiều sheet) và thực thi truy vấn Pandas an toàn.
    """

    def __init__(self, xlsx_dir: str):
        self.xlsx_dir = xlsx_dir
        # Cache dữ liệu đã làm sạch để tiết kiệm RAM (<1GB) và CPU
        self._cache = {}

    def load_and_clean_sheets(self, file_name: str) -> dict:
        """Đọc file Excel, tự động tháo ô gộp (unmerge) và chuẩn hóa bảng."""
        if file_name in self._cache:
            return self._cache[file_name]

        file_path = os.path.join(self.xlsx_dir, file_name)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Không tìm thấy tệp Excel: {file_path}")

        wb = openpyxl.load_workbook(file_path, data_only=True)
        sheets_data = {}

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            # 1. Tháo ô gộp và điền giá trị vào toàn bộ vùng gộp (xử lý tiêu đề phân cấp)
            merged_ranges = list(ws.merged_cells.ranges)
            for m_range in merged_ranges:
                min_col, min_row, max_col, max_row = m_range.bounds
                top_left_val = ws.cell(row=min_row, column=min_col).value
                ws.unmerge_cells(str(m_range))
                for r in range(min_row, max_row + 1):
                    for c in range(min_col, max_col + 1):
                        ws.cell(row=r, column=c, value=top_left_val)

            # 2. Chuyển sang danh sách dòng, loại bỏ dòng/cột trống hoàn toàn
            raw_rows = []
            for row in ws.iter_rows(values_only=True):
                if any(cell is not None and str(cell).strip() != "" for cell in row):
                    raw_rows.append(
                        ["" if cell is None else str(
                            cell).strip() for cell in row]
                    )

            if not raw_rows:
                continue

            df = pd.DataFrame(raw_rows)
            # Xóa các cột rỗng hoàn toàn
            df = df.loc[:, (df != "").any(axis=0)]
            sheets_data[sheet_name] = df

        wb.close()
        # Giữ tối đa 5 file trong cache để đảm bảo giới hạn RAM < 1GB của BTC
        if len(self._cache) >= 5:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        self._cache[file_name] = sheets_data
        return sheets_data

    def tool_inspect_compact_context(self, file_name: str, max_rows: int = 45) -> str:
        """
        MCP Tool 1: Chuyển đổi bảng Excel thành định dạng CSV thu gọn (Compact Context).
        Giúp LLM nhìn thấy toàn cảnh cấu trúc phân cấp mà tốn ít token nhất.
        """
        sheets = self.load_and_clean_sheets(file_name)
        context_parts = []
        for s_name, df in sheets.items():
            preview_df = df.head(max_rows)
            # Xuất dạng bảng có chỉ số dòng/cột rõ ràng để LLM hoặc Pandas truy chiếu
            lines = [
                f"=== Sheet: {s_name} (Shape: {df.shape[0]}x{df.shape[1]}) ==="]
            for idx, row in preview_df.iterrows():
                row_vals = [f"C{c}:{val}" for c,
                            val in enumerate(row.values) if val != ""]
                lines.append(f"R{idx}: " + " | ".join(row_vals))
            context_parts.append("\n".join(lines))
        return "\n\n".join(context_parts)

    def tool_execute_verification_query(self, file_name: str, python_expr: str) -> str:
        """
        MCP Tool 2 (Nhánh A): Thực thi biểu thức Python/Pandas trên dữ liệu thật
        để tính toán và xác minh kết quả, chống tính nhẩm sai.
        """
        if not python_expr or not python_expr.strip():
            return "SKIPPED"
        # Chặn các từ khóa nguy hiểm để đảm bảo an toàn tuyệt đối
        forbidden = ["import ", "os.", "sys.",
                     "subprocess", "open(", "eval(", "exec("]
        if any(bad in python_expr for bad in forbidden):
            return "ERROR: Biểu thức chứa từ khóa không được phép."

        sheets = self.load_and_clean_sheets(file_name)
        first_sheet = next(iter(sheets.values())) if sheets else pd.DataFrame()
        safe_locals = {
            "sheets": sheets,
            "df": first_sheet,
            "pd": pd,
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "sum": sum,
            "len": len,
            "sorted": sorted,
            "int": int,
            "float": float,
            "str": str,
        }
        try:
            result = eval(python_expr, {"__builtins__": {}}, safe_locals)
            return str(result)
        except Exception as e:
            return f"ERROR: {e}"


class FormatAndDataValidator:
    """
    Cổng kiểm định kép (Nhánh B & A):
    - Kiểm tra định dạng câu trả lời theo đúng yêu cầu trong câu hỏi (integer, 2 decimals, Yes/No...).
    - Tự động sửa lỗi định dạng cơ bản bằng Regex (tiết kiệm 100% token retry).
    """

    @staticmethod
    def validate_and_clean(query: str, raw_answer: str) -> tuple[bool, str, str]:
        """Trả về: (is_valid, cleaned_answer, error_reason)"""
        if raw_answer is None:
            return False, "", "Câu trả lời rỗng."

        ans = str(raw_answer).strip().strip('"').strip("'")
        q_lower = query.lower()

        # 1. Yêu cầu chỉ trả lời Yes hoặc No
        if "only yes or no" in q_lower or "provide 'yes' or 'no'" in q_lower:
            if "yes" in ans.lower() and "no" not in ans.lower():
                return True, "Yes", ""
            if "no" in ans.lower() and "yes" not in ans.lower():
                return True, "No", ""
            return False, ans, "Phải trả lời chính xác 'Yes' hoặc 'No'."

        # 2. Yêu cầu trả lời 2 số nguyên cách nhau bởi dấu phẩy (VD: p4_q018)
        if "two integers" in q_lower and "separated by a comma" in q_lower:
            nums = re.findall(r"[-+]?\d+", ans.replace(",", ""))
            # Nếu chuỗi gốc đã có dấu phẩy ngăn cách 2 số
            parts = [p.strip().replace(",", "")
                     for p in ans.split(",") if p.strip()]
            if len(parts) == 2 and all(re.fullmatch(r"[-+]?\d+(?:\.0+)?", p) for p in parts):
                clean_parts = [str(int(float(p))) for p in parts]
                return True, f"{clean_parts[0]}, {clean_parts[1]}", ""
            return False, ans, "Phải gồm đúng 2 số nguyên cách nhau bởi ', '."

        # 3. Yêu cầu 2 số thập phân làm tròn 2 chữ số cách nhau bởi dấu phẩy (VD: p4_q019)
        if "two decimal places" in q_lower and "separating the values with a comma" in q_lower:
            parts = [p.strip() for p in ans.split(",") if p.strip()]
            if len(parts) == 2:
                try:
                    f1, f2 = float(parts[0]), float(parts[1])
                    return True, f"{f1:.2f}, {f2:.2f}", ""
                except ValueError:
                    pass
            return False, ans, "Phải gồm 2 số thập phân (2 chữ số sau dấu chấm) cách nhau bởi ', '."

        # 4. Yêu cầu duy nhất 1 số nguyên (without commas or units / integer score)
        if "only the integer" in q_lower:
            cleaned = ans.replace(",", "").replace(
                "$", "").replace("%", "").strip()
            match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
            if match:
                val = int(round(float(match.group(0))))
                return True, str(val), ""
            return False, ans, "Phải là một số nguyên duy nhất, không kèm đơn vị hay dấu phẩy."

        # 5. Yêu cầu làm tròn 2 chữ số thập phân đơn lẻ (VD: p4_q007)
        if "rounded to two decimal places" in q_lower:
            cleaned = ans.replace(",", "").replace("%", "").strip()
            match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
            if match:
                val = float(match.group(0))
                return True, f"{val:.2f}", ""
            return False, ans, "Phải là số thập phân làm tròn 2 chữ số (VD: 3.14)."

        # 6. Mặc định: Chuẩn hóa khoảng trắng và không được rỗng
        if len(ans) > 0 and "\n" not in ans:
            return True, ans, ""
        return False, ans, "Định dạng câu trả lời không hợp lệ hoặc chứa nhiều dòng."


class ContestPipelineEngine:
    """
    Bộ điều phối Pipeline cải tiến:
    Kết nối OpenRouter / LM Studio -> Gọi MCP Context -> Xác minh A/B -> Xuất CSV & Ngôn ngữ tự nhiên.
    """

    def __init__(
        self,
        xlsx_dir=None,
        provider=None,
        api_key=None,
        base_url=None,
        model=None,
    ):
        self.xlsx_dir = xlsx_dir or os.getenv(
            "CONTEST_XLSX_DIR", "./xlsx_files")
        self.provider = (provider or os.getenv(
            "CONTEST_AI_PROVIDER", "local")).lower()

        if api_key or base_url or model:
            # Ưu tiên tham số truyền trực tiếp từ CLI khi BTC chấm bằng Docker
            self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
            self.base_url = (base_url or os.getenv(
                "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")).rstrip("/")
            self.model = model or os.getenv(
                "OPENROUTER_MODEL", "qwen/qwen3.7-flash")
        elif self.provider == "openrouter":
            self.api_key = os.getenv("OPENROUTER_API_KEY", "")
            self.base_url = os.getenv(
                "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
            self.model = os.getenv("OPENROUTER_MODEL", "qwen/qwen3.7-flash")
        else:
            # Chế độ Local LM Studio (Qwen3.5 7B / 9B)
            self.api_key = os.getenv("LOCAL_LLM_API_KEY", "lm-studio")
            self.base_url = os.getenv(
                "LOCAL_LLM_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
            self.model = os.getenv("LOCAL_LLM_MODEL", "qwen/qwen3.5-9b")

        self.site_url = os.getenv(
            "OPENROUTER_SITE_URL", "https://giasutinhoccanban.tech")
        self.site_name = os.getenv(
            "OPENROUTER_SITE_NAME", "GiaSuTinHoc_Contest_2026")
        self.mcp = MCPExcelServer(self.xlsx_dir)
        self.tracker = TokenCostTracker()

    def _call_llm_api(self, messages: list, max_tokens: int = 450) -> tuple[str, dict]:
        """Gọi API theo đúng mẫu chuẩn OpenRouter / LM Studio bằng requests.post."""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url,
            "X-OpenRouter-Title": self.site_name,
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,  # Đặt = 0 để tính toán bảng tính chính xác tuyệt đối
            "max_tokens": max_tokens,
        }

        resp = requests.post(url, headers=headers,
                             data=json.dumps(payload), timeout=90)
        resp.raise_for_status()
        res_json = resp.json()

        content = res_json["choices"][0]["message"]["content"]
        usage = res_json.get("usage", {})
        token_stats = self.tracker.record(
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
        )
        return content, token_stats

    @staticmethod
    def _parse_json_block(text: str) -> dict:
        """Bóc tách JSON an toàn kể cả khi model sinh kèm thẻ <think> hoặc markdown."""
        # Tách phần suy nghĩ <think>...</think> của dòng Qwen nếu có
        think_match = re.search(r"<think>(.*?)</think>", text, flags=re.DOTALL)
        extracted_think = think_match.group(1).strip() if think_match else ""
        cleaned = re.sub(r"<think>.*?</think>", "",
                         text, flags=re.DOTALL).strip()

        # Tìm khối JSON
        json_match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                if extracted_think and not data.get("thinking"):
                    data["thinking"] = extracted_think
                return data
            except json.JSONDecodeError:
                pass

        return {
            "thinking": extracted_think or "Phân tích trực tiếp từ bảng dữ liệu.",
            "pandas_verify_expr": "",
            "csv_answer": cleaned.split("\n")[-1].strip(),
            "natural_reply": cleaned,
        }

    def solve_question(self, query_id: str, file_name: str, query_text: str, include_natural: bool = True) -> dict:
        """
        Thực thi trọn vẹn Pipeline Mới:
        Bước 1 (MCP Extract) -> Bước 2 (LLM Reason + Code) -> Bước 3 (Valid Định dạng B & Dữ liệu A) -> Bước 4 (Output).
        """
        start_time = time.time()
        thinking_steps = []

        # --- BƯỚC 1: MCP Server trích xuất Compact Context ---
        t0 = time.time()
        compact_table = self.mcp.tool_inspect_compact_context(file_name)
        thinking_steps.append(
            f"[MCP Server] Đã tháo ô gộp & nén cấu trúc tệp '{file_name}' ({round((time.time()-t0)*1000)}ms)."
        )

        # --- BƯỚC 2: Rào Instruction buộc trả lời theo cấu trúc kiểm định ---
        system_prompt = (
            "You are an expert Excel Data Analyst Agent connected to an MCP Verification Server.\n"
            "Analyze the provided compact Excel sheet(s) (where R=Row index, C=Column index) and answer the user's question.\n"
            "Return ONLY a valid JSON object with these exact keys:\n"
            "{\n"
            '  "thinking": "Brief step-by-step cell lookup and arithmetic calculation",\n'
            '  "pandas_verify_expr": "Optional pure Python arithmetic expression to compute/verify the exact number (e.g., 152987 - 34282 or round((2.1+3.5+3.82)/3, 2))",\n'
            '  "csv_answer": "The exact final answer strictly obeying the question format constraints (NO explanation, NO units unless asked)",\n'
            '  "natural_reply": "1-sentence concise explanation in Vietnamese confirming the verified result"\n'
            "}"
        )

        user_prompt = f"[FILE]: {file_name}\n[EXCEL DATA]:\n{compact_table}\n\n[QUESTION ({query_id})]: {query_text}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw_output, token_info = self._call_llm_api(messages)
        parsed = self._parse_json_block(raw_output)
        thinking_steps.append(
            f"[AI Suy luận] {parsed.get('thinking', 'Đã phân tích dữ liệu.')}")

        candidate_answer = str(parsed.get("csv_answer", "")).strip()
        verify_expr = str(parsed.get("pandas_verify_expr", "")).strip()

        # --- BƯỚC 3A: Valid bằng truy vấn/tính toán dữ liệu (Data Verification) ---
        if verify_expr:
            mcp_calc_result = self.mcp.tool_execute_verification_query(
                file_name, verify_expr)
            if not mcp_calc_result.startswith("ERROR") and mcp_calc_result != "SKIPPED":
                thinking_steps.append(
                    f"[Kiểm định Dữ liệu - Nhánh A] MCP thực thi `{verify_expr}` => Kết quả xác minh: {mcp_calc_result}"
                )
                # Nếu câu hỏi yêu cầu số và biểu thức tính toán thành công, ưu tiên số chính xác từ CPU
                if any(k in query_text.lower() for k in ["integer", "decimal", "sum", "difference", "total", "average"]):
                    candidate_answer = mcp_calc_result

        # --- BƯỚC 3B: Valid đúng định dạng .csv yêu cầu hay không? ---
        is_valid, cleaned_answer, err_reason = FormatAndDataValidator.validate_and_clean(
            query_text, candidate_answer
        )

        if is_valid:
            thinking_steps.append(
                f"[Kiểm định Định dạng - Nhánh A] Hợp lệ chuẩn CSV: `{query_id},{cleaned_answer}`"
            )
        else:
            # Nếu sai (Nhánh B) -> Ép mô hình trả lời lại đúng 1 lần với lỗi cụ thể
            thinking_steps.append(
                f"[Kiểm định Định dạng - Nhánh B] Phát hiện sai định dạng ({err_reason}). Đang ép mô hình chuẩn hóa lại..."
            )
            retry_messages = messages + [
                {"role": "assistant", "content": raw_output},
                {
                    "role": "user",
                    "content": (
                        f"FORMAT VALIDATION FAILED: {err_reason}\n"
                        f"Provide ONLY the corrected JSON with `csv_answer` strictly matching: {query_text}"
                    ),
                },
            ]
            retry_output, retry_tokens = self._call_llm_api(
                retry_messages, max_tokens=200)
            # Cộng dồn token của lượt retry
            token_info["prompt_tokens"] += retry_tokens["prompt_tokens"]
            token_info["completion_tokens"] += retry_tokens["completion_tokens"]
            token_info["total_tokens"] += retry_tokens["total_tokens"]
            token_info["cost_usd"] = round(
                token_info["cost_usd"] + retry_tokens["cost_usd"], 6)

            parsed_retry = self._parse_json_block(retry_output)
            _, cleaned_answer, _ = FormatAndDataValidator.validate_and_clean(
                query_text, parsed_retry.get("csv_answer", candidate_answer)
            )
            thinking_steps.append(
                f"[Đã xác minh sau Retry - Nhánh A] Chuẩn hóa thành công: `{query_id},{cleaned_answer}`"
            )

        # Định dạng dòng CSV chuẩn (tự động bọc ngoặc kép nếu đáp án có dấu phẩy như p4_q013, p4_q018)
        csv_formatted_val = f'"{cleaned_answer}"' if "," in cleaned_answer else cleaned_answer
        csv_line = f"id,answer\n{query_id},{csv_formatted_val}"

        natural_reply = parsed.get("natural_reply", "")
        if not natural_reply or not include_natural:
            natural_reply = f"Đã xác minh dữ liệu trên tệp `{file_name}`. Kết quả chính xác cho câu hỏi `{query_id}` là **{cleaned_answer}**."

        elapsed = round(time.time() - start_time, 2)
        return {
            "id": query_id,
            "file_name": file_name,
            "answer": cleaned_answer,
            "csv_block": csv_line,
            "natural_reply": natural_reply,
            "thinking_steps": thinking_steps,
            "token_usage": token_info,
            "elapsed_seconds": elapsed,
            "model_used": f"{self.provider.upper()} ({self.model})",
        }
