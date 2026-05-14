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

  document.querySelectorAll("[data-speak]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const text = button.dataset.speak || "";
      if (!text) return;
      if (!window.speechSynthesis) return;
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text.replace(/\s+/g, " ").trim());
      utterance.lang = "en-US";
      utterance.rate = 0.78;
      utterance.pitch = 1;
      utterance.volume = 1;
      const voices = window.speechSynthesis.getVoices();
      const preferred = voices.find((v) =>
        /Microsoft Jenny|Microsoft Aria|Google US|Samantha|Alex|Daniel|Karen|Tingting/i.test(v.name)
      ) || voices.find((v) => /^en[-_](US|GB|AU)/i.test(v.lang));
      if (preferred) utterance.voice = preferred;
      setTimeout(() => window.speechSynthesis.speak(utterance), 80);
    });
  });
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
