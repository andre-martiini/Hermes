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
  const conversationToggle = document.getElementById("conversationToggle");
  const textInput = document.getElementById("textInput");
  const sendButton = document.getElementById("sendButton");
  const canvas = document.getElementById("waveform");
  const ctx = canvas.getContext("2d");

  // Nivel de energia (RMS, escala 0..1 pos-amplificacao) acima do qual um
  // frame e considerado fala. Frames = callbacks do ScriptProcessorNode
  // (~256ms cada, ver PROCESSOR_BUFFER_SIZE/MIC_SAMPLE_RATE).
  const VAD_THRESHOLD = 0.12;
  const VAD_SILENCE_FRAMES_TO_STOP = 3; // ~770ms de silencio para considerar o fim da fala
  const VAD_PREROLL_FRAMES = 2; // ~512ms de audio guardado antes da deteccao, para nao cortar o inicio da fala

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
  // Captura de microfone — dois modos:
  // - manual (push-to-talk): segura o micButton, comportamento original.
  // - conversa automatica: mic fica aberto continuamente, um VAD local
  //   (deteccao de voz por energia) decide quando comecar/terminar de
  //   enviar cada fala, sem precisar segurar botao.
  // ---------------------------------------------------------------------

  let micStream = null;
  let micAudioContext = null;
  let micProcessorNode = null;
  let micSourceNode = null;
  let isRecording = false; // true enquanto o servidor esta recebendo/bufferizando audio
  let conversationMode = false;
  let vadSpeaking = false;
  let vadSilenceFrames = 0;
  let vadPreroll = [];

  async function openMic() {
    if (micStream) return true;
    try {
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
      });
    } catch (err) {
      addBubble("error", `Nao foi possivel acessar o microfone: ${err.message || err}`);
      return false;
    }

    micAudioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: MIC_SAMPLE_RATE });
    micSourceNode = micAudioContext.createMediaStreamSource(micStream);
    micProcessorNode = micAudioContext.createScriptProcessor(PROCESSOR_BUFFER_SIZE, 1, 1);
    micProcessorNode.onaudioprocess = onMicFrame;

    micSourceNode.connect(micProcessorNode);
    // ScriptProcessorNode so dispara onaudioprocess se estiver conectado a um
    // destino; usamos um GainNode mudo para nao ecoar o proprio mic nos alto-falantes.
    micProcessorNode.connect(micGainSinkNode());
    return true;
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

  function closeMic() {
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
  }

  function toInt16(float32) {
    const int16 = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i++) {
      const clamped = Math.max(-1, Math.min(1, float32[i]));
      int16[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
    }
    return int16;
  }

  function sendAudioChunk(int16) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(int16.buffer);
      window.__debug.micChunksSent += 1;
    }
  }

  function onMicFrame(event) {
    const input = event.inputBuffer.getChannelData(0);
    const level = rmsLevel(input);
    currentLevel = Math.max(currentLevel, level);
    const int16 = toInt16(input);

    if (!conversationMode) {
      if (isRecording) sendAudioChunk(int16);
      return;
    }

    // Modo conversa automatica: VAD local decide quando falar comeca/termina.
    if (!vadSpeaking) {
      vadPreroll.push(int16);
      if (vadPreroll.length > VAD_PREROLL_FRAMES) vadPreroll.shift();

      if (level > VAD_THRESHOLD) {
        vadSpeaking = true;
        vadSilenceFrames = 0;
        beginAutoUtterance();
      }
      return;
    }

    sendAudioChunk(int16);
    if (level > VAD_THRESHOLD) {
      vadSilenceFrames = 0;
    } else {
      vadSilenceFrames += 1;
      if (vadSilenceFrames >= VAD_SILENCE_FRAMES_TO_STOP) {
        vadSpeaking = false;
        endAutoUtterance();
      }
    }
  }

  function beginAutoUtterance() {
    // Barge-in: se o Hermes estiver falando, corta na hora.
    stopAssistantPlayback();
    isRecording = true;
    micButton.dataset.recording = "true";
    conversationToggle.dataset.listening = "true";
    sendJson({ type: "mic_start" });
    for (const chunk of vadPreroll) sendAudioChunk(chunk);
    vadPreroll = [];
    statusLine.textContent = "Ouvindo...";
  }

  function endAutoUtterance() {
    isRecording = false;
    micButton.dataset.recording = "false";
    conversationToggle.dataset.listening = "false";
    sendJson({ type: "mic_stop" });
  }

  async function startConversationMode() {
    if (conversationMode) return;
    const ok = await openMic();
    if (!ok) return;
    conversationMode = true;
    vadSpeaking = false;
    vadSilenceFrames = 0;
    vadPreroll = [];
    conversationToggle.dataset.active = "true";
    micButton.dataset.disabled = "true";
    statusLine.textContent = "Modo conversa ativo — pode falar a vontade.";
  }

  function stopConversationMode() {
    if (!conversationMode) return;
    if (vadSpeaking) endAutoUtterance();
    conversationMode = false;
    vadSpeaking = false;
    conversationToggle.dataset.active = "false";
    conversationToggle.dataset.listening = "false";
    micButton.dataset.disabled = "false";
    closeMic();
    statusLine.textContent = "";
  }

  conversationToggle.addEventListener("click", () => {
    if (conversationMode) {
      stopConversationMode();
    } else {
      startConversationMode();
    }
  });

  async function startRecording() {
    if (conversationMode || isRecording) return;
    const ok = await openMic();
    if (!ok) return;
    isRecording = true;
    micButton.dataset.recording = "true";
    sendJson({ type: "mic_start" });
    statusLine.textContent = "Ouvindo...";
  }

  function stopRecording() {
    if (conversationMode || !isRecording) return;
    isRecording = false;
    micButton.dataset.recording = "false";
    closeMic();
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
  let activePlaybackSources = [];

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
    activePlaybackSources.push(source);
    source.addEventListener("ended", () => {
      activePlaybackSources = activePlaybackSources.filter((s) => s !== source);
    });

    const startAt = Math.max(audioCtx.currentTime, nextPlaybackTime);
    source.start(startAt);
    nextPlaybackTime = startAt + buffer.duration;
  }

  // Barge-in: corta imediatamente qualquer audio do assistente em reproducao
  // ou na fila, para o usuario poder interromper falando por cima.
  function stopAssistantPlayback() {
    for (const source of activePlaybackSources) {
      try {
        source.stop();
      } catch (err) {
        // ja pode ter terminado sozinho, ignora
      }
    }
    activePlaybackSources = [];
    if (playbackAudioContext) {
      nextPlaybackTime = playbackAudioContext.currentTime;
    }
  }

  // ---------------------------------------------------------------------
  // Entrada de texto
  // ---------------------------------------------------------------------

  function sendTextMessage() {
    const text = textInput.value.trim();
    if (!text) return;
    stopAssistantPlayback();
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
