const sendBtn = document.getElementById("send-btn");
const userInput = document.getElementById("user-input");
const chatMessages = document.getElementById("chat-messages");
const historyList = document.getElementById("history-list");
const newChatBtn = document.getElementById("new-chat-btn");
const inputWrapper = document.getElementById("input-wrapper");

const API_URL =
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1"
        ? "http://localhost:3000/api/chat"
        : "/api/chat";

const RECAPTCHA_SITE_KEY = "6Lc_1aItAAAAAB-QDCxy0BpLBn-uyLqoni7MvEdL";

// Lấy token reCAPTCHA v3 (vô hình — không cần user thao tác gì).
// Nếu vì lý do nào đó reCAPTCHA chưa load được (mạng chậm, bị chặn quảng
// cáo...) thì trả về null, để không làm gãy trải nghiệm gửi tin nhắn —
// backend sẽ tự quyết định chặn hay không khi thiếu token.
async function getCaptchaToken(action = "chat") {
    try {
        if (typeof grecaptcha === "undefined" || !grecaptcha?.execute) {
            return null;
        }
        return await new Promise((resolve) => {
            grecaptcha.ready(() => {
                grecaptcha
                    .execute(RECAPTCHA_SITE_KEY, { action })
                    .then(resolve)
                    .catch(() => resolve(null));
            });
        });
    } catch {
        return null;
    }
}

// --- QUẢN LÝ TRẠNG THÁI ---
let currentAbortController = null;
let currentTypingTimeout = null;
let sessions = {};
let currentSessionID = generateSessionID();
let currentTitle = "Đoạn chat mới";
let isFirstMessage = true;

// Khởi tạo session mặc định đầu tiên
sessions[currentSessionID] = { title: currentTitle, messages: [] };

