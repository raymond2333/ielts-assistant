(function () {
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  var isEdge = /\bEdg\//.test(navigator.userAgent || "");
  var hasSR = !!SR && !isEdge;
  var hasRecorder = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
  if (!hasSR && !hasRecorder) return;

  var listening = false;
  var recording = false;
  var recognition = null;
  var currentTarget = null;
  var mediaRecorder = null;
  var audioChunks = [];
  var activeSpeechBtn = null;
  var speechManuallyStopped = false;
  var baseSpeechText = "";
  var finalSpeechText = "";
  var restartTimer = null;
  var noResultTimer = null;
  var restartCount = 0;

  function createBtn(textarea) {
    if (textarea.dataset.voiceReady === "1") return;
    textarea.dataset.voiceReady = "1";

    var wrapper = document.createElement("div");
    wrapper.className = "voice-input-wrapper";
    textarea.parentNode.insertBefore(wrapper, textarea);
    wrapper.appendChild(textarea);

    var btnBar = document.createElement("div");
    btnBar.className = "voice-btn-bar";
    wrapper.appendChild(btnBar);

    var status = document.createElement("div");
    status.className = "voice-status";
    status.setAttribute("aria-live", "polite");
    wrapper.appendChild(status);

    if (hasSR) {
      var speakBtn = document.createElement("button");
      speakBtn.type = "button";
      speakBtn.className = "voice-btn";
      speakBtn.title = "语音转文字（说英语）";
      speakBtn.innerHTML = "🎤";
      speakBtn.addEventListener("click", function (e) { e.preventDefault(); toggleSpeech(textarea, speakBtn); });
      btnBar.appendChild(speakBtn);
    }

    if (hasRecorder) {
      var recBtn = document.createElement("button");
      recBtn.type = "button";
      recBtn.className = "voice-btn rec-btn";
      recBtn.title = "录音上传：先本地转文字，再提交评分";
      recBtn.innerHTML = "🎙️";
      recBtn.addEventListener("click", function (e) { e.preventDefault(); toggleRecord(textarea, recBtn); });
      btnBar.appendChild(recBtn);
    }

    restoreVoiceResult(textarea);
  }

  function toggleSpeech(textarea, btn) {
    if (listening && currentTarget === textarea) {
      stopSpeech(btn);
      return;
    }
    if (recording) return;
    if (listening) recognition.abort();
    currentTarget = textarea;
    startSpeech(btn);
  }

  function startSpeech(btn) {
    speechManuallyStopped = false;
    activeSpeechBtn = btn;
    baseSpeechText = currentTarget ? currentTarget.value.trim() : "";
    finalSpeechText = "";
    restartCount = 0;
    setVoiceStatus("正在启动语音识别...");
    recognition = new SR();
    recognition.lang = "en-US";
    recognition.interimResults = true;
    recognition.continuous = true;
    recognition.maxAlternatives = 1;

    recognition.onstart = function () {
      listening = true;
      btn.classList.add("listening");
      btn.innerHTML = "🔴";
      btn.title = "正在听…点击停止";
      setVoiceStatus("正在听，说完后文字会自动出现在输入框。");
      clearTimeout(noResultTimer);
      noResultTimer = setTimeout(function () {
        if (listening && currentTarget && !finalSpeechText && currentTarget.value.trim() === baseSpeechText) {
          setVoiceStatus("还没有识别到文字。如果这里一直没变化，请改用右侧录音按钮上传转写。");
        }
      }, 6000);
    };

    recognition.onresult = function (event) {
      var interimText = "";
      for (var i = event.resultIndex; i < event.results.length; i++) {
        var text = event.results[i][0].transcript.trim();
        if (!text) continue;
        if (event.results[i].isFinal) {
          finalSpeechText = (finalSpeechText + " " + text).trim();
        } else {
          interimText = (interimText + " " + text).trim();
        }
      }
      if (currentTarget) {
        currentTarget.value = [baseSpeechText, finalSpeechText, interimText].filter(Boolean).join(" ").trim();
        currentTarget.dispatchEvent(new Event("input", { bubbles: true }));
        restartCount = 0;
        if (finalSpeechText || interimText) setVoiceStatus("已识别到文字，可继续说或再次点击麦克风停止。");
      }
    };

    recognition.onerror = function (event) {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        stopSpeech(btn);
        alert("无法访问麦克风，请检查浏览器权限设置。");
        return;
      }
      if (event.error === "network") {
        setVoiceStatus("浏览器语音识别服务连接失败，请使用录音上传转写。");
      } else if (event.error === "no-speech") {
        setVoiceStatus("没有检测到清晰语音，请再说一遍或靠近麦克风。");
      } else {
        setVoiceStatus("语音识别中断：" + event.error + "，正在尝试继续。");
      }
      if (listening && !speechManuallyStopped) scheduleSpeechRestart();
    };

    recognition.onend = function () {
      if (listening && !speechManuallyStopped) {
        restartCount += 1;
        if (restartCount >= 3 && currentTarget && !finalSpeechText && currentTarget.value.trim() === baseSpeechText) {
          setVoiceStatus("浏览器语音识别没有返回文字。这通常是浏览器服务或网络限制导致的，请使用右侧录音按钮上传转写。");
        }
        scheduleSpeechRestart();
      }
    };

    try { recognition.start(); } catch (e) { scheduleSpeechRestart(); }
  }

  function scheduleSpeechRestart() {
    clearTimeout(restartTimer);
    restartTimer = setTimeout(function () {
      if (!listening || speechManuallyStopped || !currentTarget || !activeSpeechBtn) return;
      try {
        recognition.start();
      } catch (e) {
        scheduleSpeechRestart();
      }
    }, 350);
  }

  function stopSpeech(btn) {
    speechManuallyStopped = true;
    listening = false;
    clearTimeout(restartTimer);
    clearTimeout(noResultTimer);
    var targetBtn = btn || activeSpeechBtn;
    if (targetBtn) {
      targetBtn.classList.remove("listening");
      targetBtn.innerHTML = "🎤";
      targetBtn.title = "语音转文字（说英语）";
    }
    try { recognition.abort(); } catch (e) {}
    recognition = null;
    setVoiceStatus("");
    activeSpeechBtn = null;
    currentTarget = null;
  }

  function setVoiceStatus(message) {
    var wrapper = currentTarget && currentTarget.closest(".voice-input-wrapper");
    if (!wrapper) return;
    var status = wrapper.querySelector(".voice-status");
    if (!status) return;
    status.textContent = message || "";
    status.style.display = message ? "block" : "none";
  }

  function toggleRecord(textarea, btn) {
    if (recording) {
      stopRecord(btn);
      return;
    }
    if (listening) { recognition.abort(); stopSpeech(null); }
    currentTarget = textarea;
    startRecord(btn);
  }

  function startRecord(btn) {
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      recording = true;
      audioChunks = [];
      var mimeType = "";
      if (window.MediaRecorder && MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
        mimeType = "audio/webm;codecs=opus";
      } else if (window.MediaRecorder && MediaRecorder.isTypeSupported("audio/webm")) {
        mimeType = "audio/webm";
      } else if (window.MediaRecorder && MediaRecorder.isTypeSupported("audio/mp4")) {
        mimeType = "audio/mp4";
      }
      mediaRecorder = mimeType ? new MediaRecorder(stream, { mimeType: mimeType }) : new MediaRecorder(stream);
      mediaRecorder.ondataavailable = function (e) { if (e.data.size > 0) audioChunks.push(e.data); };
      mediaRecorder.onstop = function () {
        stream.getTracks().forEach(function (t) { t.stop(); });
        var blob = new Blob(audioChunks, { type: mediaRecorder.mimeType });
        uploadAudio(blob, btn);
      };
      mediaRecorder.start();
      btn.classList.add("listening");
      btn.innerHTML = "⏺️";
      btn.title = "录音中…点击停止";
    }).catch(function () {
      alert("无法访问麦克风，请检查浏览器权限设置。");
    });
  }

  function stopRecord(btn) {
    if (!recording) return;
    recording = false;
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }
    btn.classList.remove("listening");
    btn.innerHTML = "⏳";
      btn.title = "正在上传录音并转文字...";
  }

  function uploadAudio(blob, btn) {
    var formData = new FormData();
    formData.append("audio", blob, "recording." + (blob.type.includes("webm") ? "webm" : "m4a"));
    formData.append("user_response", currentTarget ? currentTarget.value : "");
    var form = currentTarget ? currentTarget.closest("form") : null;
    if (form) {
      var questionInput = form.querySelector("input[name='question'], textarea[name='question']");
      var targetInput = form.querySelector("input[name='target_score'], select[name='target_score']");
      var sourceModeInput = form.querySelector("input[name='source_mode']");
      var sourceDataInput = form.querySelector("input[name='source_result_data']");
      if (questionInput) formData.append("question", questionInput.value || "");
      if (targetInput) formData.append("target_score", targetInput.value || "6.5");
      if (sourceModeInput) formData.append("source_mode", sourceModeInput.value || "");
      if (sourceDataInput) formData.append("source_result_data", sourceDataInput.value || "");
    }

    fetch("/api/speech-score", {
      method: "POST",
      body: formData
    })
    .then(function (r) {
      return r.text().then(function (text) {
        var data = {};
        try { data = text ? JSON.parse(text) : {}; } catch (e) {
          throw new Error("服务器返回了非 JSON 内容，可能登录已过期或服务异常。");
        }
        if (!r.ok) {
          throw new Error(data.error || ("请求失败：" + r.status));
        }
        return data;
      });
    })
    .then(function (data) {
      btn.classList.remove("listening");
      btn.innerHTML = "🎙️";
      btn.title = "录音上传：先本地转文字，再提交评分";
      if (data.error) {
        alert("评分失败: " + data.error);
        return;
      }
      if (data.transcript && currentTarget) {
        var existingText = currentTarget.value.trim();
        var transcriptText = data.transcript.trim();
        if (!existingText) {
          currentTarget.value = transcriptText;
        } else if (!existingText.includes(transcriptText)) {
          currentTarget.value = (existingText + " " + transcriptText).trim();
        }
        currentTarget.dispatchEvent(new Event("input", { bubbles: true }));
      }
      if (data.score_box) {
        var host = getResultHost(currentTarget);
        var oldBox = host ? host.querySelector(".voice-score-box") : null;
        if (oldBox) oldBox.remove();
        var box = document.createElement("div");
        box.className = "voice-score-box";
        var transcriptHtml = data.transcript
          ? '<details class="result-accordion" open><summary>转写文字</summary><div class="result-body"><p>' + escapeHtml(data.transcript) + '</p></div></details>'
          : "";
        box.innerHTML = transcriptHtml + data.score_box;
        if (host) {
          host.appendChild(box);
          persistVoiceResult(currentTarget, box.innerHTML);
        }
      } else if (data.message) {
        alert(data.message);
      }
    })
    .catch(function (err) {
      btn.classList.remove("listening");
      btn.innerHTML = "🎙️";
      btn.title = "录音上传：先本地转文字，再提交评分";
      alert(err && err.message ? err.message : "上传失败，请稍后重试。");
    });
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function getVoiceResultKey(textarea) {
    if (!textarea) return "";
    var form = textarea.closest("form");
    var questionInput = form ? form.querySelector("input[name='question'], textarea[name='question']") : null;
    var question = questionInput ? questionInput.value : "";
    var name = textarea.name || textarea.placeholder || "";
    return "xindaya-voice-result:" + location.pathname + ":" + name + ":" + question;
  }

  function getResultHost(textarea) {
    if (!textarea) return null;
    var form = textarea.closest("form");
    var key = getVoiceResultKey(textarea);
    if (form) {
      var next = form.nextElementSibling;
      if (next && next.classList && next.classList.contains("voice-result-host")) {
        return next;
      }
      var host = document.createElement("div");
      host.className = "voice-result-host";
      host.dataset.voiceKey = key;
      form.insertAdjacentElement("afterend", host);
      return host;
    }
    return textarea.closest(".voice-input-wrapper");
  }

  function persistVoiceResult(textarea, html) {
    var key = getVoiceResultKey(textarea);
    if (!key || !html) return;
    try { localStorage.setItem(key, html); } catch (e) {}
  }

  function restoreVoiceResult(textarea) {
    if (!textarea || textarea.dataset.voiceResultRestored === "1") return;
    textarea.dataset.voiceResultRestored = "1";
    var key = getVoiceResultKey(textarea);
    if (!key) return;
    var html = "";
    try { html = localStorage.getItem(key) || ""; } catch (e) {}
    if (!html) return;
    var host = getResultHost(textarea);
    if (!host || host.querySelector(".voice-score-box")) return;
    var box = document.createElement("div");
    box.className = "voice-score-box";
    box.innerHTML = html;
    host.appendChild(box);
  }

  var observer = new MutationObserver(function () {
    document.querySelectorAll("textarea:not(.no-voice)").forEach(createBtn);
  });
  observer.observe(document.body, { childList: true, subtree: true });
  document.querySelectorAll("textarea:not(.no-voice)").forEach(createBtn);
})();
