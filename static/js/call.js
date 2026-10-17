/* Voice call room, GPT-Live style. One websocket per call:
   - mic PCM16 24 kHz mono in; agent audio PCM16 out, played gap-free;
   - live captions while either side talks; final lines land in the transcript;
   - barge-in: when you start talking over the agent, its audio stops at once;
   - lines and typing go over the same socket, so the page never reloads mid-call.
   Without the socket the forms still post normally. A browser call is not a phone call. */
(function () {
  "use strict";
  var root = document.querySelector("[data-call]");
  if (!root || !window.WebSocket || root.getAttribute("data-status") !== "live") return;
  var token = root.getAttribute("data-token");
  var RATE = 24000;
  var BARGE_RMS = 0.045;

  var socket = null, ctx = null, stream = null, source = null, node = null, gain = null;
  var playAt = 0, sources = [], ended = false, retry = 0, mode = root.getAttribute("data-mode");
  var agentBusy = false, userTalking = false, loud = 0, interruptedAt = 0;
  var live = { agent: null, rep: null };

  var $ = function (id) { return document.getElementById(id); };
  var micBtn = $("mic"), micLabel = micBtn ? micBtn.querySelector("[data-mic-label]") : null;
  var status = $("call-status"), stateEl = $("agent-state"), caption = $("caption");
  var orb = $("orb"), chat = $("chat"), empty = $("chat-empty"), terms = $("terms"), offer = $("offer");
  var cont = $("continue-form"), pad = $("typepad"), padToggle = $("toggle-type");
  var scroller = chat ? chat.closest(".vc-transcript") : null;

  var diag = document.createElement("p");
  diag.className = "call-diag";
  if (status) status.parentNode.insertBefore(diag, status.nextSibling);

  function say(text) { if (status) status.textContent = text; }
  function micOn() { return !!stream; }
  function setLevel(v) { if (orb) orb.style.setProperty("--level", Math.min(1, v).toFixed(3)); }
  function setState(state, label) {
    if (orb) orb.setAttribute("data-state", state);
    if (stateEl && label) stateEl.textContent = label;
  }
  function idle() {
    if (agentBusy) return;
    if (micOn()) setState(userTalking ? "user" : "listening", userTalking ? "You're speaking" : "Listening");
    else setState("idle", mode === "realtime" ? "Tap to start talking" : "Rehearsal");
  }
  function setCaption(text, who) {
    if (!caption) return;
    caption.textContent = text;
    caption.classList.toggle("is-rep", who === "rep");
    caption.classList.toggle("is-quiet", !who);
  }

  /* ---------- transcript ---------- */
  function label(turn) {
    if (turn.who === "agent") {
      if (turn.type === "template") return "Afterward (AI), approved wording";
      if (turn.via === "realtime_voice") return "Afterward (AI), live realtime model, voice";
      if (turn.via === "realtime") return "Afterward (AI), live realtime model, text";
      if (turn.via === "scripted") return "Afterward (AI), fixed fallback line";
      return "Afterward (AI)";
    }
    if (turn.who === "rep") return turn.via === "typed" ? "You, typed" : turn.via === "voice" ? "You, spoken" : "You";
    return "";
  }
  function bubble(who, name, text, extra) {
    var li = document.createElement("li");
    li.className = "bubble bubble--" + who + (extra ? " " + extra : "");
    if (name) {
      var w = document.createElement("span");
      w.className = "bubble__who";
      w.textContent = name;
      li.appendChild(w);
    }
    var t = document.createElement("span");
    t.className = "bubble__text";
    t.textContent = text;
    li.appendChild(t);
    return li;
  }
  function scrollDown() { if (scroller) scroller.scrollTop = scroller.scrollHeight; }
  function addTurn(turn) {
    if (!chat) return;
    if (empty) { empty.remove(); empty = null; }
    var who = turn.who === "system" ? "system" : turn.who;
    var slot = who === "agent" || who === "rep" ? live[who] : null;
    var li = bubble(who, label(turn), turn.text, turn.type === "discarded" ? "bubble--discarded" : "");
    if (slot && slot.el && slot.el.parentNode) { chat.replaceChild(li, slot.el); live[who] = null; }
    else chat.appendChild(li);
    scrollDown();
  }
  function liveCaption(who, item, delta) {
    if (!chat) return;
    var slot = live[who];
    if (!slot || slot.item !== item) {
      if (empty) { empty.remove(); empty = null; }
      var el = bubble(who, who === "agent" ? "Afterward (AI), speaking…" : "You, speaking…", "", "bubble--live");
      chat.appendChild(el);
      slot = live[who] = { item: item, el: el, text: "" };
    }
    slot.text += delta;
    slot.el.querySelector(".bubble__text").textContent = slot.text;
    setCaption(slot.text, who);
    scrollDown();
  }
  function showState(state) {
    if (cont) cont.hidden = !state.can_continue;
    if (!terms) return;
    terms.innerHTML = "";
    if (offer) offer.hidden = !state.terms;
    if (!state.terms) return;
    var li = document.createElement("li");
    var span = document.createElement("span");
    span.textContent = state.terms.months + " months at $" + state.terms.price + "/month";
    var chip = document.createElement("span");
    var voided = state.approval === "void";
    chip.className = "status status--" + (voided ? "void" : state.approval === "approved" ? "holding" : "review");
    chip.textContent = voided ? "Void: offer changed" : state.approval === "approved" ? "Approved by Sara"
      : state.approval === "pending" ? "Waiting for Sara" : state.approval;
    li.appendChild(span);
    li.appendChild(chip);
    terms.appendChild(li);
  }
  function kb(n) { return n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.round(n / 1024) + " KB"; }
  function showStats(st) {
    var parts = [st.connected ? "model connected" : "model not connected",
      "sent " + kb(st.audio_in_bytes || 0), "received " + (st.audio_out_chunks || 0) + " audio chunks"];
    if (st.last_event) parts.push("last event " + st.last_event);
    if (st.last_error) parts.push("error " + st.last_error);
    diag.textContent = parts.join(" · ");
  }

  /* ---------- audio out ---------- */
  function ensureCtx() {
    if (ctx) return ctx;
    var AC = window.AudioContext || window.webkitAudioContext;
    try { ctx = new AC({ sampleRate: RATE, latencyHint: "interactive" }); } catch (e) { ctx = new AC(); }
    gain = ctx.createGain();
    gain.connect(ctx.destination);
    return ctx;
  }
  function stopPlayback() {
    sources.forEach(function (s) { try { s.stop(); } catch (e) {} });
    sources = [];
    playAt = 0;
    agentBusy = false;
    setLevel(0);
    idle();
  }
  function play(buffer) {
    if (Date.now() - interruptedAt < 400) return; // tail of a reply you just talked over
    var pcm = new Int16Array(buffer);
    if (!pcm.length) return;
    var c = ensureCtx();
    var audio = c.createBuffer(1, pcm.length, RATE);
    var out = audio.getChannelData(0), sum = 0;
    for (var i = 0; i < pcm.length; i++) { out[i] = pcm[i] / 32768; sum += out[i] * out[i]; }
    var level = Math.sqrt(sum / pcm.length) * 4;
    var src = c.createBufferSource();
    src.buffer = audio;
    src.connect(gain);
    playAt = Math.max(playAt, c.currentTime + 0.05);
    var startAt = playAt;
    src.start(startAt);
    playAt += audio.duration;
    sources.push(src);
    agentBusy = true;
    setState("speaking", "Afterward is speaking");
    window.setTimeout(function () { if (agentBusy) setLevel(level); }, Math.max(0, (startAt - c.currentTime) * 1000));
    src.onended = function () {
      sources = sources.filter(function (s) { return s !== src; });
      if (!sources.length) { agentBusy = false; setLevel(0); idle(); }
    };
  }

  /* ---------- audio in ---------- */
  function toPcm16(f32, fromRate) {
    var ratio = fromRate / RATE, length = Math.floor(f32.length / ratio), out = new Int16Array(length);
    for (var i = 0; i < length; i++) {
      var v = Math.max(-1, Math.min(1, f32[Math.floor(i * ratio)]));
      out[i] = v < 0 ? v * 32768 : v * 32767;
    }
    return out.buffer;
  }
  function onMic(f32, rate) {
    var sum = 0;
    for (var i = 0; i < f32.length; i++) sum += f32[i] * f32[i];
    var rms = Math.sqrt(sum / f32.length);
    if (!agentBusy) setLevel(rms * 6);
    loud = rms > BARGE_RMS ? loud + 1 : 0;
    if (agentBusy && loud >= 2) bargeIn();
    if (socket && socket.readyState === 1) socket.send(toPcm16(f32, rate));
  }
  function bargeIn() {
    interruptedAt = Date.now();
    stopPlayback();
    sendJson({ type: "interrupt" });
    setState("user", "You're speaking");
  }
  async function startMic() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (e) {
      stream = null;
      say("The microphone is blocked. Allow it in the browser, or type instead.");
      return;
    }
    var c = ensureCtx();
    if (c.state === "suspended") await c.resume();
    source = c.createMediaStreamSource(stream);
    node = c.createScriptProcessor(2048, 1, 1);
    node.onaudioprocess = function (ev) { onMic(ev.inputBuffer.getChannelData(0), c.sampleRate); };
    var mute = c.createGain();
    mute.gain.value = 0; // keep the processor running without playing the mic back
    source.connect(node);
    node.connect(mute);
    mute.connect(c.destination);
    if (micBtn) { micBtn.setAttribute("aria-pressed", "true"); micBtn.setAttribute("aria-label", "End talking"); }
    if (micLabel) micLabel.textContent = "Stop talking";
    idle();
    setCaption("Go ahead — you're on. Answer as Northline would.", null);
    say("Listening. Talk over the agent any time; it stops.");
  }
  function stopMic(message) {
    if (node) { node.disconnect(); node = null; }
    if (source) { source.disconnect(); source = null; }
    if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; }
    if (micBtn) { micBtn.setAttribute("aria-pressed", "false"); micBtn.setAttribute("aria-label", "Start talking"); }
    if (micLabel) micLabel.textContent = "Start talking";
    setLevel(0);
    idle();
    if (message) say(message);
  }
  if (micBtn) micBtn.addEventListener("click", function () {
    if (micOn()) stopMic("Microphone off. The call is still open."); else startMic();
  });
  if (padToggle && pad) padToggle.addEventListener("click", function () {
    var open = pad.hidden;
    pad.hidden = !open;
    padToggle.setAttribute("aria-expanded", String(open));
    if (open) { var i = $("typed"); if (i) i.focus(); }
  });

  /* ---------- socket ---------- */
  function onFrame(data) {
    switch (data.kind) {
      case "call.ready":
        retry = 0;
        mode = data.mode;
        if (micBtn) micBtn.disabled = data.mode !== "realtime";
        say(data.mode === "realtime" ? (micOn() ? "Listening." : "Connected to the live model.")
          : "Rehearsal (no model): send a line; a fixed reply comes back as text." + (data.note ? " " + data.note : ""));
        idle();
        break;
      case "turn":
        addTurn(data);
        if (data.who === "rep") { userTalking = false; if (mode === "realtime") setState("thinking", "Thinking…"); }
        if (data.who === "agent" && data.type !== "template") setCaption(data.text, "agent");
        if (data.type === "guard") { stopPlayback(); setState("tripped", "Stopped by the speech check"); }
        break;
      case "caption":
        liveCaption(data.who, data.item, data.delta);
        break;
      case "speech":
        if (data.who === "rep" && data.state === "start") {
          userTalking = true;
          if (agentBusy) { interruptedAt = Date.now(); stopPlayback(); }
          setState("user", "You're speaking");
        } else if (data.who === "rep") {
          userTalking = false;
          setState("thinking", "Thinking…");
        }
        break;
      case "agent":
        if (data.state === "thinking" && !agentBusy) setState("thinking", "Thinking…");
        if (data.state === "done" && !agentBusy) idle();
        break;
      case "state": showState(data); break;
      case "stats": showStats(data); break;
      case "event":
        if (data.event === "audio_interrupted") stopPlayback();
        if (data.event === "guardrail_tripped") { stopPlayback(); say("The speech check stopped a possible agreement. Nothing was accepted."); }
        break;
      case "error": say(data.text); break;
      case "ended": ended = true; stopMic("The call has ended."); setState("idle", "Call ended"); break;
      case "missing": case "not_started": ended = true; stopMic("This call link is not open."); break;
    }
  }
  function connect() {
    var proto = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(proto + "://" + location.host + "/ws/calls/" + token);
    socket.binaryType = "arraybuffer";
    socket.onmessage = function (msg) {
      if (typeof msg.data !== "string") { play(msg.data); return; }
      try { onFrame(JSON.parse(msg.data)); } catch (e) { /* ignore a bad frame */ }
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

  var talk = $("talk-form");
  if (talk) talk.addEventListener("submit", function (e) {
    var picked = talk.querySelector("input[name=line]:checked");
    if (picked && sendJson({ type: "line", text: picked.value })) { e.preventDefault(); if (agentBusy) bargeIn(); }
  });
  var typed = $("typed-form");
  if (typed) typed.addEventListener("submit", function (e) {
    var input = typed.querySelector("input[name=text]"), text = input ? input.value.trim() : "";
    if (text && sendJson({ type: "line", text: text })) { e.preventDefault(); input.value = ""; if (agentBusy) bargeIn(); }
  });
  if (cont) cont.addEventListener("submit", function (e) {
    if (sendJson({ type: "continue" })) { e.preventDefault(); cont.hidden = true; }
  });
  window.addEventListener("beforeunload", function () { ended = true; stopMic(); });
  connect();
})();