function generateSessionID() {
    return `session-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

sendBtn.addEventListener("click", sendMessage);

// Textarea: Enter gửi, Shift+Enter xuống dòng
userInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// ---- AUTO-RESIZE & SHOW/HIDE SEND BTN (MOBILE) ----
function autoResizeTextarea() {
    userInput.style.height = "auto";
    const isMobile = window.innerWidth < 768;
    if (isMobile) {
        userInput.style.height = Math.min(userInput.scrollHeight, 130) + "px";
        if (userInput.value.trim().length > 0) {
            inputWrapper.classList.add("has-text");
        } else {
            inputWrapper.classList.remove("has-text");
        }
    } else {
        userInput.style.height = userInput.scrollHeight + "px";
    }
}

userInput.addEventListener("input", autoResizeTextarea);

window.addEventListener("resize", () => {
    autoResizeTextarea();
    if (window.innerWidth >= 768) {
        inputWrapper.classList.remove("has-text");
    }
});

// --- HÀM GỬI TIN NHẮN ---
async function sendMessage() {
    const message = userInput.value.trim();
    if (!message) return;

    // Lưu tin nhắn của user vào session
    sessions[currentSessionID].messages.push({ sender: "user", text: message });
    addMessageToChat("user", message);

    // Reset input
    userInput.value = "";
    autoResizeTextarea();

    // Thiết lập UI nếu là tin nhắn đầu
    if (isFirstMessage) {
        isFirstMessage = false;
        // Hiện ngay đoạn chat lên Sidebar với tên trích xuất tạm từ tin nhắn
        let tempTitle = message.substring(0, 25);
        if (message.length > 25) tempTitle += "...";
        currentTitle = tempTitle;
        sessions[currentSessionID].title = currentTitle;
        addSessionToHistoryUI(currentSessionID, currentTitle);

        // LƯU Ý: Không gọi generateAITitle ở đây nữa để tránh làm chết Server Python cục bộ
    }

    // Khóa UI & Hiển thị indicator
    if (typeof showThinkingIndicator === "function") showThinkingIndicator();
    userInput.disabled = true;
    sendBtn.disabled = true;

    // Hủy request trước đó nếu đang chạy ngầm
    if (currentAbortController) {
        currentAbortController.abort();
    }
    currentAbortController = new AbortController();
    const signal = currentAbortController.signal;

    // Hủy hiệu ứng gõ chữ cũ nếu có
    if (currentTypingTimeout) {
        clearTimeout(currentTypingTimeout);
        currentTypingTimeout = null;
    }

    try {
        // BẢO MẬT: lấy token reCAPTCHA v3 vô hình trước khi gửi — không có
        // bước thao tác nào của người dùng, chạy nền trong lúc gõ.
        const captchaToken = await getCaptchaToken("chat");

        const response = await fetch(API_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            // THÊM SESSION ID ĐỂ BACKEND NHỚ LỊCH SỬ CHAT
            body: JSON.stringify({
                message: message,
                sessionID: currentSessionID,
                captchaToken: captchaToken,
            }),
            signal: signal,
        });

        const data = await response.json();

        // FIX: nếu backend trả lỗi (429 rate-limit, 403 captcha, 502 bad
        // gateway...), data sẽ không có "reply" mà có "error" — cần bung
        // ra đúng lỗi thật ở đây, thay vì cố hiển thị reply=undefined rồi
        // rơi vào lỗi JS chung chung khiến không biết nguyên nhân thật.
        if (!response.ok) {
            throw new Error(
                data?.error || `Lỗi máy chủ (mã ${response.status}).`,
            );
        }

        // Lưu tin nhắn của AI vào session
        sessions[currentSessionID].messages.push({
            sender: "bot",
            text: data.reply,
        });

        // Tắt indicator
        if (typeof hideThinkingIndicator === "function")
            hideThinkingIndicator();
        document
            .querySelectorAll(".typing-indicator")
            .forEach((el) => el.remove());

        // Hiển thị tin nhắn chính
        addMessageToChat("bot", data.reply, true);

        // Backend tạo title local trong CÙNG request /api/chat.
        // Không gọi API thứ hai để tránh tốn rate-limit/quota và tạo session rác.
        if (data?.title && typeof data.title === "string") {
            const aiTitle = data.title.trim();
            if (aiTitle && sessions[currentSessionID]) {
                sessions[currentSessionID].title = aiTitle;
                currentTitle = aiTitle;

                const histBtn = document.getElementById(
                    `hist-${currentSessionID}`,
                );
                const titleSpan = histBtn?.querySelector(".hist-title");
                if (titleSpan) titleSpan.textContent = aiTitle;
            }
        }
    } catch (error) {
        if (error.name === "AbortError") {
            console.log("Đã hủy request cũ do người dùng chuyển session.");
        } else {
            console.error("Lỗi khi gọi AI:", error);
            if (typeof hideThinkingIndicator === "function")
                hideThinkingIndicator();
            document
                .querySelectorAll(".typing-indicator")
                .forEach((el) => el.remove());
            // Hiện lỗi thật (vd "Bạn gửi quá nhanh", "Bad Gateway"...) thay
            // vì luôn hiện 1 câu chung chung — dễ chẩn đoán sự cố hơn.
            const friendlyMessage =
                error instanceof TypeError
                    ? "Không thể kết nối tới máy chủ. Vui lòng kiểm tra mạng và thử lại."
                    : error.message || "Xin lỗi, đã có lỗi xảy ra.";
            addMessageToChat("bot", friendlyMessage);

            // Mở khóa UI do lỗi
            userInput.disabled = false;
            sendBtn.disabled = false;
        }
    }
}

// --- HÀM LOAD LỊCH SỬ CHAT ---
function loadChatHistory(sessionId) {
    // 1. Hủy ngay lập tức API đang gọi dở dang
    if (currentAbortController) {
        currentAbortController.abort();
        currentAbortController = null;
    }

    // 2. ÉP BUỘC HỦY hiệu ứng gõ chữ ngầm (Tránh Memory Leak & giật UI)
    if (currentTypingTimeout) {
        clearTimeout(currentTypingTimeout);
        currentTypingTimeout = null;
    }

    // 3. ÉP BUỘC TẮT thanh "AI đang suy nghĩ"
    if (typeof hideThinkingIndicator === "function") hideThinkingIndicator();
    document
        .querySelectorAll(".typing-indicator, #thinking-indicator")
        .forEach((el) => el.remove());

    // 4. ÉP BUỘC MỞ KHÓA ô chat và nút Gửi
    userInput.disabled = false;
    sendBtn.disabled = false;
    newChatBtn.disabled = false;
    newChatBtn.classList.remove("opacity-50", "pointer-events-none");

    // 5. Nếu người dùng đang nhắn dở đoạn chat hiện tại mà chưa lưu, thì lưu tạm vào UI
    if (
        currentSessionID !== sessionId &&
        sessions[currentSessionID] &&
        sessions[currentSessionID].messages.length > 0
    ) {
        addSessionToHistoryUI(
            currentSessionID,
            sessions[currentSessionID].title,
        );
    }

    // 6. Chuyển đổi ID và Title
    currentSessionID = sessionId;
    currentTitle = sessions[sessionId].title;
    isFirstMessage = false;

    // 7. Highlight nút active ở Sidebar
    document
        .querySelectorAll(".history-item")
        .forEach((b) =>
            b.classList.remove(
                "bg-gray-200",
                "dark:bg-gray-700/50",
                "ring-1",
                "ring-gray-300",
                "dark:ring-gray-600",
                "font-medium",
            ),
        );
    const activeBtn = document.getElementById(`hist-${sessionId}`);
    if (activeBtn) {
        activeBtn.classList.add(
            "bg-gray-200",
            "dark:bg-gray-700/50",
            "ring-1",
            "ring-gray-300",
            "dark:ring-gray-600",
            "font-medium",
        );
    }

    // 8. Xóa khung chat cũ và vẽ lại toàn bộ tin nhắn (không hiệu ứng gõ máy)
    chatMessages.innerHTML = "";
    sessions[sessionId].messages.forEach((msg) => {
        addMessageToChat(msg.sender, msg.text, false);
    });

    // Đẩy thanh cuộn xuống cuối
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// --- HÀM GẮN NÚT LỊCH SỬ LÊN SIDEBAR ---
function addSessionToHistoryUI(id, title) {
    if (document.getElementById(`hist-${id}`)) {
        // Cập nhật lại title nếu nút đã tồn tại
        const existingBtn = document.getElementById(`hist-${id}`);
        if (existingBtn.querySelector(".hist-title")) {
            existingBtn.querySelector(".hist-title").textContent = title;
        }
        return;
    }

    const btn = document.createElement("button");
    btn.id = `hist-${id}`;
    btn.className =
        "history-item w-full text-left px-3 py-2 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700/50 truncate transition-all duration-200 flex items-center gap-2";

    btn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
        <span class="hist-title truncate">${title}</span>
    `;

    btn.addEventListener("click", () => {
        loadChatHistory(id);
    });

    historyList.prepend(btn);

    if (id === currentSessionID) {
        document
            .querySelectorAll(".history-item")
            .forEach((b) =>
                b.classList.remove(
                    "bg-gray-200",
                    "dark:bg-gray-700/50",
                    "ring-1",
                    "ring-gray-300",
                    "dark:ring-gray-600",
                    "font-medium",
                ),
            );
        btn.classList.add(
            "bg-gray-200",
            "dark:bg-gray-700/50",
            "ring-1",
            "ring-gray-300",
            "dark:ring-gray-600",
            "font-medium",
        );
    }
}

