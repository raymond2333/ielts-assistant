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

  function speakTextValue(text) {
    if (!text || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const cleanText = text.replace(/\s+/g, " ").trim();
    const maxChunkLength = 180;
    const chunks = cleanText.match(new RegExp(`.{1,${maxChunkLength}}(\\s|$)`, "g")) || [cleanText];
    const voices = window.speechSynthesis.getVoices();
    const preferred = voices.find((v) =>
      /Microsoft Jenny|Microsoft Aria|Google US|Samantha|Alex|Daniel|Karen|Tingting/i.test(v.name)
    ) || voices.find((v) => /^en[-_](US|GB|AU)/i.test(v.lang));
    const speakChunk = (index) => {
      if (index >= chunks.length) return;
      const utterance = new SpeechSynthesisUtterance(chunks[index].trim());
      utterance.lang = "en-US";
      utterance.rate = 0.78;
      utterance.pitch = 1;
      utterance.volume = 1;
      if (preferred) utterance.voice = preferred;
      utterance.onend = () => speakChunk(index + 1);
      window.speechSynthesis.speak(utterance);
    };
    speakChunk(0);
  }

  window.speakText = speakTextValue;

  document.addEventListener("click", (event) => {
    const button = event.target.closest(".speak-btn");
    if (!button) return;
    const directText = button.dataset.speak || "";
    const nearest = button.closest(".result-body, .cue-card-body, details, summary");
    const source = (nearest ? nearest.querySelector(".speak-source") : null) ||
      (button.closest("details") ? button.closest("details").querySelector(".speak-source") : null);
    const text = directText || (source ? source.textContent : "");
    if (!text) return;
    event.preventDefault();
    event.stopPropagation();
    speakTextValue(text);
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
