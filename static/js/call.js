/* Call room. One websocket per call: mic PCM16 (24 kHz mono) in, agent audio, transcript
   lines and offer state out. Lines and typing go over the same socket, so the page never
   reloads mid-call. Without the socket the forms still post normally. Not a phone call. */
(function () {
  "use strict";
  var root = document.querySelector("[data-call]");
  if (!root || !window.WebSocket || root.getAttribute("data-status") !== "live") return;
  var token = root.getAttribute("data-token");
  var RATE = 24000;
  var socket = null, ctx = null, stream = null, source = null, node = null;
  var playAt = 0, sources = [], ended = false, retry = 0, mode = root.getAttribute("data-mode");

  var micBtn = document.getElementById("mic");
  var micLabel = micBtn ? micBtn.querySelector("[data-mic-label]") : null;
  var status = document.getElementById("call-status");
  var orb = document.querySelector(".agent-orb");
  var chat = document.getElementById("chat");
  var empty = document.getElementById("chat-empty");
  var terms = document.getElementById("terms");
  var cont = document.getElementById("continue-form");
  var scroller = chat ? chat.closest(".scroll") : null;

  function say(text) { if (status) status.textContent = text; }
  function setOrb(state) { if (orb) orb.setAttribute("data-state", state); }
  function micOn() { return !!stream; }
  function idleOrb() { setOrb(micOn() ? "listening" : "idle"); }

  /* ---------- transcript ---------- */
  function label(turn) {
    if (turn.who === "agent") {
      if (turn.type === "template") return "Afterward (AI), approved wording";
      if (turn.via === "realtime") return "Afterward (AI), live realtime model";
      if (turn.via === "scripted") return "Afterward (AI), fixed fallback line";
      return "Afterward (AI)";
    }
    if (turn.who === "rep") return turn.via === "typed" ? "You, typed" : turn.via === "voice" ? "You, spoken" : "You";
    return "";
  }
  function addTurn(turn) {
    if (!chat) return;
    if (empty) { empty.remove(); empty = null; }
    var li = document.createElement("li");
    var who = turn.who === "system" ? "system" : turn.who;
    li.className = "bubble bubble--" + who + (turn.type === "discarded" ? " bubble--discarded" : "");
    var name = label(turn);
    if (name) {
      var w = document.createElement("span");
      w.className = "bubble__who";
      w.textContent = name;
      li.appendChild(w);
    }
    var t = document.createElement("span");
    t.className = "bubble__text";
    t.textContent = turn.text;
    li.appendChild(t);
    chat.appendChild(li);
    if (scroller) scroller.scrollTop = scroller.scrollHeight;
  }
  function showState(state) {
    if (cont) cont.hidden = !state.can_continue;
    if (!terms) return;
    terms.innerHTML = "";
    if (!state.terms) return;
    var li = document.createElement("li");
    var span = document.createElement("span");
    span.textContent = state.terms.months + " months at $" + state.terms.price + "/month";
    var chip = document.createElement("span");
    var voided = state.approval === "void";
    chip.className = "status status--" + (voided ? "void" : state.approval === "approved" ? "holding" : "review");
    chip.textContent = voided ? "Void: offer changed" : state.approval === "approved" ? "Approved by Sara" : state.approval === "pending" ? "Waiting for Sara" : state.approval;
    li.appendChild(span);
    li.appendChild(chip);
    terms.appendChild(li);
  }

  /* ---------- audio out ---------- */
  function stopPlayback() {
    sources.forEach(function (s) { try { s.stop(); } catch (e) {} });
    sources = [];
    playAt = 0;
    idleOrb();
  }
  function ensureCtx() {
    if (ctx) return ctx;
    var AC = window.AudioContext || window.webkitAudioContext;
    try { ctx = new AC({ sampleRate: RATE }); } catch (e) { ctx = new AC(); }
    return ctx;
  }
  function play(buffer) {
    var pcm = new Int16Array(buffer);
    if (!pcm.length) return;
    var c = ensureCtx();
    var audio = c.createBuffer(1, pcm.length, RATE);
    var out = audio.getChannelData(0);
    for (var i = 0; i < pcm.length; i++) out[i] = pcm[i] / 32768;
    var src = c.createBufferSource();
    src.buffer = audio;
    src.connect(c.destination);
    playAt = Math.max(playAt, c.currentTime + 0.03);
    src.start(playAt);
    playAt += audio.duration;
    sources.push(src);
    setOrb("speaking");
    src.onended = function () {
      sources = sources.filter(function (s) { return s !== src; });
      if (!sources.length) idleOrb();
    };
  }

  /* ---------- audio in ---------- */
  function toPcm16(float32, fromRate) {
    var ratio = fromRate / RATE;
    var length = Math.floor(float32.length / ratio);
    var out = new Int16Array(length);
    for (var i = 0; i < length; i++) {
      var v = Math.max(-1, Math.min(1, float32[Math.floor(i * ratio)]));
      out[i] = v < 0 ? v * 32768 : v * 32767;
    }
    return out.buffer;
  }
  async function startMic() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    } catch (e) {
      stream = null;
      say("The microphone is blocked. Allow it in the browser, or use Quick lines and typing.");
      return;
    }
    var c = ensureCtx();
    if (c.state === "suspended") await c.resume();
    source = c.createMediaStreamSource(stream);
    node = c.createScriptProcessor(4096, 1, 1);
    node.onaudioprocess = function (ev) {
      if (socket && socket.readyState === 1) socket.send(toPcm16(ev.inputBuffer.getChannelData(0), c.sampleRate));
    };
    source.connect(node);
    node.connect(c.destination);
    if (micBtn) micBtn.setAttribute("aria-pressed", "true");
    if (micLabel) micLabel.textContent = "Stop talking";
    setOrb("listening");
    say("Listening. Speak as the Northline representative; the agent answers out loud.");
  }
  function stopMic(message) {
    if (node) { node.disconnect(); node = null; }
    if (source) { source.disconnect(); source = null; }
    if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; }
    if (micBtn) micBtn.setAttribute("aria-pressed", "false");
    if (micLabel) micLabel.textContent = "Start talking";
    idleOrb();
    if (message) say(message);
  }
  if (micBtn) {
    micBtn.addEventListener("click", function () {
      if (micOn()) stopMic("Microphone off. The call is still open.");
      else startMic();
    });
  }

  /* ---------- socket ---------- */
  function connect() {
    var proto = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(proto + "://" + location.host + "/ws/calls/" + token);
    socket.binaryType = "arraybuffer";
    socket.onmessage = function (msg) {
      if (typeof msg.data !== "string") { play(msg.data); return; }
      var data;
      try { data = JSON.parse(msg.data); } catch (e) { return; }
      if (data.kind === "call.ready") {
        retry = 0;
        mode = data.mode;
        if (micBtn) micBtn.disabled = data.mode !== "realtime";
        say(data.mode === "realtime"
          ? (micOn() ? "Listening." : "Connected to the live model. Press Start talking.")
          : "Rehearsal (no model): send a line; a fixed reply comes back as text." + (data.note ? " " + data.note : ""));
      } else if (data.kind === "turn") {
        addTurn(data);
        if (data.who === "rep" && mode === "realtime") setOrb("thinking");
      } else if (data.kind === "state") {
        showState(data);
      } else if (data.kind === "event" && data.event === "audio_interrupted") {
        stopPlayback();
      } else if (data.kind === "event" && data.event === "guardrail_tripped") {
        stopPlayback();
        say("The speech check stopped a possible agreement. Nothing was accepted.");
      } else if (data.kind === "error") {
        say(data.text);
      } else if (data.kind === "ended") {
        ended = true;
        stopMic("The call has ended.");
      } else if (data.kind === "missing" || data.kind === "not_started") {
        ended = true;
        stopMic("This call link is not open.");
      }
    };
    socket.onclose = function () {
      socket = null;
      if (micBtn) micBtn.disabled = true;
      if (ended) return;
      retry = Math.min(retry + 1, 5);
      say("Connection lost. Reconnecting…");
      window.setTimeout(connect, 600 * retry);
    };
  }
  function sendJson(obj) {
    if (!socket || socket.readyState !== 1) return false;
    socket.send(JSON.stringify(obj));
    return true;
  }

  /* Lines, typing and "continue" go over the socket; the forms remain the fallback. */
  var talk = document.getElementById("talk-form");
  if (talk) {
    talk.addEventListener("submit", function (e) {
      var picked = talk.querySelector("input[name=line]:checked");
      if (picked && sendJson({ type: "line", text: picked.value })) e.preventDefault();
    });
  }
  var typed = document.getElementById("typed-form");
  if (typed) {
    typed.addEventListener("submit", function (e) {
      var input = typed.querySelector("input[name=text]");
      var text = input ? input.value.trim() : "";
      if (text && sendJson({ type: "line", text: text })) {
        e.preventDefault();
        input.value = "";
      }
    });
  }
  if (cont) {
    cont.addEventListener("submit", function (e) {
      if (sendJson({ type: "continue" })) { e.preventDefault(); cont.hidden = true; }
    });
  }
  window.addEventListener("beforeunload", function () { ended = true; stopMic(); });
  connect();
})();
