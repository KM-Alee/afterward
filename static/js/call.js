/* Call room audio. Streams mic PCM16 (24 kHz mono) over the websocket and plays the reply.
   Loaded only on the call page. A browser call is not a phone call. */
(function () {
  "use strict";
  var form = document.getElementById("talk-form");
  if (!form || !window.WebSocket || !navigator.mediaDevices) return;
  var match = /\/api\/calls\/([^/]+)\/turn/.exec(form.getAttribute("action") || "");
  if (!match) return;
  var RATE = 24000;
  var socket = null, ctx = null, stream = null, node = null, playAt = 0, sources = [];

  var row = document.createElement("div");
  row.className = "typed__row";
  var button = document.createElement("button");
  button.type = "button";
  button.className = "btn";
  button.textContent = "Use microphone";
  var status = document.createElement("p");
  status.className = "xsmall muted";
  status.setAttribute("aria-live", "polite");
  status.textContent = "Optional. Streams your voice to this call. Not a phone call.";
  row.appendChild(button);
  row.appendChild(status);
  form.parentNode.insertBefore(row, form.nextSibling);

  function stopPlayback() {
    sources.forEach(function (s) { try { s.stop(); } catch (e) {} });
    sources = [];
    playAt = 0;
  }

  function play(buffer) {
    var pcm = new Int16Array(buffer);
    if (!pcm.length || !ctx) return;
    var audio = ctx.createBuffer(1, pcm.length, RATE);
    var out = audio.getChannelData(0);
    for (var i = 0; i < pcm.length; i++) out[i] = pcm[i] / 32768;
    var src = ctx.createBufferSource();
    src.buffer = audio;
    src.connect(ctx.destination);
    playAt = Math.max(playAt, ctx.currentTime + 0.02);
    src.start(playAt);
    playAt += audio.duration;
    sources.push(src);
    src.onended = function () { sources = sources.filter(function (s) { return s !== src; }); };
  }

  function teardown(message) {
    if (node) { node.disconnect(); node = null; }
    if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; }
    stopPlayback();
    if (socket) { try { socket.close(); } catch (e) {} socket = null; }
    button.textContent = "Use microphone";
    if (message) status.textContent = message;
  }

  function toInt16(float32) {
    var out = new Int16Array(float32.length);
    for (var i = 0; i < float32.length; i++) {
      var v = Math.max(-1, Math.min(1, float32[i]));
      out[i] = v < 0 ? v * 32768 : v * 32767;
    }
    return out.buffer;
  }

  async function begin() {
    var proto = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(proto + "://" + location.host + "/ws/calls/" + match[1]);
    socket.binaryType = "arraybuffer";
    var ready = false;
    socket.onmessage = function (msg) {
      if (typeof msg.data !== "string") { play(msg.data); return; }
      var data = JSON.parse(msg.data);
      if (data.kind === "call.ready") {
        ready = true;
        status.textContent = data.mode === "realtime"
          ? "Live: " + data.label + ". Speak as the Northline representative."
          : "Rehearsal (no model): your voice is relayed, no reply is spoken.";
      } else if (data.kind === "event" && data.event === "audio_interrupted") {
        stopPlayback();
      } else if (data.kind === "event" && data.event === "guardrail_tripped") {
        stopPlayback();
        status.textContent = "The speech check stopped a possible agreement. Nothing was accepted.";
      } else if (data.kind === "ended") {
        teardown("Call ended.");
      } else if (data.kind === "missing") {
        teardown("That call link is not valid.");
      }
    };
    socket.onclose = function () { if (ready) teardown("Connection closed."); };
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } });
    } catch (e) {
      teardown("Microphone not available. You can still type.");
      return;
    }
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)({ sampleRate: RATE });
    if (ctx.state === "suspended") await ctx.resume();
    var source = ctx.createMediaStreamSource(stream);
    node = ctx.createScriptProcessor(2048, 1, 1);
    node.onaudioprocess = function (ev) {
      if (socket && socket.readyState === 1) socket.send(toInt16(ev.inputBuffer.getChannelData(0)));
    };
    source.connect(node);
    node.connect(ctx.destination);
    button.textContent = "Stop microphone";
    status.textContent = "Connecting...";
  }

  button.addEventListener("click", function () {
    if (socket) teardown("Microphone off.");
    else begin();
  });
})();
