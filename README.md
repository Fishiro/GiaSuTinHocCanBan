# 🏆 Bài dự thi AI 2026 — Bảng C (Mã đội: AI26C0084)

**Chủ đề 2: Hỏi đáp trên bảng tính Excel (Excel Question Answering)**

Giải pháp tự động trả lời câu hỏi bằng ngôn ngữ tự nhiên trên dữ liệu bảng tính Excel phức tạp (nhiều trang tính, nhiều bảng trên một sheet, tiêu đề phân cấp, ô gộp) sử dụng kiến trúc **MCP-Driven Hybrid Verification Pipeline**. Hệ thống kết hợp tiền xử lý cấu trúc bảng (0 token), suy luận LLM (`qwen/qwen3.7-flash`) và cổng kiểm định kép (xác minh số học bằng Python/Pandas + chuẩn hóa định dạng CSV).

---

## 📦 1. Cấu trúc Bài nộp (`AI26C0084.zip`)

```text
AI26C0084.zip
├── Dockerfile              # Cấu hình Docker chuẩn linux/amd64 (không dùng GPU, RAM < 1GB)
├── .dockerignore           # Loại bỏ dữ liệu thừa và khóa cá nhân khi build image
├── main.py                 # Entrypoint chính nhận tham số dòng lệnh và xuất submission.csv
├── mcp_excel_engine.py     # Lõi MCP Server nội bộ, tiền xử lý Excel, kiểm định A/B & đo Token
├── requirements.txt        # Danh sách thư viện Python phụ thuộc
├── README.md               # Tài liệu hướng dẫn cài đặt, cấu hình và chạy chương trình
├── server.py               # (Mở rộng) Backend Flask phục vụ giao diện Web trực quan
├── server.js               # (Mở rộng) Node.js Gateway phục vụ giao diện Web
├── package.json            # (Mở rộng) Cấu hình dependencies cho giao diện Web
└── public/                 # (Mở rộng) Giao diện Web tối giản có Tab "AI Thi Đấu" riêng
```

---

## 🐳 2. Chạy bằng Docker (Chuẩn Hệ thống Chấm tự động của BTC)

`Dockerfile` đặt ngay tại thư mục gốc của tệp nén, sử dụng `ENTRYPOINT ["python", "main.py"]` và nhận đầy đủ 6 tham số dòng lệnh của Ban Tổ chức:

```bash
# Bước 1: Build Docker image (kiến trúc linux/amd64, không cần GPU)
docker build --platform linux/amd64 -t ai26c0084 .

# Bước 2: Chạy container chấm bài
docker run --rm \
  -v /duong/dan/input:/input:ro \
  -v /duong/dan/output:/output \
  ai26c0084 \
  --xlsx-dir /input/xlsx_files \
  --queries /input/queries.json \
  --output /output/submission.csv \
  --openrouter-key "<OPENROUTER_API_KEY>" \
  --openrouter-model "qwen/qwen3.7-flash" \
  --openrouter-base-url "https://openrouter.ai/api/v1"
```

---

## 💻 3. Cài đặt & Chạy Trực tiếp bằng Dòng lệnh (CLI)

### 3.1. Cài đặt môi trường

- Yêu cầu: **Python 3.11+**
- Cài đặt thư viện:

```bash
pip install -r requirements.txt
```

### 3.2. Chạy với OpenRouter API (Model `qwen/qwen3.7-flash`)

```bash
python main.py \
  --xlsx-dir ./test_xlsx \
  --queries ./queries.json \
  --output ./submission.csv \
  --openrouter-key "<OPENROUTER_API_KEY>" \
  --openrouter-model "qwen/qwen3.7-flash" \
  --openrouter-base-url "https://openrouter.ai/api/v1"
```

### 3.3. Chạy thử nghiệm Local với LM Studio (`http://127.0.0.1:1234/v1`)

Khi không truyền `--openrouter-key` trên dòng lệnh, chương trình tự động đọc cấu hình trong `.env` và kết nối tới máy chủ LLM cục bộ (mặc định `http://127.0.0.1:1234/v1`):

