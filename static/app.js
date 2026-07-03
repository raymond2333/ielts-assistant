document.addEventListener("DOMContentLoaded", () => {
  const shell = document.querySelector(".app-shell");
  const toggle = document.querySelector("[data-sidebar-toggle]");
  const stored = localStorage.getItem("xindaya-sidebar");

  if (shell && stored === "collapsed") {
    shell.classList.add("sidebar-collapsed");
  }

  if (shell && toggle) {
    toggle.addEventListener("click", () => {
      shell.classList.toggle("sidebar-collapsed");
      localStorage.setItem(
        "xindaya-sidebar",
        shell.classList.contains("sidebar-collapsed") ? "collapsed" : "expanded"
      );
    });
  }

  // ---- Loading state: disable submit buttons and show progress on form submit ----
  document.addEventListener("submit", (e) => {
    const form = e.target;
    if (form.tagName !== "FORM") return;
    const btn = form.querySelector('button[type="submit"]');
    if (!btn || btn.disabled) return;
    btn.dataset.originalText = btn.textContent;
    btn.textContent = "正在生成…";
    btn.disabled = true;
    // Insert a progress bar below the button
    let bar = document.createElement("div");
    bar.className = "form-loading-bar";
    bar.innerHTML = '<div class="form-loading-bar-inner"></div>';
    btn.parentNode.insertBefore(bar, btn.nextSibling);
    // Animate indeterminate progress
    let pct = 0;
    const tick = () => {
      pct = Math.min(pct + Math.random() * 12, 95);
      const inner = bar.querySelector(".form-loading-bar-inner");
      if (inner) inner.style.width = pct + "%";
    };
    bar._interval = setInterval(tick, 400);
    tick();
    // If the page navigates away, the bar disappears naturally.
    // If the form submission fails (e.g. validation), restore the button.
    setTimeout(() => {
      if (!btn.disabled) return;
      // Still disabled after 60s — likely stuck, restore
      clearInterval(bar._interval);
      if (bar.parentNode) bar.remove();
      btn.textContent = btn.dataset.originalText || btn.textContent;
      btn.disabled = false;
    }, 60000);
  });

  document.querySelectorAll("[data-tab-group]").forEach((group) => {
    const buttons = group.querySelectorAll("[data-tab-target]");
    const panels = group.querySelectorAll("[data-tab-panel]");
    const syncResults = (target) => {
      document.querySelectorAll("[data-result-for]").forEach((panel) => {
        const resultFor = panel.dataset.resultFor || "";
        panel.style.display = resultFor === target ? "" : "none";
      });
    };

    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        const target = button.dataset.tabTarget;
        buttons.forEach((item) => item.classList.toggle("active", item === button));
        panels.forEach((panel) => {
          panel.classList.toggle("active", panel.dataset.tabPanel === target);
        });
        syncResults(target);
      });
    });

    const active = group.querySelector("[data-tab-target].active");
    if (active) syncResults(active.dataset.tabTarget);
  });

  function loadVoices() {
    if (!window.speechSynthesis) return Promise.resolve([]);
    const voices = window.speechSynthesis.getVoices();
    if (voices.length) return Promise.resolve(voices);
    return new Promise((resolve) => {
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        resolve(window.speechSynthesis.getVoices());
      };
      window.speechSynthesis.onvoiceschanged = finish;
      setTimeout(finish, 700);
    });
  }

  function pickEnglishVoice(voices) {
    const englishVoices = voices.filter((v) => /^en[-_]/i.test(v.lang || ""));
    const preferredNames = [
      /Microsoft Guy/i,
      /Microsoft David/i,
      /Microsoft Mark/i,
      /Google UK English Male/i,
      /Google US English Male/i,
      /Daniel/i,
      /Alex/i,
      /Microsoft Aria/i,
      /Microsoft Jenny/i,
      /Google US English/i,
      /Google UK English/i,
      /Samantha/i,
      /Karen/i,
    ];
    for (const pattern of preferredNames) {
      const match = englishVoices.find((v) => pattern.test(v.name || ""));
      if (match) return match;
    }
    return englishVoices.find((v) => /^en[-_](US|GB|AU)/i.test(v.lang || "")) || englishVoices[0] || null;
  }

  function chunkSpeechText(text) {
    const cleanText = text.replace(/\s+/g, " ").trim();
    if (!cleanText) return [];
    if (cleanText.length <= 900) return [cleanText];
    const sentenceChunks = cleanText.match(/[^.!?。！？]+[.!?。！？]?/g) || [cleanText];
    const chunks = [];
    let current = "";
    sentenceChunks.forEach((sentence) => {
      const trimmed = sentence.trim();
      if (!trimmed) return;
      if ((current + " " + trimmed).trim().length <= 650) {
        current = (current + " " + trimmed).trim();
        return;
      }
      if (current) chunks.push(current);
      current = trimmed;
    });
    if (current) chunks.push(current);
    return chunks;
  }

  function setTtsStatus(button, message, kind = "") {
    if (!button) return;
    let status = button.nextElementSibling && button.nextElementSibling.classList.contains("tts-status")
      ? button.nextElementSibling
      : null;
    if (!status && button.insertAdjacentElement) {
      status = document.createElement("span");
      status.className = "tts-status";
      button.insertAdjacentElement("afterend", status);
    }
    if (!status) return;
    status.textContent = message || "";
    status.dataset.kind = kind;
    button.title = message || button.title || "";
  }

  function shortenTtsError(message) {
    const clean = String(message || "").replace(/\s+/g, " ").trim();
    if (!clean) return "云端 TTS 暂时不可用";
    return clean.length > 96 ? `${clean.slice(0, 96)}...` : clean;
  }

  async function speakCloudTextValue(text, button = null) {
    if (!text) return;
    const cleanText = text.replace(/\s+/g, " ").trim();
    if (!cleanText) return;
    const originalText = button ? button.textContent : "";
    if (button) {
      button.disabled = true;
      button.textContent = "☁️ 云端朗读中...";
      setTtsStatus(button, "正在调用云端 AI 语音", "loading");
    }
    try {
      const response = await fetch("/api/tts", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({text: cleanText})
      });
      if (response.ok && (response.headers.get("content-type") || "").includes("audio/")) {
        window.speechSynthesis.cancel();
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        const provider = response.headers.get("X-TTS-Provider") || "AI";
        const model = response.headers.get("X-TTS-Model") || "";
        const voice = response.headers.get("X-TTS-Voice") || "";
        setTtsStatus(button, `${provider}${model ? ` · ${model}` : ""}${voice ? ` · ${voice}` : ""}`, "ok");
        audio.onended = () => {
          URL.revokeObjectURL(url);
          if (button) {
            button.disabled = false;
            button.textContent = originalText || "☁️ 云端朗读";
          }
        };
        audio.onerror = () => {
          URL.revokeObjectURL(url);
          if (button) {
            button.disabled = false;
            button.textContent = originalText || "☁️ 云端朗读";
            setTtsStatus(button, "音频播放失败，已回退浏览器朗读", "warn");
          }
        };
        await audio.play();
        return;
      }
      let errorMessage = "云端 TTS 没有返回音频";
      try {
        const data = await response.json();
        errorMessage = data.error || errorMessage;
      } catch (parseError) {
        errorMessage = `${errorMessage}（HTTP ${response.status}）`;
      }
      setTtsStatus(button, `${shortenTtsError(errorMessage)}，已回退浏览器朗读`, "warn");
    } catch (error) {
      setTtsStatus(button, `${shortenTtsError(error.message)}，已回退浏览器朗读`, "warn");
    }
    if (button) {
      button.disabled = false;
      button.textContent = originalText || "☁️ 云端朗读";
    }
  }

  async function speakLocalTextValue(text, button = null) {
    if (!text || !window.speechSynthesis) return;
    const cleanText = text.replace(/\s+/g, " ").trim();
    if (!cleanText) return;
    const originalText = button ? button.textContent : "";
    if (button) {
      button.disabled = true;
      button.textContent = "🔊 朗读中...";
      setTtsStatus(button, "正在使用浏览器本地朗读", "loading");
    }
    window.speechSynthesis.cancel();
    const chunks = chunkSpeechText(cleanText);
    if (!chunks.length) {
      if (button) {
        button.disabled = false;
        button.textContent = originalText || "🔊 朗读";
      }
      return;
    }
    const voices = await loadVoices();
    const preferred = pickEnglishVoice(voices);
    const speakChunk = (index) => {
      if (index >= chunks.length) {
        if (button) {
          button.disabled = false;
          button.textContent = originalText || "🔊 朗读";
          setTtsStatus(button, "朗读完成", "ok");
        }
        return;
      }
      const utterance = new SpeechSynthesisUtterance(chunks[index]);
      utterance.lang = preferred ? preferred.lang : "en-US";
      utterance.rate = 0.92;
      utterance.pitch = 1;
      utterance.volume = 1;
      if (preferred) utterance.voice = preferred;
      utterance.onend = () => speakChunk(index + 1);
      window.speechSynthesis.speak(utterance);
    };
    speakChunk(0);
  }

  function getSpeakButtonText(button) {
    const directText = button.dataset.speak || "";
    const nearest = button.closest(".result-body, .cue-card-body, details, summary");
    const source = (nearest ? nearest.querySelector(".speak-source") : null) ||
      (button.closest("details") ? button.closest("details").querySelector(".speak-source") : null);
    return directText || (source ? source.textContent : "");
  }

  function localizeSpeakButtons() {
    document.querySelectorAll(".speak-btn").forEach((button) => {
      if (button.classList.contains("cloud-speak-btn")) return;
      if (button.dataset.localReady === "1") return;
      button.dataset.localReady = "1";
      if (!button.dataset.originalLabel) button.dataset.originalLabel = button.textContent.trim();
      const label = button.textContent.replace(/🔊/g, "").replace(/朗读/g, "").trim();
      button.textContent = label ? `🔊 朗读${label}` : "🔊 朗读";
      button.title = "使用浏览器本地语音，响应更快";
    });
  }

  async function installCloudSpeakButtons() {
    localizeSpeakButtons();
    let status = null;
    try {
      const response = await fetch("/api/tts-status", {headers: {"Accept": "application/json"}});
      if (!response.ok) return;
      status = await response.json();
    } catch (error) {
      return;
    }
    if (!status || !status.enabled) return;
    document.querySelectorAll(".speak-btn").forEach((button) => {
      if (button.nextElementSibling && button.nextElementSibling.classList.contains("cloud-speak-btn")) return;
      const cloudButton = document.createElement("button");
      cloudButton.type = "button";
      cloudButton.className = "speak-btn cloud-speak-btn";
      cloudButton.dataset.cloudReady = "1";
      if (button.dataset.speak) cloudButton.dataset.speak = button.dataset.speak;
      cloudButton.textContent = "☁️ 云端朗读";
      cloudButton.title = `${status.provider_label || "云端 TTS"}${status.model ? ` · ${status.model}` : ""}${status.voice ? ` · ${status.voice}` : ""}`;
      button.insertAdjacentElement("afterend", cloudButton);
    });
  }

  window.speakText = speakLocalTextValue;
  window.speakCloudText = speakCloudTextValue;
  installCloudSpeakButtons();

  document.addEventListener("click", (event) => {
    const button = event.target.closest(".speak-btn, .cloud-speak-btn");
    if (!button) return;
    const text = getSpeakButtonText(button);
    if (!text) return;
    event.preventDefault();
    event.stopPropagation();
    if (button.classList.contains("cloud-speak-btn")) {
      speakCloudTextValue(text, button);
    } else {
      speakLocalTextValue(text, button);
    }
  });

  const focusedFeedback = document.querySelector("[data-feedback-focus='1']");
  if (focusedFeedback) {
    setTimeout(() => {
      let parent = focusedFeedback.parentElement;
      while (parent) {
        if (parent.tagName === "DETAILS") parent.open = true;
        parent = parent.parentElement;
      }
      if (focusedFeedback.tagName === "DETAILS") focusedFeedback.open = true;
      focusedFeedback.scrollIntoView({ behavior: "smooth", block: "center" });
      focusedFeedback.classList.add("feedback-focus-flash");
      setTimeout(() => focusedFeedback.classList.remove("feedback-focus-flash"), 1600);
    }, 120);
  }
});

document.addEventListener("click", function(e) {
  var btn = e.target.closest(".del-recording-btn");
  if (!btn) return;
  e.preventDefault();
  if (!confirm("确定要删除这条录音吗？")) return;
  var ts = btn.dataset.timestamp;
  fetch("/api/recordings/delete", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({timestamp: ts})
  }).then(function(r){ return r.json(); })
    .then(function(d){ if(d.ok || d.error==="recording not found") location.reload(); else alert("删除失败："+(d.error||"")); })
    .catch(function(){ alert("删除请求失败"); });
});
