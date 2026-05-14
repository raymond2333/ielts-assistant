(() => {
  let popup = null;
  let lastInfo = null;

  function ensurePopup() {
    if (popup) return popup;
    popup = document.createElement("div");
    popup.className = "word-popup";
    popup.innerHTML = `
      <div class="word-popup-title">选词查询</div>
      <div class="word-popup-body">选择 AI 输出中的英文词语查看释义。</div>
      <div class="word-popup-actions">
        <button type="button" data-action="save">加入生词本</button>
        <button type="button" data-action="close">关闭</button>
      </div>
    `;
    document.body.appendChild(popup);
    popup.querySelector('[data-action="close"]').addEventListener("click", () => popup.classList.remove("show"));
    popup.querySelector('[data-action="save"]').addEventListener("click", saveWord);
    return popup;
  }

  async function lookupWord(word, rect) {
    const box = ensurePopup();
    box.style.left = `${Math.min(rect.left + window.scrollX, window.scrollX + window.innerWidth - 340)}px`;
    box.style.top = `${rect.bottom + window.scrollY + 10}px`;
    box.classList.add("show");
    box.querySelector(".word-popup-title").textContent = word;
    box.querySelector(".word-popup-body").textContent = "查询中...";

    const response = await fetch("/api/word-lookup", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({word})
    });
    const data = await response.json();
    lastInfo = data;
    box.querySelector(".word-popup-body").innerHTML = `
      <p><strong>翻译：</strong>${data.translation || ""}</p>
      <p><strong>常用搭配：</strong>${(data.phrases || []).join(" / ")}</p>
      <p><strong>作文用法：</strong>${data.usage || ""}</p>
    `;
  }

  async function saveWord() {
    if (!lastInfo) return;
    await fetch("/api/wordbook", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        word: lastInfo.word,
        translation: lastInfo.translation,
        usage: lastInfo.usage,
        source: lastInfo.source || "AI输出选词"
      })
    });
    const box = ensurePopup();
    box.querySelector(".word-popup-title").textContent = "已加入生词本";
  }

  document.addEventListener("mouseup", () => {
    const selection = window.getSelection();
    const text = selection.toString().trim();
    if (!text || text.length > 40 || !/[A-Za-z]/.test(text)) return;
    const anchor = selection.anchorNode?.parentElement;
    if (!anchor?.closest(".ai-output")) return;
    const rect = selection.getRangeAt(0).getBoundingClientRect();
    lookupWord(text, rect);
  });
})();