```bash
python main.py \
  --xlsx-dir ./test_xlsx \
  --queries ./queries.json \
  --output ./submission.csv
```

---

## 🌐 4. Giao diện Web Trực quan (Tab "AI Thi Đấu")

Dự án tích hợp sẵn một tab giao diện tối giản để Ban Giám khảo theo dõi trực quan từng bước suy luận (**Thinking Steps**), kết quả xác minh dữ liệu và lượng **Token / Chi phí USD** theo thời gian thực:

1. Tạo tệp `.env` tại thư mục gốc (hoặc chỉnh sửa tệp `.env` sẵn có):

```env
# Chọn "openrouter" khi chấm bằng API OpenRouter, hoặc "local" khi test LM Studio
CONTEST_AI_PROVIDER=openrouter

# --- Cấu hình OpenRouter (BGK chỉ cần thay khóa API tại đây) ---
OPENROUTER_API_KEY=sk-or-v1-thay-key-tai-day
OPENROUTER_MODEL=qwen/qwen3.7-flash
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# --- Cấu hình LM Studio Local ---
LOCAL_LLM_BASE_URL=http://127.0.0.1:1234/v1
LOCAL_LLM_MODEL=qwen/qwen3.5-9b
LOCAL_LLM_API_KEY=lm-studio

# --- Đường dẫn dữ liệu mặc định ---
CONTEST_XLSX_DIR=./test_xlsx
CONTEST_QUERIES_FILE=./queries.json
CONTEST_OUTPUT_CSV=./submission.csv
```

2. Khởi chạy máy chủ Web:

```bash
npm install
npm run dev
```

3. Mở trình duyệt tại `http://localhost:3000` và chuyển sang tab **AI Thi Đấu** ở góc trên thanh điều hướng bên trái.

---

## 🧠 5. Nguyên lý Hoạt động & Tối ưu Tiêu chí Xếp hạng

1. **Bước 1 — Tiền xử lý Bảng tính qua MCP Server nội bộ (0 Token):**
    - Tự động tháo toàn bộ ô gộp (`unmerge_cells`) và điền đầy giá trị vào vùng gộp (Forward-fill) để bảo toàn ngữ cảnh tiêu đề phân cấp nhiều tầng.
    - Chuẩn hóa ngày tháng về `YYYY-MM-DD`, số nguyên về dạng chuẩn và nén bảng thành tọa độ `R{hàng}: C{cột}:Giá_trị`, giảm hơn 75% lượng token đầu vào.
2. **Bước 2 — Suy luận kết hợp Sinh biểu thức Xác minh (`qwen/qwen3.7-flash`):**
    - Mô hình xác định tọa độ ô dữ liệu liên quan và sinh biểu thức tính toán Python (`pandas_verify_expr`) cùng đáp án dự kiến (`csv_answer`).
3. **Bước 3 — Cổng Kiểm định Kép (Dual-Validation Gate A & B):**
    - **Kiểm định Dữ liệu (Nhánh A):** Thực thi biểu thức số học (`num(r, c)`, `cell(r, c)`, `sum`, `abs`, `round`, `sorted`) trực tiếp trên dữ liệu thật bằng Python để loại bỏ hoàn toàn sai số tính nhẩm của LLM.
    - **Kiểm định Định dạng (Nhánh B):** Kiểm tra nghiêm ngặt ràng buộc của câu hỏi (số nguyên không dấu phẩy, làm tròn 2 chữ số thập phân, `Yes`/`No`, xếp hạng phân tách bằng `, `). Tự động làm sạch bằng Regex (0 token) hoặc chỉ gọi retry tối đa 1 lần nếu sai cấu trúc.
4. **Đảm bảo Giới hạn Tài nguyên:**
    - **Chi phí:** Trung bình `~0.0003 - 0.0015 USD / câu hỏi` (thấp hơn rất nhiều so với trần `0.10 USD / câu hỏi`).
    - **Bộ nhớ & Thời gian:** Cơ chế LRU Cache giới hạn tối đa 5 tệp Excel trong bộ nhớ giúp RAM luôn dưới `200 MB` (giới hạn `< 1 GB`); tổng thời gian chạy 20 câu hỏi đạt `~1 - 3 phút` (giới hạn `< 40 phút`).