// --- XỬ LÝ KHI NHẤN NÚT "+ ĐOẠN CHAT MỚI" ---
newChatBtn.addEventListener("click", () => {
    if (
        sessions[currentSessionID] &&
        sessions[currentSessionID].messages.length > 0
    ) {
        addSessionToHistoryUI(
            currentSessionID,
            sessions[currentSessionID].title,
        );
    }

    // Reset data
    currentSessionID = generateSessionID();
    currentTitle = "Đoạn chat mới";
    isFirstMessage = true;
    sessions[currentSessionID] = { title: currentTitle, messages: [] };

    // Hủy request cũ, hủy hiệu ứng gõ chữ, reset UI
    if (currentAbortController) {
        currentAbortController.abort();
        currentAbortController = null;
    }
    if (currentTypingTimeout) {
        clearTimeout(currentTypingTimeout);
        currentTypingTimeout = null;
    }

    if (typeof hideThinkingIndicator === "function") hideThinkingIndicator();
    document
        .querySelectorAll(".typing-indicator, #thinking-indicator")
        .forEach((el) => el.remove());

    userInput.disabled = false;
    sendBtn.disabled = false;

    // Reset Giao diện
    chatMessages.innerHTML = "";
    document
        .querySelectorAll(".history-item")
        .forEach((b) =>
            b.classList.remove(
                "bg-gray-200",
                "dark:bg-gray-700/50",
                "ring-1",
                "ring-gray-300",
                "dark:ring-gray-600",
                "font-medium",
            ),
        );

    addMessageToChat(
        "bot",
        "Đã bắt đầu đoạn chat mới. Tôi có thể giúp gì cho bạn?",
    );
});

