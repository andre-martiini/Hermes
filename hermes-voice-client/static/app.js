(() => {
  "use strict";

  // Exposto para depuracao manual e para testes automatizados (Playwright).
  window.__debug = { micChunksSent: 0, audioChunksReceived: 0 };

  const MIC_SAMPLE_RATE = 16000;
  const PROCESSOR_BUFFER_SIZE = 4096;
  const WAVEFORM_HISTORY_LEN = 96;
  const LEVEL_DECAY_PER_FRAME = 0.08;

  const chatLog = document.getElementById("chatLog");
  const statusLine = document.getElementById("statusLine");
  const connIndicator = document.getElementById("connIndicator");
  const connLabel = document.getElementById("connLabel");
  const micButton = document.getElementById("micButton");
  const textInput = document.getElementById("textInput");
  const sendButton = document.getElementById("sendButton");
  const canvas = document.getElementById("waveform");
  const ctx = canvas.getContext("2d");

  // ---------------------------------------------------------------------
  // WebSocket
  // ---------------------------------------------------------------------

  let ws = null;
  let reconnectTimer = null;

  function wsUrl() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${location.host}/ws`;
  }

  function setConnState(state, label) {
    connIndicator.dataset.state = state;
    connLabel.textContent = label;
  }

  function connect() {
    setConnState("connecting", "conectando...");
    ws = new WebSocket(wsUrl());
    ws.binaryType = "arraybuffer";

    ws.addEventListener("open", () => {
      setConnState("open", "conectado");
    });

    ws.addEventListener("close", () => {
      setConnState("closed", "desconectado — tentando reconectar...");
      scheduleReconnect();
    });

    ws.addEventListener("error", () => {
      ws.close();
    });

    ws.addEventListener("message", onServerMessage);
  }

  function scheduleReconnect() {
    if (reconnectTimer) return;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, 2000);
  }

  function sendJson(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    }
  }

  function onServerMessage(event) {
    if (typeof event.data === "string") {
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch (err) {
        return;
      }
      handleServerJson(payload);
      return;
    }
    handleServerAudioChunk(event.data);
  }

  function handleServerJson(payload) {
    switch (payload.type) {
      case "status":
        statusLine.textContent = payload.message || "";
        break;
      case "user_transcript":
        addBubble("user", payload.text);
        statusLine.textContent = "";
        break;
      case "assistant_text":
        addBubble("assistant", payload.text);
        break;
      case "assistant_audio_start":
        pendingPlaybackSampleRate = payload.sampleRate || 22050;
        break;
      case "assistant_audio_end":
        statusLine.textContent = "";
        break;
      case "error":
        addBubble("error", payload.message || "Erro desconhecido.");
        statusLine.textContent = "";
        break;
      default:
        break;
    }
  }

  function addBubble(role, text) {
    const el = document.createElement("div");
    el.className = `bubble ${role}`;
    el.textContent = text;
    chatLog.appendChild(el);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  // ---------------------------------------------------------------------
  // Forma de onda (canvas)
  // ---------------------------------------------------------------------

  let currentLevel = 0; // 0..1, atualizado pela captura de mic e pela reproducao de TTS
  const levelHistory = new Array(WAVEFORM_HISTORY_LEN).fill(0);

  function resizeCanvas() {
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.floor(rect.width * devicePixelRatio));
    canvas.height = Math.max(1, Math.floor(rect.height * devicePixelRatio));
  }

  function drawWaveform() {
    levelHistory.shift();
    levelHistory.push(currentLevel);
    currentLevel = Math.max(0, currentLevel - LEVEL_DECAY_PER_FRAME);

    const w = canvas.width;
    const h = canvas.height;
    const mid = h / 2;
    const step = w / (WAVEFORM_HISTORY_LEN - 1);

    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue("--accent") || "#6ea8fe";
    ctx.lineWidth = Math.max(1, 2 * devicePixelRatio);
    ctx.beginPath();

    for (let i = 0; i < WAVEFORM_HISTORY_LEN; i++) {
      const amplitude = levelHistory[i] * mid * 0.9;
      const x = i * step;
      if (i === 0) {
        ctx.moveTo(x, mid - amplitude);
      } else {
        ctx.lineTo(x, mid - amplitude);
      }
    }
    for (let i = WAVEFORM_HISTORY_LEN - 1; i >= 0; i--) {
      const amplitude = levelHistory[i] * mid * 0.9;
      const x = i * step;
      ctx.lineTo(x, mid + amplitude);
    }
    ctx.closePath();
    ctx.fillStyle = ctx.strokeStyle;
    ctx.globalAlpha = 0.35;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.stroke();

    requestAnimationFrame(drawWaveform);
  }

  window.addEventListener("resize", resizeCanvas);
  resizeCanvas();
  requestAnimationFrame(drawWaveform);

  function rmsLevel(float32Array) {
    let sum = 0;
    for (let i = 0; i < float32Array.length; i++) {
      sum += float32Array[i] * float32Array[i];
    }
    const rms = Math.sqrt(sum / float32Array.length);
    // Amplifica um pouco para a fala normal ocupar boa parte do medidor.
    return Math.min(1, rms * 6);
  }

  // ---------------------------------------------------------------------
  // Captura de microfone (push-to-talk)
  // ---------------------------------------------------------------------

  let micStream = null;
  let micAudioContext = null;
  let micProcessorNode = null;
  let micSourceNode = null;
  let isRecording = false;

  async function startRecording() {
    if (isRecording) return;
    try {
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
      });
    } catch (err) {
      addBubble("error", `Nao foi possivel acessar o microfone: ${err.message || err}`);
      return;
    }

    micAudioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: MIC_SAMPLE_RATE });
    micSourceNode = micAudioContext.createMediaStreamSource(micStream);
    micProcessorNode = micAudioContext.createScriptProcessor(PROCESSOR_BUFFER_SIZE, 1, 1);

    micProcessorNode.onaudioprocess = (event) => {
      const input = event.inputBuffer.getChannelData(0);
      currentLevel = Math.max(currentLevel, rmsLevel(input));

      const int16 = new Int16Array(input.length);
      for (let i = 0; i < input.length; i++) {
        const clamped = Math.max(-1, Math.min(1, input[i]));
        int16[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
      }

      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(int16.buffer);
        window.__debug.micChunksSent += 1;
      }
    };

    micSourceNode.connect(micProcessorNode);
    // ScriptProcessorNode so dispara onaudioprocess se estiver conectado a um
    // destino; usamos um GainNode mudo para nao ecoar o proprio mic nos alto-falantes.
    micProcessorNode.connect(micGainSinkNode());

    isRecording = true;
    micButton.dataset.recording = "true";
    sendJson({ type: "mic_start" });
    statusLine.textContent = "Ouvindo...";
  }

  function micGainSinkNode() {
    // Conecta a um GainNode com volume 0 em vez do destination direto, para
    // nao ecoar o proprio microfone nos alto-falantes.
    if (!micGainSinkNode._node) {
      const gain = micAudioContext.createGain();
      gain.gain.value = 0;
      gain.connect(micAudioContext.destination);
      micGainSinkNode._node = gain;
    }
    return micGainSinkNode._node;
  }

  function stopRecording() {
    if (!isRecording) return;
    isRecording = false;
    micButton.dataset.recording = "false";

    if (micProcessorNode) {
      micProcessorNode.disconnect();
      micProcessorNode.onaudioprocess = null;
      micProcessorNode = null;
    }
    if (micSourceNode) {
      micSourceNode.disconnect();
      micSourceNode = null;
    }
    if (micStream) {
      micStream.getTracks().forEach((track) => track.stop());
      micStream = null;
    }
    if (micAudioContext) {
      micAudioContext.close();
      micAudioContext = null;
    }
    micGainSinkNode._node = null;

    sendJson({ type: "mic_stop" });
  }

  micButton.addEventListener("mousedown", startRecording);
  micButton.addEventListener("touchstart", (e) => { e.preventDefault(); startRecording(); });
  ["mouseup", "mouseleave"].forEach((evt) => micButton.addEventListener(evt, stopRecording));
  micButton.addEventListener("touchend", (e) => { e.preventDefault(); stopRecording(); });

  // ---------------------------------------------------------------------
  // Reproducao de audio do assistente (TTS)
  // ---------------------------------------------------------------------

  let playbackAudioContext = null;
  let nextPlaybackTime = 0;
  let pendingPlaybackSampleRate = 22050;

  function getPlaybackContext() {
    if (!playbackAudioContext) {
      playbackAudioContext = new (window.AudioContext || window.webkitAudioContext)();
      nextPlaybackTime = playbackAudioContext.currentTime;
    }
    return playbackAudioContext;
  }

  function handleServerAudioChunk(arrayBuffer) {
    window.__debug.audioChunksReceived += 1;
    const int16 = new Int16Array(arrayBuffer);
    if (int16.length === 0) return;

    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / 0x8000;
    }
    currentLevel = Math.max(currentLevel, rmsLevel(float32));

    const audioCtx = getPlaybackContext();
    const buffer = audioCtx.createBuffer(1, float32.length, pendingPlaybackSampleRate);
    buffer.copyToChannel(float32, 0);

    const source = audioCtx.createBufferSource();
    source.buffer = buffer;
    source.connect(audioCtx.destination);

    const startAt = Math.max(audioCtx.currentTime, nextPlaybackTime);
    source.start(startAt);
    nextPlaybackTime = startAt + buffer.duration;
  }

  // ---------------------------------------------------------------------
  // Entrada de texto
  // ---------------------------------------------------------------------

  function sendTextMessage() {
    const text = textInput.value.trim();
    if (!text) return;
    addBubble("user", text);
    sendJson({ type: "text_message", text });
    textInput.value = "";
  }

  sendButton.addEventListener("click", sendTextMessage);
  textInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      sendTextMessage();
    }
  });

  connect();
})();