---

# 🎓 Gia sư Tin học căn bản — IT-Chatbot

Chatbot RAG (Retrieval-Augmented Generation) hỗ trợ giảng dạy và tra cứu **Tin học căn bản** theo chuẩn Thông tư 11/2018/TT-BLĐTBXH. Bot trả lời dựa trên tài liệu học tập thật (giáo trình, bài giảng, đề thi) thay vì chỉ dựa vào kiến thức nền của mô hình ngôn ngữ.

- **Backend**: Render (Node.js + Python)
- **Frontend**: Vercel (HTML/CSS/JS thuần)
- **LLM**: Google Gemini

---

## 📑 Mục lục

- [Kiến trúc tổng thể](#-kiến-trúc-tổng-thể)
- [Tính năng nổi bật](#-tính-năng-nổi-bật)
- [Cơ chế RAG hoạt động ra sao](#-cơ-chế-rag-retrieval-augmented-generation-hoạt-động-ra-sao)
- [Fallback đa API key](#-fallback-đa-api-key)
- [Các lớp bảo mật](#-các-lớp-bảo-mật--chống-bot)
- [Cấu trúc thư mục](#-cấu-trúc-thư-mục)
- [Công nghệ sử dụng](#-công-nghệ-sử-dụng)
- [Cài đặt & chạy local](#-cài-đặt--chạy-local)
- [Biến môi trường](#-biến-môi-trường)
- [Build lại dữ liệu RAG](#-build-lại-dữ-liệu-rag)
- [Triển khai (Deploy)](#-triển-khai-deploy)
- [Hạn chế & hướng cải thiện](#-hạn-chế--hướng-cải-thiện)
- [License](#-license)

---

## 🏗 Kiến trúc tổng thể

Dự án dùng mô hình **2 tầng (Gateway pattern)**:

```

Trình duyệt (Vercel)
│ HTTPS
▼
┌──────────────────────┐
│ Node.js (server.js) │ ← Gateway: phục vụ frontend tĩnh,
│ Express │ CORS, rate-limit, forward request
└─────────┬────────────┘
│ localhost:5000 (nội bộ)
▼
┌──────────────────────┐
│ Python (server.py) │ ← AI Backend: xác minh reCAPTCHA,
│ Flask │ truy vấn RAG, gọi Gemini
└─────────┬────────────┘
│
▼
┌─────────────┐ ┌────────────────┐
│ FAISS Index │ │ Gemini API │
│ (vector DB) │ │ (chat + embed) │
└─────────────┘ └────────────────┘

```

**Vì sao tách 2 tầng thay vì 1 backend duy nhất?**

| Lý do                       | Giải thích                                                                                                                          |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Hệ sinh thái AI             | Python có `langchain`, `faiss-cpu`, `google-genai` mạnh hơn hẳn Node cho RAG                                                        |
| Giới hạn nền tảng free-tier | Render free-tier chỉ chạy được **1 start command** → `server.js` tự `spawn()` `server.py` làm subprocess con để "lách" giới hạn này |
| Tách trách nhiệm            | Node lo phục vụ tĩnh + gateway nhẹ; Python lo toàn bộ logic AI                                                                      |

---

## ✨ Tính năng nổi bật

- 🔍 **RAG thực thụ**: bot trả lời dựa trên tài liệu học tập đã nạp (giáo trình Office 2013, bài giảng Excel, đề thi trắc nghiệm/thực hành, văn bản pháp quy...), không bịa đặt tính năng/phím tắt không có thật.
- 🔄 **Fallback đa API key**: tự động xoay vòng giữa nhiều Gemini API key khi 1 key hết quota — cho cả model chat **lẫn** model embedding.
- 🛡️ **Nhiều lớp bảo mật**: reCAPTCHA v3 vô hình, rate-limit kép, ban IP tạm thời, secret nội bộ giữa 2 tầng backend, helmet security headers.
- 📄 **Đọc đa định dạng tài liệu**: `.docx`, `.pptx`, `.xlsx`, `.csv`, `.txt`, `.pdf` (kể cả PDF scan qua OCR), và tự động convert file Office đời cũ (`.doc/.ppt/.xls`).
- ⚡ **Cập nhật dữ liệu tăng dần (incremental)**: chỉ nhúng lại phần tài liệu mới/thay đổi (so sánh hash SHA-256), không tốn quota nhúng lại toàn bộ mỗi lần.
- 🧠 **Giữ ngữ cảnh hội thoại**: mỗi session giữ lịch sử chat riêng, kể cả khi phải fallback sang API key khác giữa chừng.
- 🐢 **Chịu được cold-start free-tier**: nạp vector DB (FAISS) trong background thread, request đến sớm sẽ chờ thay vì bị bỏ qua RAG.

---

## 🧩 Cơ chế RAG (Retrieval-Augmented Generation) hoạt động ra sao

### Giai đoạn 1 — Chuẩn bị dữ liệu (offline, chạy `prepare_data.py`)

```

learning_data/\*.docx,.pptx,.xlsx,.pdf...
│
▼ 1. Trích xuất văn bản (đa định dạng, OCR nếu là PDF scan)
▼ 2. Cắt nhỏ thành từng đoạn (chunk)
▼ 3. Biến mỗi đoạn thành vector số (embedding) qua Gemini
▼ 4. Lưu vào FAISS index
faiss_index/ (index.faiss + index.pkl)

```

Chi tiết kỹ thuật:

1. **Trích xuất văn bản đa định dạng** (`extract_text_from_file`):
    - `.docx` → đọc cả đoạn văn lẫn nội dung bảng (table).
    - `.pptx` → đọc text trong từng shape của từng slide.
    - `.xlsx`/`.csv` → dùng `pandas`, giữ định dạng bảng.
    - `.pdf` → dùng `pdfplumber`; nếu trang không có text (PDF dạng ảnh scan) thì tự động **OCR** bằng Tesseract (hỗ trợ tiếng Việt).
    - `.doc/.ppt/.xls` (Office đời cũ) → tự động convert sang định dạng mới qua **LibreOffice headless** (ưu tiên, đa nền tảng) hoặc **Microsoft Office COM** (chỉ Windows) trước khi đọc.

2. **Chia nhỏ văn bản (chunking)**: dùng `RecursiveCharacterTextSplitter` với `chunk_size=1000, chunk_overlap=200`.
    - Chunk quá lớn → tìm kiếm kém chính xác (mỗi đoạn chứa quá nhiều ý khác nhau).
    - Chunk quá nhỏ → mất ngữ cảnh, trả lời rời rạc.
    - `overlap=200` đảm bảo không cắt đứt ý đang dang dở giữa 2 đoạn liền kề.

3. **Embedding**: mỗi đoạn văn bản được Gemini Embedding API (`gemini-embedding-001`) biến thành 1 vector số nhiều chiều, đại diện cho _ý nghĩa_ của đoạn đó.

4. **Lưu vào FAISS**: thư viện tìm kiếm vector tốc độ cao của Meta, chạy hoàn toàn local (không cần server vector DB riêng) — phù hợp free-tier.

5. **Manifest tăng dần** (`embed_manifest.json`): lưu hash SHA-256 của từng file đã nhúng. Lần chạy sau, script so sánh hash để:
    - Bỏ qua file không đổi (tiết kiệm quota API).
    - Chỉ nhúng lại file mới/đã sửa.
    - Tự xoá vector của file đã bị xoá khỏi `learning_data/`.

6. **Checkpoint sau mỗi file**: nếu mất mạng/lỗi quota giữa chừng, chạy lại script sẽ tiếp tục từ file dang dở, không mất tiến độ.

### Giai đoạn 2 — Trả lời câu hỏi (online, mỗi request tới `/api/chat`)

```

Câu hỏi user
│
▼ 1. Embed câu hỏi thành vector
▼ 2. Tìm trong FAISS các đoạn tài liệu gần nghĩa nhất (similarity search)
▼ 3. Lọc theo ngưỡng độ liên quan (relevance score ≥ 0.55)
▼ 4. Ghép đoạn tài liệu tìm được + câu hỏi → gửi Gemini
▼ 5. Gemini trả lời DỰA TRÊN tài liệu, không bịa đặt
Câu trả lời

```

Điểm quan trọng: nếu **không tìm được đoạn nào đủ liên quan** (dưới ngưỡng `RAG_MIN_RELEVANCE`), hệ thống vẫn báo rõ cho Gemini biết "không tìm thấy tài liệu phù hợp" thay vì im lặng bỏ qua — nhờ vậy `system_instruction` mới có thể khiến model **từ chối đúng cách** (trả lời đúng câu quy định) thay vì bịa ra câu trả lời không có căn cứ.

---

## 🔄 Fallback đa API key

Dự án dùng 2 Gemini API key (`GEMINI_API_KEY_1`, `GEMINI_API_KEY_2`) với cơ chế fallback áp dụng ở **2 nơi độc lập**:

|                      | Model chat (trả lời)                                                                    | Model embedding (tìm kiếm RAG)                            |
| -------------------- | --------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| Dùng khi nào         | Mỗi lần gọi trả lời câu hỏi                                                             | Lúc build FAISS index + mỗi câu hỏi user                  |
| Cơ chế               | `clients[current_key_index]`, xoay vòng khi gặp lỗi `429 / quota / exhausted`           | Class `FallbackEmbeddings` tự viết, thử lần lượt từng key |
| Bảo toàn gì          | Copy lại **lịch sử hội thoại** sang session dùng key mới — user không mất ngữ cảnh chat | Không có trạng thái cần giữ, chỉ retry với key khác       |
| Chống race condition | `threading.Lock()` khi nhiều request cùng lúc kích hoạt fallback                        | Có lock riêng trong class `FallbackEmbeddings`            |

Ở script `prepare_data.py` (chuẩn bị dữ liệu offline) còn dùng thêm chiến lược **chủ động xoay vòng key theo từng batch** — không đợi đến khi bị lỗi mới đổi key, mà chủ động chia đều tải giữa các key ngay từ đầu để giảm khả năng bị giới hạn tốc độ (rate limit).

---

## 🛡 Các lớp bảo mật & chống bot

Áp dụng theo nguyên tắc **phòng thủ theo chiều sâu** (defense in depth) — nhiều lớp độc lập, lớp này chặn không được thì lớp sau vẫn chặn:

| #   | Lớp bảo vệ                                | Mục đích                                                                                                                     |
| --- | ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| 1   | **CORS whitelist**                        | Chỉ domain cụ thể (`giasutinhoccanban.tech`, `it-chatbot.vercel.app`...) được gọi API, khớp cấu hình ở cả Node và Flask      |
| 2   | **reCAPTCHA v3 vô hình**                  | Chấm điểm độ tin cậy 0.0–1.0 là người thật, không cần user thao tác gì; fail-open khi Google lỗi tạm thời để tránh chặn nhầm |
| 3   | **Rate-limit theo IP**                    | Giới hạn 15 request/phút/IP, áp dụng ở **cả 2 tầng** (Node và Flask) — phòng trường hợp Flask bị gọi thẳng, bỏ qua Node      |
| 4   | **Ban IP tạm thời**                       | Nếu 1 IP xác minh captcha thất bại nhiều lần liên tiếp trong thời gian ngắn → chặn tạm, chống brute-force                    |
| 5   | **Internal secret** (`X-Internal-Secret`) | Flask chỉ nhận request có kèm secret bí mật này, đảm bảo request thực sự đến từ Node gateway, không phải ai đó gọi thẳng     |
| 6   | **Giới hạn kích thước dữ liệu**           | Giới hạn độ dài message, sessionID, dung lượng request body — cả ở Express lẫn Flask                                         |
| 7   | **Helmet**                                | Tự động thêm các HTTP security header (chống clickjacking, MIME-sniffing...)                                                 |
| 8   | **`trust proxy` / `ProxyFix`**            | Bắt buộc khi chạy sau reverse proxy (Render) để rate-limit nhận đúng IP thật của client, không phải IP nội bộ của proxy      |
| 9   | **Ẩn chi tiết lỗi nội bộ**                | Không trả traceback/stack trace ra client, chỉ log chi tiết ở server                                                         |

---

## 📁 Cấu trúc thư mục

```

IT-Chatbot/
├── server.js # Node.js Gateway: static hosting, CORS, rate-limit, forward request
├── server.py # Flask AI Backend: reCAPTCHA, RAG, gọi Gemini
├── prepare_data.py # Script offline: đọc tài liệu → chunk → embed → lưu FAISS
├── check_models.py # Script kiểm tra model Gemini khả dụng
├── requirements.txt # Dependencies Python
├── package.json # Dependencies Node.js
├── runtime.txt # Phiên bản Python dùng trên Render
├── faiss_index/ # Vector DB đã build sẵn (index.faiss + index.pkl)
├── embed_manifest.json # Theo dõi file nào đã nhúng (hash-based, incremental)
├── learning_data/ # Tài liệu học tập nguồn (giáo trình, đề thi, văn bản pháp quy...)
└── public/ # Frontend tĩnh
├── index.html
├── script.js # Gọi reCAPTCHA, gửi/nhận tin nhắn, quản lý session UI
└── style.css

```

---

## 🧰 Công nghệ sử dụng

| Thành phần        | Công nghệ                                                                                      |
| ----------------- | ---------------------------------------------------------------------------------------------- |
| Frontend          | HTML/CSS/JS thuần (không framework), Tailwind CDN, `marked.js` (render Markdown)               |
| Gateway           | Node.js + Express 5                                                                            |
| AI Backend        | Python 3.11 + Flask                                                                            |
| LLM               | Google Gemini (`gemini-flash-lite-latest`)                                                     |
| Embedding         | Google Gemini Embedding (`gemini-embedding-001`)                                               |
| Vector Database   | FAISS (Facebook AI Similarity Search) — chạy local                                             |
| Orchestration RAG | LangChain (`langchain`, `langchain-google-genai`, `langchain-community`)                       |
| Đọc tài liệu      | `python-docx`, `python-pptx`, `openpyxl`, `pandas`, `pdfplumber`, `pypdf`, `pytesseract` (OCR) |
| Bảo mật           | Google reCAPTCHA v3, `express-rate-limit`, `flask-limiter`, `helmet`                           |
| Deploy            | Backend: **Render** — Frontend: **Vercel**                                                     |

---

## ⚙️ Cài đặt & chạy local

### Yêu cầu

- Node.js ≥ 18
- Python 3.11.0
- (Tùy chọn) LibreOffice nếu cần đọc file Office đời cũ (`.doc/.ppt/.xls`)
- (Tùy chọn) Tesseract OCR nếu cần đọc PDF dạng scan

### Các bước

```bash
# 1. Clone repo
git clone https://github.com/Fishiro/IT-Chatbot.git
cd IT-Chatbot

# 2. Cài dependencies Node
npm install

# 3. Cài dependencies Python
pip install -r requirements.txt

# 4. Tạo file .env ở thư mục gốc (xem mục Biến môi trường bên dưới)

# 5. Chạy ở chế độ dev (Node + Python chạy song song, tự động reload)
npm run dev
```

Sau khi chạy, mở trình duyệt tại `http://localhost:3000`.

> `npm run dev` dùng `concurrently` để chạy riêng `server.js` (`--watch`) và `server.py` cùng lúc, kèm `SKIP_PYTHON_SPAWN=1` để `server.js` không tự spawn Python lần nữa (tránh chạy trùng 2 lần).

---

## 🔑 Biến môi trường

Tạo file `.env` ở thư mục gốc với nội dung:

```env
# --- Bắt buộc ---
GEMINI_API_KEY_1=your_first_gemini_api_key
GEMINI_API_KEY_2=your_second_gemini_api_key   # tùy chọn, dùng cho fallback

# --- Bảo mật ---
RECAPTCHA_SECRET_KEY=your_recaptcha_v3_secret_key
INTERNAL_SECRET=random_string_dai_it_nhat_32_ky_tu

# --- Tùy chọn (đều có giá trị mặc định hợp lý) ---
RAG_MAX_WAIT_SECONDS=55        # thời gian tối đa chờ FAISS nạp xong
RAG_TOP_K=3                    # số đoạn tài liệu lấy ra mỗi lần tìm kiếm
RAG_MIN_RELEVANCE=0.55         # ngưỡng độ liên quan (0..1)
MAX_ACTIVE_SESSIONS=200        # số session tối đa giữ trong RAM
MAX_MESSAGE_LENGTH=2000        # độ dài tối đa 1 tin nhắn
CAPTCHA_BAN_THRESHOLD=5        # số lần fail captcha trước khi ban IP tạm
CAPTCHA_BAN_WINDOW=300         # thời gian ban IP (giây)
DEBUG_RAG=0                    # đặt =1 để log chi tiết quá trình truy vấn RAG
SKIP_PYTHON_SPAWN=0            # đặt =1 khi chạy dev để tránh spawn Python trùng lặp
```

> ⚠️ **Không commit file `.env` lên GitHub** — đã có sẵn trong `.gitignore`. Khi deploy trên Render, khai báo các biến này trong tab **Environment** của service.

---

## 📚 Build lại dữ liệu RAG

Khi thêm/sửa/xoá tài liệu trong `learning_data/`, cần chạy lại script để cập nhật `faiss_index/`:

```bash
# Cập nhật tăng dần — chỉ nhúng phần mới/thay đổi (khuyên dùng)
python prepare_data.py

# Xây dựng lại toàn bộ từ đầu (xoá index + manifest cũ, nhúng lại tất cả)
python prepare_data.py --rebuild
```

Có thể dùng nhiều key cùng lúc để tăng tốc độ nhúng (script tự xoay vòng key theo batch):

```env
GEMINI_API_KEYS=key1,key2,key3,key4,key5
```

Sau khi chạy xong, commit `faiss_index/` và `embed_manifest.json` mới vào repo để deploy dùng dữ liệu đã cập nhật.

---

## 🚀 Triển khai (Deploy)

### Backend — Render

1. Tạo **Web Service** mới trên Render, trỏ vào repo GitHub này.
2. Start command: `npm start` (Node sẽ tự spawn Python — xem giải thích kiến trúc ở trên).
3. Khai báo đầy đủ biến môi trường ở mục [Biến môi trường](#-biến-môi-trường).
4. (Khuyên dùng) Gắn UptimeRobot hoặc dịch vụ ping tương tự gọi `GET`/`HEAD` tới `/health` định kỳ để tránh service free-tier bị "ngủ".

### Frontend — Vercel

1. Deploy thư mục `public/` như 1 static site trên Vercel.
2. Đảm bảo `API_URL` trong `public/script.js` trỏ đúng domain Render đã deploy.
3. Thêm domain Vercel vào danh sách `ALLOWED_ORIGINS` trong cả `server.js` và `server.py`.

---

## 🔧 Hạn chế & hướng cải thiện

- `faiss_index/` được build local rồi commit thẳng vào Git — nếu `learning_data/` thay đổi thường xuyên, nên cân nhắc CI/CD tự động build lại thay vì build tay.
- Session chat và `current_key_index` hiện lưu trong RAM (biến toàn cục) — phù hợp 1 instance; nếu sau này scale nhiều instance cần chuyển sang lưu trữ chung (Redis, DB).
- `allow_dangerous_deserialization=True` khi load FAISS — an toàn khi chỉ 1 mình bạn kiểm soát file `index.pkl`, cần lưu ý nếu sau này có nhiều người cùng quản lý repo.
- File tài liệu trong `learning_data/` khá nặng (có file gần 20MB) — nếu dữ liệu tiếp tục tăng, nên cân nhắc Git LFS.

---

## 📄 License

**All Rights Reserved.** Đây **KHÔNG PHẢI** mã nguồn mở — mọi hình thức sao chép, sửa đổi, phân phối, hay triển khai lại (kể cả một phần) đều cần được sự đồng ý bằng văn bản của chủ sở hữu bản quyền. Xem chi tiết tại [LICENSE](./LICENSE).
