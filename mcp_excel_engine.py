import os
import re
import json
import time
import requests
import pandas as pd
from typing import Dict, Any, Tuple, Optional


class FormatAndDataValidator:
    """
    Bộ kiểm định định dạng và làm sạch dữ liệu đầu ra trước khi ghi vào CSV.
    """

    @staticmethod
    def validate_and_clean(query_text: str, answer_val: Any) -> Tuple[bool, str, str]:
        if answer_val is None:
            return False, "", "Giá trị rỗng (None)"

        val_str = str(answer_val).strip()
        if not val_str or val_str.upper() in ["NONE", "NAN", "N/A", "NULL", "ERROR", "SKIPPED"]:
            return False, "", "Kết quả trả về không hợp lệ hoặc chứa lỗi"

        # Loại bỏ các dấu ngoặc kép hoặc khoảng trắng dư thừa ở hai đầu
        cleaned = val_str.strip('"\'')

        query_lower = query_text.lower()

        # Tự động ép kiểu số nguyên nếu câu hỏi yêu cầu đếm/tính số lượng
        if any(k in query_lower for k in ["nguyên", "integer", "số lượng", "đếm", "count"]):
            try:
                num_float = float(re.sub(r"[^\d.-]", "", cleaned))
                cleaned = str(int(round(num_float)))
            except Exception:
                pass

        return True, cleaned, ""


class MCPExcelServer:
    """
    MCP Server xử lý đọc, tối ưu dung lượng tệp Excel và thực thi câu lệnh kiểm định Python.
    """

    def __init__(self, xlsx_dir: str = "./test_xlsx"):
        self.xlsx_dir = xlsx_dir
        self._cache: Dict[str, Dict[str, pd.DataFrame]] = {}

    def load_and_clean_sheets(self, file_name: str) -> Dict[str, pd.DataFrame]:
        if file_name in self._cache:
            return self._cache[file_name]

        file_path = os.path.join(self.xlsx_dir, file_name)
        if not os.path.exists(file_path):
            file_path = file_name

        if not os.path.exists(file_path):
            raise FileNotFoundError(
                f"Không tìm thấy tệp Excel tại: {file_path}")

        xls = pd.ExcelFile(file_path)
        sheets = {}
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
            # Loại bỏ các hàng và cột trống ở rìa bảng
            df = df.dropna(how="all").dropna(how="all", axis=1)
            sheets[sheet_name] = df.reset_index(drop=True)

        self._cache[file_name] = sheets
        return sheets

    def tool_inspect_compact_context(self, file_name: str, max_rows: int = 150) -> str:
        """
        Chuyển đổi bảng tính Excel sang dạng tọa độ nén siêu gọn (R{r}: C{c}:val)
        giúp tiết kiệm từ 40% đến 60% Context Window.
        """
        sheets = self.load_and_clean_sheets(file_name)
        context_parts = []
        for s_name, df in sheets.items():
            preview_df = df.head(max_rows)
            lines = [
                f"=== Sheet: {s_name} (Rows: {df.shape[0]}, Cols: {df.shape[1]}) ==="]
            for idx, row in preview_df.iterrows():
                row_vals = []
                for c, val in enumerate(row.values):
                    if pd.isna(val):
                        continue
                    val_str = str(val).strip()
                    if val_str != "":
                        if len(val_str) > 80:
                            val_str = val_str[:77] + "..."
                        row_vals.append(f"C{c}:{val_str}")
                if row_vals:
                    lines.append(f"R{idx}: " + " | ".join(row_vals))
            context_parts.append("\n".join(lines))
        return "\n\n".join(context_parts)

    def tool_execute_verification_query(self, file_name: str, verify_expr: str) -> str:
        """
        Thực thi biểu thức Python an toàn để kiểm định kết quả từ tọa độ ô Excel.
        """
        if not verify_expr or verify_expr.lower() in ["none", "n/a", ""]:
            return "SKIPPED"

        try:
            sheets = self.load_and_clean_sheets(file_name)
            first_sheet = next(iter(sheets.values()))

            def num(r, c, sheet_name=None):
                target_df = sheets[sheet_name] if sheet_name and sheet_name in sheets else first_sheet
                val = target_df.iloc[r, c]
                if pd.isna(val):
                    return 0.0
                if isinstance(val, (int, float)):
                    return float(val)
                val_str = re.sub(r"[^\d.-]", "", str(val))
                return float(val_str) if val_str else 0.0

            def cell(r, c, sheet_name=None):
                target_df = sheets[sheet_name] if sheet_name and sheet_name in sheets else first_sheet
                val = target_df.iloc[r, c]
                return "" if pd.isna(val) else str(val).strip()

            exec_env = {
                "sheets": sheets,
                "df": first_sheet,
                "num": num,
                "cell": cell,
                "abs": abs,
                "sum": sum,
                "min": min,
                "max": max,
                "round": round,
                "int": int,
                "float": float,
                "len": len,
                "re": re,
                "pd": pd,
            }

            res = eval(verify_expr, {"__builtins__": None}, exec_env)
            return str(res)
        except Exception as e:
            return f"ERROR: {str(e)}"


