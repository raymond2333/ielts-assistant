(function () {
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  var hasSR = !!SR;
  var hasRecorder = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
  if (!hasSR && !hasRecorder) return;

  var listening = false;
  var recording = false;
  var recognition = null;
  var currentTarget = null;
  var mediaRecorder = null;
  var audioChunks = [];

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
      recBtn.title = "录音上传评分";
      recBtn.innerHTML = "🎙️";
      recBtn.addEventListener("click", function (e) { e.preventDefault(); toggleRecord(textarea, recBtn); });
      btnBar.appendChild(recBtn);
    }
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
    recognition = new SR();
    recognition.lang = "en-US";
    recognition.interimResults = true;
    recognition.continuous = true;
    recognition.maxAlternatives = 1;
    var retries = 0;

    recognition.onstart = function () {
      listening = true;
      btn.classList.add("listening");
      btn.innerHTML = "🔴";
      btn.title = "正在听…说英语吧";
    };

    recognition.onresult = function (event) {
      var transcript = "";
      for (var i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript + " ";
      }
      if (currentTarget) {
        currentTarget.value = (currentTarget.value + " " + transcript).trim();
        currentTarget.dispatchEvent(new Event("input", { bubbles: true }));
      }
      retries = 0;
    };

    recognition.onerror = function (event) {
      if (event.error === "no-speech" && retries < 3) {
        retries++;
        try { recognition.start(); } catch (e) {}
        return;
      }
      stopSpeech(btn);
    };

    recognition.onend = function () {
      if (listening && retries < 3) {
        try { recognition.start(); } catch (e) { stopSpeech(btn); }
        return;
      }
      stopSpeech(btn);
    };

    recognition.start();
  }

  function stopSpeech(btn) {
    listening = false;
    currentTarget = null;
    if (btn) {
      btn.classList.remove("listening");
      btn.innerHTML = "🎤";
    }
    try { recognition.abort(); } catch (e) {}
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
      mediaRecorder = new MediaRecorder(stream, { mimeType: MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "audio/mp4" });
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
    btn.title = "正在上传录音评分...";
  }

  function uploadAudio(blob, btn) {
    var formData = new FormData();
    formData.append("audio", blob, "recording." + (blob.type.includes("webm") ? "webm" : "m4a"));
    formData.append("user_response", currentTarget ? currentTarget.value : "");

    fetch("/api/speech-score", {
      method: "POST",
      body: formData
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      btn.classList.remove("listening");
      btn.innerHTML = "🎙️";
      btn.title = "录音上传评分";
      if (data.error) {
        alert("评分失败: " + data.error);
        return;
      }
      if (data.transcript && currentTarget) {
        currentTarget.value = (currentTarget.value + " " + data.transcript).trim();
        currentTarget.dispatchEvent(new Event("input", { bubbles: true }));
      }
      if (data.score_box) {
        var box = document.createElement("div");
        box.className = "voice-score-box";
        box.innerHTML = data.score_box;
        if (currentTarget && currentTarget.closest(".voice-input-wrapper")) {
          currentTarget.closest(".voice-input-wrapper").appendChild(box);
          setTimeout(function () { box.remove(); }, 12000);
        }
      }
    })
    .catch(function () {
      btn.classList.remove("listening");
      btn.innerHTML = "🎙️";
      btn.title = "录音上传评分";
      alert("上传失败，请稍后重试。");
    });
  }

  var observer = new MutationObserver(function () {
    document.querySelectorAll("textarea:not(.no-voice)").forEach(createBtn);
  });
  observer.observe(document.body, { childList: true, subtree: true });
  document.querySelectorAll("textarea:not(.no-voice)").forEach(createBtn);
})();
