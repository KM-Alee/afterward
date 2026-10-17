/* Voice call room. Audio goes browser <-> OpenAI over WebRTC (ephemeral key minted by our
   server). Our server keeps the tools, the transcript record, the family approval and the
   approved-sentence playback. A websocket brings server state (transcript lines, offer,
   approval) back to this page. The speech check also runs here on the agent transcript; it
   reduces risk and is not a guarantee. A browser call is not a phone call. */
(function () {
  "use strict";
  var root = document.querySelector("[data-call]");
  if (!root || !window.WebSocket || root.getAttribute("data-status") !== "live") return;
  var token = root.getAttribute("data-token");
  var CALLS_URL = "https://api.openai.com/v1/realtime/calls";
  var STOPPED_MSG = "The speech check stopped a possible agreement. Nothing was accepted.";

  var socket = null, ended = false, retry = 0, mode = root.getAttribute("data-mode");
  var pc = null, dc = null, micStream = null, micTrack = null, sender = null, remoteAudio = null;
  var micAnalyser = null, remoteAnalyser = null, audioCtx = null, connecting = null;
  var agentBusy = false, userTalking = false, responseActive = false, playingApproved = false;
  var live = { agent: null, rep: null };
  var pending = { agent: [], rep: [] };
  var items = {}; // agent item id -> { text, tripped, posted }
  var calls = {}; // call ids already handled
  var queued = [], typedN = 0;
  var diagState = { connected: false, events: 0, last: "", error: "", mic: 0 };

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
  function micOn() { return !!(micTrack && micTrack.enabled); }
  function setLevel(v) { if (orb) orb.style.setProperty("--level", Math.min(1, v).toFixed(3)); }
  function setState(state, label) {
    if (orb) orb.setAttribute("data-state", state);
    if (stateEl && label) stateEl.textContent = label;
  }
  function idle() {
    if (agentBusy) return;
    if (micOn()) setState(userTalking ? "user" : "listening", userTalking ? "You're speaking" : "Listening");
    else setState("idle", mode === "realtime" ? (dc ? "Mic is off" : "Tap to start talking") : "Rehearsal");
  }
  function setCaption(text, who) {
    if (!caption) return;
    caption.textContent = text;
    caption.classList.toggle("is-rep", who === "rep");
    caption.classList.toggle("is-quiet", !who);
  }
  function showDiag() {
    diag.textContent = [
      diagState.connected ? "connected to the model" : "not connected",
      "mic level " + Math.round(diagState.mic * 100) + "%",
      "events " + diagState.events + (diagState.last ? " (last: " + diagState.last + ")" : ""),
      diagState.error ? "error: " + diagState.error : "",
    ].filter(Boolean).join(" · ");
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
    var li = bubble(who, label(turn), turn.text, turn.type === "discarded" ? "bubble--discarded" : "");
    var target = null;
    if (who === "agent" || who === "rep") {
      if (pending[who].length) target = pending[who].shift();
      else if (live[who]) { target = live[who].el; live[who] = null; }
    }
    if (target && target.parentNode) chat.replaceChild(li, target);
    else chat.appendChild(li);
    scrollDown();
  }
  function liveCaption(who, item, delta) {
    if (!chat) return;
    var slot = live[who];
    if (slot && slot.item !== item) {
      slot.el.classList.remove("bubble--live");
      var name = slot.el.querySelector(".bubble__who");
      if (name) name.textContent = who === "agent" ? "Afterward (AI), cut off" : "You";
      pending[who].push(slot.el);
      slot = live[who] = null;
    }
    if (!slot) {
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
  /* ---------- speech check (same rules as app/call/guard.py; not a guarantee) ---------- */
  var COMMIT = [
    /\b(we|i)\s+(accept|agree)\b/i,
    /\b(it'?s|that'?s)\s+a\s+deal\b/i,
    /\bdeal\s*[.!]/i,
    /(^|[.!?]\s+)agreed\b/i,
    /\b(?:we|i)\s+(?:have\s+)?agreed\b/i,
    /\bgo\s+ahead\s+(?:with|and)\b/i,
    /\b(?:yes|yeah|ok(?:ay)?|sure),?\s+go\s+ahead\b/i,
    /\bplease\s+(?:proceed|process)\b/i,
    /\bwe(?:'ll| will)\s+take\s+it\b/i,
  ];
  function commitmentTripped(text) { return COMMIT.some(function (re) { return re.test(text); }); }

  /* ---------- data channel ---------- */
  function send(obj) {
    if (!dc || dc.readyState !== "open") return false;
    dc.send(JSON.stringify(obj));
    return true;
  }
  function silenceAgent() {
    if (responseActive) send({ type: "response.cancel" });
    send({ type: "output_audio_buffer.clear" });
    agentBusy = false;
  }
  function postJson(path, body) {
    return fetch("/api/calls/" + token + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json().catch(function () { return {}; }); });
  }
  function postLine(who, text, itemId, via) {
    return postJson("/transcript", { who: who, text: text, item_id: itemId, via: via || "" }).catch(function () { return {}; });
  }
  function trip(item, st) {
    st.tripped = true;
    silenceAgent();
    if (live.agent && live.agent.item === item) { live.agent.el.remove(); live.agent = null; }
    if (remoteAudio) remoteAudio.muted = true;
    setState("tripped", "Stopped by the speech check");
    say(STOPPED_MSG);
    setCaption(STOPPED_MSG, null);
    if (!st.posted) { st.posted = true; postLine("agent", st.text, item); }
  }
  function handleTool(name, callId, args) {
    if (!callId || calls[callId]) return;
    calls[callId] = true;
    postJson("/tool", { name: name, call_id: callId, arguments: args }).then(function (res) {
      var output = res && res.output ? res.output : (res && res.error ? "Not done: " + res.error : "Not done.");
      send({ type: "conversation.item.create", item: { type: "function_call_output", call_id: callId, output: output } });
      if (!playingApproved) send({ type: "response.create" });
    });
  }
  function onEvent(ev) {
    diagState.events++;
    diagState.last = ev.type;
    switch (ev.type) {
      case "input_audio_buffer.speech_started":
        userTalking = true;
        if (agentBusy || responseActive) silenceAgent();
        setState("user", "You're speaking");
        break;
      case "input_audio_buffer.speech_stopped":
        userTalking = false;
        setState("thinking", "Thinking…");
        break;
      case "conversation.item.input_audio_transcription.delta":
        if (ev.delta) liveCaption("rep", ev.item_id, ev.delta);
        break;
      case "conversation.item.input_audio_transcription.completed":
        if (ev.transcript && ev.transcript.trim()) postLine("rep", ev.transcript.trim(), ev.item_id, "voice");
        break;
      case "response.created":
        responseActive = true;
        if (playingApproved) send({ type: "response.cancel" });
        else if (!agentBusy) setState("thinking", "Thinking…");
        break;
      case "output_audio_buffer.started":
        if (!playingApproved) { agentBusy = true; setState("speaking", "Afterward is speaking"); }
        break;
      case "output_audio_buffer.stopped":
      case "output_audio_buffer.cleared":
        agentBusy = false; setLevel(0); idle();
        break;
      case "response.output_audio_transcript.delta": {
        var st = items[ev.item_id] || (items[ev.item_id] = { text: "", tripped: false, posted: false });
        if (st.tripped || playingApproved) break;
        st.text += ev.delta || "";
        liveCaption("agent", ev.item_id, ev.delta || "");
        if (commitmentTripped(st.text)) trip(ev.item_id, st);
        break;
      }
      case "response.output_audio_transcript.done": {
        var s2 = items[ev.item_id] || (items[ev.item_id] = { text: "", tripped: false, posted: false });
        var full = (ev.transcript || s2.text || "").trim();
        if (!s2.tripped && full && commitmentTripped(full)) { s2.text = full; trip(ev.item_id, s2); }
        else if (!s2.posted && full && !playingApproved) { s2.posted = true; postLine("agent", full, ev.item_id); }
        break;
      }
      case "response.function_call_arguments.done":
        handleTool(ev.name, ev.call_id, ev.arguments);
        break;
      case "response.done": {
        responseActive = false;
        var out = (ev.response && ev.response.output) || [];
        out.forEach(function (it) { if (it.type === "function_call") handleTool(it.name, it.call_id, it.arguments); });
        if (ev.response && ev.response.status === "failed") {
          var d = ev.response.status_details && ev.response.status_details.error;
          diagState.error = (d && (d.message || d.code)) || "response failed";
        }
        if (!agentBusy) idle();
        break;
      }
      case "error":
        diagState.error = (ev.error && (ev.error.message || ev.error.code)) || "unknown error";
        break;
    }
    showDiag();
  }

  /* ---------- WebRTC ---------- */
  function ensureCtx() {
    if (!audioCtx) { var AC = window.AudioContext || window.webkitAudioContext; audioCtx = new AC(); }
    if (audioCtx.state === "suspended") audioCtx.resume();
    return audioCtx;
  }
  function analyserFor(stream) {
    var c = ensureCtx(), a = c.createAnalyser();
    a.fftSize = 512;
    c.createMediaStreamSource(stream).connect(a);
    return a;
  }
  function rms(a) {
    var buf = new Uint8Array(a.fftSize), sum = 0;
    a.getByteTimeDomainData(buf);
    for (var i = 0; i < buf.length; i++) { var v = (buf[i] - 128) / 128; sum += v * v; }
    return Math.sqrt(sum / buf.length);
  }
  function meter() {
    if (ended) return;
    var m = micAnalyser && micOn() ? rms(micAnalyser) : 0;
    var r = remoteAnalyser ? rms(remoteAnalyser) : 0;
    diagState.mic = Math.min(1, m * 4);
    if (r > 0.02 && !playingApproved) {
      if (!agentBusy) { agentBusy = true; setState("speaking", "Afterward is speaking"); }
      setLevel(r * 5);
    } else if (agentBusy && r <= 0.02 && !responseActive) {
      agentBusy = false; idle();
    } else if (!agentBusy) {
      setLevel(m * 6);
    }
    if (Math.random() < 0.1) showDiag();
    window.requestAnimationFrame(meter);
  }
  async function connect() {
    if (pc) return connecting;
    connecting = (async function () {
      say("Connecting to the live model…");
      var res = await fetch("/api/calls/" + token + "/session", { method: "POST" });
      var data = await res.json().catch(function () { return {}; });
      if (!res.ok || !data.client_secret) throw new Error(data.error || "Could not start a voice session.");
      var key = data.client_secret;
      pc = new RTCPeerConnection();
      remoteAudio = document.createElement("audio");
      remoteAudio.autoplay = true;
      remoteAudio.setAttribute("playsinline", "");
      document.body.appendChild(remoteAudio);
      pc.ontrack = function (e) {
        remoteAudio.srcObject = e.streams[0];
        try { remoteAnalyser = analyserFor(e.streams[0]); } catch (err) { /* meter only */ }
      };
      pc.onconnectionstatechange = function () {
        diagState.connected = pc && pc.connectionState === "connected";
        if (pc && (pc.connectionState === "failed" || pc.connectionState === "disconnected") && !ended) {
          diagState.error = "connection " + pc.connectionState;
          say("The voice connection dropped. Press the microphone to reconnect.");
          closePeer();
        }
        showDiag();
      };
      var tx = pc.addTransceiver("audio", { direction: "sendrecv" });
      sender = tx.sender;
      dc = pc.createDataChannel("oai-events");
      dc.onmessage = function (m) { try { onEvent(JSON.parse(m.data)); } catch (e) { /* ignore */ } };
      dc.onopen = function () {
        say(micOn() ? "Listening. Talk over the agent any time; it stops." : "Connected. Start talking or type.");
        queued.splice(0).forEach(function (t) { sendTypedNow(t); });
        idle();
      };
      var offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      var answer = await fetch(CALLS_URL, {
        method: "POST",
        body: offer.sdp,
        headers: { Authorization: "Bearer " + key, "Content-Type": "application/sdp" },
      });
      if (!answer.ok) throw new Error("OpenAI refused the connection (" + answer.status + ").");
      await pc.setRemoteDescription({ type: "answer", sdp: await answer.text() });
      window.requestAnimationFrame(meter);
    })();
    try { await connecting; } catch (e) { closePeer(); throw e; } finally { connecting = null; }
  }
  function closePeer() {
    if (dc) { try { dc.close(); } catch (e) { /* closed */ } dc = null; }
    if (pc) { try { pc.close(); } catch (e) { /* closed */ } pc = null; }
    if (remoteAudio) { remoteAudio.remove(); remoteAudio = null; }
    remoteAnalyser = null; sender = null; agentBusy = false; responseActive = false;
    diagState.connected = false;
    stopMicTrack();
    showDiag();
  }
  function stopMicTrack() {
    if (micStream) micStream.getTracks().forEach(function (t) { t.stop(); });
    micStream = null; micTrack = null; micAnalyser = null;
    setMicButton(false);
  }
  function setMicButton(on) {
    if (micBtn) { micBtn.setAttribute("aria-pressed", String(on)); micBtn.setAttribute("aria-label", on ? "Stop talking" : "Start talking"); }
    if (micLabel) micLabel.textContent = on ? "Stop talking" : "Start talking";
  }
  async function startTalking() {
    try {
      if (!micStream) {
        micStream = await navigator.mediaDevices.getUserMedia({
          audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
        micTrack = micStream.getAudioTracks()[0];
        micAnalyser = analyserFor(micStream);
      }
    } catch (e) {
      say("The microphone is blocked. Allow it in the browser, or type instead.");
      return;
    }
    try { await connect(); } catch (e) { say(e.message); diagState.error = e.message; showDiag(); return; }
    if (sender) await sender.replaceTrack(micTrack);
    micTrack.enabled = true;
    setMicButton(true);
    idle();
    setCaption("Go ahead, you're on. Answer as Northline would.", null);
    say("Listening. Talk over the agent any time; it stops.");
  }
  function muteMic() {
    if (micTrack) micTrack.enabled = false;
    setMicButton(false);
    userTalking = false;
    idle();
    say("Microphone off. The call is still open.");
  }
  if (micBtn) micBtn.addEventListener("click", function () {
    if (micOn()) muteMic(); else startTalking();
  });
  if (padToggle && pad) padToggle.addEventListener("click", function () {
    var open = pad.hidden;
    pad.hidden = !open;
    padToggle.setAttribute("aria-expanded", String(open));
    if (open) { var i = $("typed"); if (i) i.focus(); }
  });

  /* ---------- typed lines ---------- */
  function sendTypedNow(text) {
    if (agentBusy || responseActive) silenceAgent();
    send({ type: "conversation.item.create", item: { type: "message", role: "user", content: [{ type: "input_text", text: text }] } });
    send({ type: "response.create" });
    typedN++;
    postLine("rep", text, "typed-" + Date.now() + "-" + typedN, "typed");
  }
  async function sendTyped(text) {
    if (dc && dc.readyState === "open") { sendTypedNow(text); return; }
    queued.push(text);
    try { await connect(); } catch (e) { queued = []; say(e.message); }
  }

  /* ---------- approved sentence (server-built; the model never says it) ---------- */
  async function playApproved() {
    var res = await postJson("/approved-audio", {});
    if (!res || !res.played) { say("The approved terms changed, so nothing was played."); return; }
    if (!res.audio) { say("The approved sentence is in the transcript. Speech was not available."); return; }
    playingApproved = true;
    silenceAgent();
    if (remoteAudio) remoteAudio.muted = true;
    var clip = new Audio("data:" + (res.mime || "audio/ogg") + ";base64," + res.audio);
    var done = function () { playingApproved = false; if (remoteAudio) remoteAudio.muted = false; idle(); };
    clip.onended = done;
    clip.onerror = done;
    setState("speaking", "Approved wording");
    clip.play().catch(done);
  }

  /* ---------- server state socket ---------- */
  function onFrame(data) {
    switch (data.kind) {
      case "call.ready":
        retry = 0;
        mode = data.mode;
        if (micBtn) micBtn.disabled = data.mode !== "realtime";
        if (!micOn()) say(data.mode === "realtime" ? "Ready. Press Start talking." : "Rehearsal (no model): send a line; a fixed reply comes back as text." + (data.note ? " " + data.note : ""));
        idle();
        break;
      case "turn":
        addTurn(data);
        if (data.type === "guard" && mode !== "realtime") { setState("tripped", "Stopped by the speech check"); }
        break;
      case "state": showState(data); break;
      case "ended":
        ended = true;
        say("The call has ended.");
        setState("idle", "Call ended");
        window.setTimeout(function () { closePeer(); }, 6000); // let the goodbye finish
        break;
      case "missing": case "not_started": ended = true; closePeer(); say("This call link is not open."); break;
    }
  }
  function openSocket() {
    var proto = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(proto + "://" + location.host + "/ws/calls/" + token);
    socket.onmessage = function (msg) {
      if (typeof msg.data !== "string") return;
      try { onFrame(JSON.parse(msg.data)); } catch (e) { /* ignore a bad frame */ }
    };
    socket.onclose = function () {
      socket = null;
      if (ended) return;
      retry = Math.min(retry + 1, 5);
      window.setTimeout(openSocket, 600 * retry);
    };
  }
  function sendJson(obj) {
    if (!socket || socket.readyState !== 1) return false;
    socket.send(JSON.stringify(obj));
    return true;
  }

  function lineSubmit(form, getText, clear) {
    if (!form) return;
    form.addEventListener("submit", function (e) {
      var text = getText();
      if (!text) return;
      if (mode === "realtime") { e.preventDefault(); sendTyped(text); if (clear) clear(); }
      else if (sendJson({ type: "line", text: text })) { e.preventDefault(); if (clear) clear(); }
    });
  }
  var talk = $("talk-form");
  lineSubmit(talk, function () {
    var p = talk && talk.querySelector("input[name=line]:checked");
    return p ? p.value : "";
  });
  var typed = $("typed-form");
  var typedInput = typed ? typed.querySelector("input[name=text]") : null;
  lineSubmit(typed, function () { return typedInput ? typedInput.value.trim() : ""; }, function () { typedInput.value = ""; });
  if (cont) cont.addEventListener("submit", function (e) {
    e.preventDefault();
    cont.hidden = true;
    playApproved();
  });
  window.addEventListener("beforeunload", function () { ended = true; closePeer(); });
  showDiag();
  openSocket();
})();