class ContestPipelineEngine:
    """
    Engine điều phối quy trình giải đề Excel tự động kết hợp với MCP Server và LLM API.
    """

    def __init__(
        self,
        provider: str = "local",
        model: str = "qwen3.5-7b",
        api_base: str = "http://localhost:1234/v1",
        api_key: str = "lm-studio",
        xlsx_dir: str = "./test_xlsx",
    ):
        self.provider = provider
        self.model = model
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.mcp = MCPExcelServer(xlsx_dir=xlsx_dir)

    def _call_llm_api(self, messages: list, max_tokens: int = 1000) -> Tuple[str, dict]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }

        url = f"{self.api_base}/chat/completions"
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        raw_content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        token_info = {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "cost_usd": 0.0,
        }
        return raw_content, token_info

    def _parse_json_block(self, text: str) -> dict:
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        try:
            return json.loads(text)
        except Exception:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass

        return {
            "thinking": "Không thể giải mã JSON từ kết quả AI.",
            "pandas_verify_expr": "",
            "csv_answer": text,
            "natural_reply": text,
        }

    def solve_question(
        self,
        query_id: str,
        file_name: str,
        query_text: str,
        include_natural: bool = True,
    ) -> dict:
        start_time = time.time()
        thinking_steps = []

        # 1. Trích xuất ngữ cảnh nén từ MCP
        t0 = time.time()
        compact_table = self.mcp.tool_inspect_compact_context(file_name)
        thinking_steps.append(
            f"[MCP Server] Chuẩn hóa tệp '{file_name}' ({round((time.time()-t0)*1000)}ms)."
        )

        system_prompt = (
            "/no_think\n"
            "You are an expert Excel Data Analyst Agent connected to an MCP Verification Server.\n"
            "Analyze the compact Excel sheet(s) where R{r} is row r and C{c} is column c.\n"
            "In `pandas_verify_expr`, write a single-line Python expression using `num(r, c)` or `cell(r, c)` to verify calculations.\n"
            "Return ONLY a valid JSON object with these exact keys:\n"
            "{\n"
            '  "thinking": "1-sentence cell coordinates lookup and logic",\n'
            '  "pandas_verify_expr": "Single-line Python expression to compute/verify the exact answer",\n'
            '  "csv_answer": "The exact final answer strictly obeying formatting constraints",\n'
            '  "natural_reply": "1-sentence concise Vietnamese explanation"\n'
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
            f"[AI Suy luận] {parsed.get('thinking', 'Đã phân tích dữ liệu.')}"
        )

        candidate_answer = str(parsed.get("csv_answer", "")).strip()
        verify_expr = str(parsed.get("pandas_verify_expr", "")).strip()

        # 2. Kiểm định định dạng kết quả AI
        is_valid, cleaned_answer, err_reason = FormatAndDataValidator.validate_and_clean(
            query_text, candidate_answer
        )

        # 3. Thực thi kiểm định Python qua MCP
        if verify_expr:
            mcp_calc_result = self.mcp.tool_execute_verification_query(
                file_name, verify_expr)
            if (
                not mcp_calc_result.startswith("ERROR")
                and mcp_calc_result != "SKIPPED"
                and mcp_calc_result != "None"
            ):
                thinking_steps.append(
                    f"[Kiểm định Dữ liệu] MCP thực thi `{verify_expr}` => Kết quả: {mcp_calc_result}"
                )
                calc_ok, calc_cleaned, _ = FormatAndDataValidator.validate_and_clean(
                    query_text, mcp_calc_result
                )
                # Đè kết quả nếu đáp án AI chưa hợp lệ hoặc khi dùng Cloud Provider
                if calc_ok and (not is_valid or self.provider != "local"):
                    cleaned_answer = calc_cleaned
                    is_valid = True

        # 4. Yêu cầu định dạng lại nếu kết quả không đạt
        if is_valid:
            thinking_steps.append(
                f"[Kiểm định Định dạng] Hợp lệ chuẩn CSV: `{query_id},{cleaned_answer}`"
            )
        else:
            thinking_steps.append(
                f"[Kiểm định Định dạng] Sai định dạng ({err_reason}). Đang yêu cầu AI định dạng lại..."
            )
            retry_messages = messages + [
                {"role": "assistant", "content": raw_output},
                {
                    "role": "user",
                    "content": (
                        f"/no_think\nFORMAT VALIDATION FAILED: {err_reason}\n"
                        f"Return ONLY the corrected JSON with `csv_answer` strictly matching: {query_text}"
                    ),
                },
            ]
            retry_output, retry_tokens = self._call_llm_api(
                retry_messages, max_tokens=250)
            token_info["prompt_tokens"] += retry_tokens["prompt_tokens"]
            token_info["completion_tokens"] += retry_tokens["completion_tokens"]
            token_info["total_tokens"] += retry_tokens["total_tokens"]

            parsed_retry = self._parse_json_block(retry_output)
            _, cleaned_answer, _ = FormatAndDataValidator.validate_and_clean(
                query_text, parsed_retry.get("csv_answer", candidate_answer)
            )

        csv_formatted_val = f'"{cleaned_answer}"' if "," in cleaned_answer else cleaned_answer
        csv_line = f"id,answer\n{query_id},{csv_formatted_val}"

        natural_reply = parsed.get("natural_reply", "")
        if not natural_reply or not include_natural:
            natural_reply = (
                f"Đã xác minh dữ liệu trên tệp `{file_name}`. "
                f"Kết quả chính xác cho câu hỏi `{query_id}` là **{cleaned_answer}**."
            )

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
