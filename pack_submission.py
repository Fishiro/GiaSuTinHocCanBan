# File: pack_submission.py
# Mô tả: Đóng gói tự động bài nộp AI26C0084.zip đúng chuẩn cấu trúc gốc của BTC (< 100MB, không chứa API key).

import os
import zipfile

TEAM_ID = "AI26C0084"
OUTPUT_ZIP = f"{TEAM_ID}.zip"

# Danh sách các tệp và thư mục mã nguồn cần đưa vào gốc của AI26C0084.zip
INCLUDE_FILES = [
    "Dockerfile",
    ".dockerignore",
    "README.md",
    "main.py",
    "mcp_excel_engine.py",
    "server.py",
    "server.js",
    "package.json",
    "requirements.txt",
    "runtime.txt",
]

INCLUDE_DIRS = [
    "public",
]


def build_zip():
    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_name in INCLUDE_FILES:
            if os.path.exists(file_name):
                # Ghi trực tiếp vào gốc của file ZIP (arcname=file_name)
                zf.write(file_name, arcname=file_name)
                print(f"  [+] Đã thêm: {file_name}")
            else:
                print(f"  [!] Cảnh báo thiếu file: {file_name}")

        for folder in INCLUDE_DIRS:
            if os.path.isdir(folder):
                for root, _, files in os.walk(folder):
                    for f in files:
                        full_path = os.path.join(root, f)
                        rel_path = os.path.relpath(full_path, ".")
                        zf.write(full_path, arcname=rel_path)
                print(f"  [+] Đã thêm thư mục: {folder}/")

    size_mb = os.path.getsize(OUTPUT_ZIP) / (1024 * 1024)
    print("=" * 60)
    print(
        f"✅ Đóng gói thành công: {OUTPUT_ZIP} ({size_mb:.2f} MB / giới hạn 100 MB)")
    print("   - Dockerfile & README.md đã nằm ngay tại thư mục gốc của ZIP.")
    print("   - Đã loại bỏ hoàn toàn file .env (không lộ API key) và dữ liệu rác.")
    print("=" * 60)


if __name__ == "__main__":
    build_zip()