// --- HÀM RENDER TIN NHẮN ---
function addMessageToChat(sender, message, isTyping = false) {
    const messageElement = document.createElement("div");
    messageElement.classList.add("message", sender, "new-message");

    if (sender === "bot" && isTyping) {
        chatMessages.appendChild(messageElement);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        let i = 0;
        const speed = 8; // ms giữa mỗi lần "nhả" chữ (giảm để nhanh hơn nữa)
        const charsPerTick = 6; // số ký tự nhả ra mỗi lần (tăng để nhanh hơn nữa)
        messageElement.textContent = "";

        function typeWriter() {
            // Kiểm tra xem user có đang ở cuối thanh cuộn không
            const isNearBottom =
                chatMessages.scrollHeight - chatMessages.clientHeight <=
                chatMessages.scrollTop + 10;

            if (i < message.length) {
                messageElement.textContent += message.slice(
                    i,
                    i + charsPerTick,
                );
                i += charsPerTick;
                if (isNearBottom)
                    chatMessages.scrollTop = chatMessages.scrollHeight;

                // Lưu tham chiếu timeout để có thể ngắt nếu người dùng chuyển tab
                currentTypingTimeout = setTimeout(typeWriter, speed);
            } else {
                // Kết thúc gõ phím -> parse Markdown và NHẢ KHÓA
                messageElement.innerHTML = marked.parse(message);
                if (isNearBottom)
                    chatMessages.scrollTop = chatMessages.scrollHeight;

                currentTypingTimeout = null; // Xóa tham chiếu
                userInput.disabled = false;
                sendBtn.disabled = false;
                newChatBtn.disabled = false;
                newChatBtn.classList.remove(
                    "opacity-50",
                    "pointer-events-none",
                );
                userInput.focus();
            }
        }
        typeWriter();
    } else {
        if (sender === "bot") {
            messageElement.innerHTML = marked.parse(message);
        } else {
            messageElement.textContent = message;
        }
        chatMessages.appendChild(messageElement);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
}

// ============================================================
// MODULE MỞ RỘNG: TAB AI THI ĐẤU (EXCEL QA + MCP VERIFICATION)
// Giữ nguyên toàn bộ hàm sendMessage() và session của Tab Gia Sư cũ.
// ============================================================
{
    let activeMode = "tutor"; // "tutor" | "contest"
    const tabTutorBtn = document.getElementById("tab-btn-tutor");
    const tabContestBtn = document.getElementById("tab-btn-contest");
    const contestToolbar = document.getElementById("contest-toolbar");
    const fileSelect = document.getElementById("contest-file-select");
    const queryIdInput = document.getElementById("contest-query-id");
    const modelBadge = document.getElementById("contest-model-badge");
    const tokenBadge = document.getElementById("contest-token-badge");

    const CONTEST_API_BASE =
        window.location.hostname === "localhost" ||
        window.location.hostname === "127.0.0.1"
            ? "http://localhost:3000/api/contest"
            : "/api/contest";

    // Nạp thông tin cấu hình (.env) và danh sách file .xlsx cho Tab Thi Đấu
    async function loadContestConfig() {
        try {
            const res = await fetch(`${CONTEST_API_BASE}/config`);
            if (!res.ok) return;
            const cfg = await res.json();
            modelBadge.textContent = `${cfg.provider.toUpperCase()}: ${cfg.model}`;
            if (Array.isArray(cfg.xlsx_files) && cfg.xlsx_files.length > 0) {
                fileSelect.innerHTML = cfg.xlsx_files
                    .map((f) => `<option value="${f}">${f}</option>`)
                    .join("");
            }
        } catch (e) {
            modelBadge.textContent = "Offline / Chưa kết nối";
        }
    }

    // Chuyển đổi qua lại giữa 2 chế độ
    function switchMode(mode) {
        activeMode = mode;
        const activeClasses = [
            "bg-white",
            "dark:bg-slate-700",
            "text-[#1B1B1E]",
            "dark:text-white",
            "shadow-sm",
        ];
        const inactiveClasses = ["text-gray-500", "dark:text-gray-400"];

        if (mode === "contest") {
            tabContestBtn.classList.add(...activeClasses);
            tabContestBtn.classList.remove(...inactiveClasses);
            tabTutorBtn.classList.remove(...activeClasses);
            tabTutorBtn.classList.add(...inactiveClasses);
            contestToolbar.classList.remove("hidden");
            userInput.placeholder =
                "Nhập câu hỏi truy vấn bảng tính Excel (VD: Who was the second-youngest person...)";
            loadContestConfig();
        } else {
            tabTutorBtn.classList.add(...activeClasses);
            tabTutorBtn.classList.remove(...inactiveClasses);
            tabContestBtn.classList.remove(...activeClasses);
            tabContestBtn.classList.add(...inactiveClasses);
            contestToolbar.classList.add("hidden");
            userInput.placeholder = "Nhập câu hỏi của bạn...";
        }
    }

    tabTutorBtn?.addEventListener("click", () => switchMode("tutor"));
    tabContestBtn?.addEventListener("click", () => switchMode("contest"));

    // Chặn sự kiện gửi tin nhắn khi đang ở Tab Thi Đấu để gọi sang Pipeline MCP
    sendBtn.addEventListener(
        "click",
        (e) => {
            if (activeMode === "contest") {
                e.stopImmediatePropagation();
                sendContestMessage();
            }
        },
        true, // Sử dụng capture phase để ưu tiên điều hướng trước hàm sendMessage cũ
    );

    userInput.addEventListener(
        "keydown",
        (e) => {
            if (activeMode === "contest" && e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                e.stopImmediatePropagation();
                sendContestMessage();
            }
        },
        true,
    );

    async function sendContestMessage() {
        const queryText = userInput.value.trim();
        if (!queryText) return;

        const selectedFile = fileSelect.value || "p4_t01.xlsx";
        const queryId = queryIdInput.value.trim() || "p4_q001";

        // Hiển thị câu hỏi của người dùng
        addMessageToChat("user", `[${selectedFile} | ${queryId}] ${queryText}`);
        userInput.value = "";
        autoResizeTextarea();

        userInput.disabled = true;
        sendBtn.disabled = true;
        if (window.toggleAIWaitingState) window.toggleAIWaitingState(true);

        try {
            const res = await fetch(`${CONTEST_API_BASE}/chat`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    message: queryText,
                    file_name: selectedFile,
                    query_id: queryId,
                }),
            });
            const data = await res.json();
            if (!res.ok)
                throw new Error(data.error || "Lỗi xử lý câu hỏi thi đấu.");

            // Cập nhật đồng hồ đo Token & Chi phí USD
            const usage = data.token_usage || {};
            tokenBadge.textContent = `${usage.total_tokens || 0} tok • $${(usage.cost_usd || 0).toFixed(5)} / $0.10`;

            // Render kết quả tối giản: Bước suy nghĩ (Collapsible) + Câu trả lời tự nhiên + Khối CSV chuẩn
            const stepsHtml = (data.thinking_steps || [])
                .map(
                    (s) =>
                        `<li class="text-xs text-gray-500 dark:text-gray-400 py-0.5 font-mono">${s}</li>`,
                )
                .join("");

            const formattedReply = `
<details class="mb-3 rounded-xl bg-gray-100/80 dark:bg-slate-800/70 px-3.5 py-2 text-xs cursor-pointer" open>
    <summary class="font-semibold text-[#38BDF8] select-none">
        ⚡ Tiến trình MCP & Kiểm định A/B (${data.elapsed_seconds}s)
    </summary>
    <ul class="mt-2 space-y-1 list-disc pl-4">${stepsHtml}</ul>
</details>
<p class="mb-2">${data.natural_reply}</p>
<pre><code>${data.csv_block}</code></pre>
            `.trim();

            addMessageToChat("bot", formattedReply, false);
        } catch (err) {
            addMessageToChat("bot", `❌ **Lỗi:** ${err.message}`, false);
        } finally {
            userInput.disabled = false;
            sendBtn.disabled = false;
            if (window.toggleAIWaitingState) window.toggleAIWaitingState(false);
        }
    }
}
