/* ScamSense: Inbox Defender — game engine. Vanilla JS, no dependencies. Authored content lives in levels.js.
 * The player TYPES. Typed text is classified into an INTENT (LLM via /api/probe when available, regex otherwise);
 * every reply from a scammer or a genuine sender is AUTHORED. No timers, no multiple choice. */
(() => {
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const rnd = (a, b) => a + Math.random() * (b - a);

/* ------------------------------------------------------------ persistence (never required) */
const Store = {
  load() { try { return JSON.parse(localStorage.getItem("scamsense_game2") || "{}"); } catch { return {}; } },
  save(o) { try { localStorage.setItem("scamsense_game2", JSON.stringify(o)); } catch { /* ignore */ } },
};
const save = Store.load();
save.stars = save.stars || {};
if (save.sound === undefined) save.sound = true;
if (!save.speed) save.speed = 1;
const SPEEDS = [[0.7, "Chill"], [1, "Normal"], [2, "Fast"]];

/* ------------------------------------------------------------ sound (WebAudio, tiny synth) */
const Sfx = {
  ctx: null,
  tone(f, d = 0.12, type = "sine", v = 0.12, at = 0) {
    if (!save.sound) return;
    try {
      this.ctx = this.ctx || new (window.AudioContext || window.webkitAudioContext)();
      const c = this.ctx, o = c.createOscillator(), g = c.createGain(), t = c.currentTime + at;
      o.type = type; o.frequency.setValueAtTime(f, t);
      g.gain.setValueAtTime(v, t); g.gain.exponentialRampToValueAtTime(0.0001, t + d);
      o.connect(g); g.connect(c.destination); o.start(t); o.stop(t + d + 0.02);
    } catch { /* audio unavailable */ }
  },
  ping() { this.tone(880, .09, "triangle", .13); this.tone(1320, .14, "triangle", .11, .09); },
  tick() { this.tone(520, .05, "square", .05); },
  send() { this.tone(660, .06, "triangle", .08); },
  good() { [523, 659, 784, 1047].forEach((f, i) => this.tone(f, .14, "triangle", .12, i * .07)); },
  clue() { [784, 988, 1319].forEach((f, i) => this.tone(f, .12, "sine", .12, i * .06)); },
  bad() { this.tone(180, .35, "sawtooth", .16); this.tone(120, .4, "sawtooth", .14, .12); },
  stamp() { this.tone(90, .25, "square", .2); this.tone(60, .3, "sine", .25, .05); },
  win() { [523, 659, 784, 1047, 1319, 1568].forEach((f, i) => this.tone(f, .2, "triangle", .13, i * .09)); },
  lose() { [392, 330, 262, 196].forEach((f, i) => this.tone(f, .3, "sawtooth", .12, i * .16)); },
};

/* ------------------------------------------------------------ visual FX */
const fx = $("#fx"), fctx = fx.getContext("2d");
let parts = [], fxRun = false;
function sizeFx() { fx.width = innerWidth; fx.height = innerHeight; }
addEventListener("resize", sizeFx); sizeFx();
function confetti(x, y, n = 40, spread = 1) {
  const cols = ["#ffd23f", "#ff4fa3", "#19d3c5", "#7c4dff", "#2ee6a6", "#ff7043"];
  for (let i = 0; i < n; i++) parts.push({ x, y, vx: rnd(-6, 6) * spread, vy: rnd(-11, -2) * spread, g: .28, s: rnd(5, 10), r: rnd(0, 6), vr: rnd(-.3, .3), c: cols[i % cols.length], life: rnd(60, 110) });
  if (!fxRun) { fxRun = true; requestAnimationFrame(loopFx); }
}
function loopFx() {
  fctx.clearRect(0, 0, fx.width, fx.height);
  parts = parts.filter(p => p.life > 0 && p.y < fx.height + 30);
  for (const p of parts) {
    p.vy += p.g; p.x += p.vx; p.y += p.vy; p.r += p.vr; p.life--;
    fctx.save(); fctx.translate(p.x, p.y); fctx.rotate(p.r); fctx.fillStyle = p.c; fctx.globalAlpha = Math.min(1, p.life / 30);
    fctx.fillRect(-p.s / 2, -p.s / 3, p.s, p.s * .6); fctx.restore();
  }
  if (parts.length) requestAnimationFrame(loopFx); else fxRun = false;
}
function floatText(text, cls, x, y) {
  const d = document.createElement("div"); d.className = "floater " + cls; d.textContent = text;
  d.style.left = x + "px"; d.style.top = y + "px"; $("#floaters").appendChild(d); setTimeout(() => d.remove(), 1500);
}
function flash(kind) { const d = document.createElement("div"); d.className = "flash " + kind; document.body.appendChild(d); setTimeout(() => d.remove(), 650); }
function shake(node) { node.classList.remove("shake"); void node.offsetWidth; node.classList.add("shake"); }
function toast(msg, kind = "info") {
  const box = $("#toasts"); while (box.children.length >= 3) box.firstChild.remove();
  const t = document.createElement("div"); t.className = "toast " + kind; t.textContent = msg; box.appendChild(t);
  setTimeout(() => t.remove(), 4300);
}
const center = n => { const r = n.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; };

/* ------------------------------------------------------------ markup: "text {{red flag|label}} text" */
function parseMarkup(s) {
  const out = []; let plain = "", last = 0, m;
  const re = /\{\{(.+?)(?:\|(.+?))?\}\}/g;
  while ((m = re.exec(s))) {
    if (m.index > last) out.push({ t: s.slice(last, m.index) });
    out.push({ t: m[1], label: m[2] || "Red flag" });
    plain += s.slice(last, m.index) + m[1]; last = re.lastIndex;
  }
  if (last < s.length) out.push({ t: s.slice(last) });
  plain += s.slice(last);
  return { parts: out, plain };
}
function bubbleHTML(msg, chatId, mi) {
  if (msg.from !== "them") return esc(msg.plain);
  let fi = 0;
  return msg.parts.map(p => {
    if (p.label) return `<span class="f" data-key="${chatId}:${mi}:${fi++}" data-label="${esc(p.label)}">${esc(p.t)}</span>`;
    return p.t.split(/(\s+)/).map(w => (/^\s*$/.test(w) ? esc(w) : `<span class="w">${esc(w)}</span>`)).join("");
  }).join("");
}
const fill = (str, vars) => String(str).replace(/\{(\w+)\}/g, (_, k) => (vars[k] ?? ""));

/* ------------------------------------------------------------ game state */
let G = null;
const nameOfTypology = id => (TYPOLOGY_NAMES[id] || id);
function show(screen) { $$(".screen").forEach(s => s.classList.toggle("active", s.id === "screen-" + screen)); }
const spd = () => save.speed;
const alive = c => G && G.alive && !c.halted;

function later(fn, ms) { const id = setTimeout(() => { G && G.timeouts.delete(id); fn(); }, ms); if (G) G.timeouts.add(id); return id; }
function wait(ms) { return new Promise(res => later(res, ms / spd())); }

function collectGos(def) {
  const out = [];
  const scan = v => {
    if (Array.isArray(v)) v.forEach(scan);
    else if (v && typeof v === "object") { if (v.go) out.push(v.go); Object.values(v).forEach(scan); }
  };
  scan(def.script);
  return [...new Set(out)];
}

function newGame(idx) {
  endGame();
  const L = LEVELS[idx];
  G = { idx, L, money: L.savings, lives: 3, score: 0, scans: 3, alive: true, active: null, chats: {}, order: [], found: 0, clues: 0,
        timeouts: new Set(), clock: 9 * 60 + 41, done: false, finished: false, nodes: {}, seq: 0, foundSet: new Set(), facts: {}, contra: new Set(),
        minQ: L.id === 1 ? 1 : (L.id <= 3 ? 2 : 3) };
  for (const def of L.chats) G.chats[def.id] = { def, id: def.id, msgs: [], unread: 0, started: false, halted: false, finished: false,
    verdict: null, typing: false, cancelled: false, found: 0, correct: null, open: null, busy: false, evidence: [], children: collectGos(def) };
}
function endGame() { if (G) { G.alive = false; G.timeouts.forEach(clearTimeout); G.timeouts.clear(); } }

/* ------------------------------------------------------------ HUD */
function hud() {
  $("#hud-emoji").textContent = G.L.emoji; $("#hud-name").textContent = `Case ${G.L.id}: ${G.L.name}`;
  $("#hud-lives").textContent = "❤️".repeat(G.lives) + "🖤".repeat(3 - G.lives);
  $("#hud-score").textContent = G.score; $("#scan-left").textContent = `(${G.scans})`; $("#btn-scan").disabled = G.scans <= 0;
  $("#btn-speed").textContent = SPEEDS.find(s => s[0] === save.speed)?.[1] || "Normal";
  animateMoney();
}
let shownMoney = 0, moneyRaf = 0;
function animateMoney() {
  cancelAnimationFrame(moneyRaf);
  const tick = () => {
    const d = G.money - shownMoney;
    shownMoney = Math.abs(d) < 3 ? G.money : shownMoney + d * 0.15;
    $("#hud-money").textContent = "$" + Math.round(shownMoney).toLocaleString();
    if (shownMoney !== G.money) moneyRaf = requestAnimationFrame(tick);
  };
  tick();
}
function hudPulse(sel, cls) { const n = $(sel).closest(".hud-stat"); n.classList.remove("hit", "gain"); void n.offsetWidth; n.classList.add(cls); }
function addScore(n) {
  G.score = Math.max(0, G.score + n); $("#hud-score").textContent = G.score;
  const [x, y] = center($("#hud-score")); floatText((n > 0 ? "+" : "") + n, n > 0 ? "gold" : "bad", x - 20, y + 20);
  hudPulse("#hud-score", n > 0 ? "gain" : "hit");
}
function changeMoney(d) {
  G.money = Math.max(0, G.money + d); animateMoney();
  const [x, y] = center($("#hud-money")); floatText((d > 0 ? "+$" : "-$") + Math.abs(d).toLocaleString(), d > 0 ? "good" : "bad", x - 30, y + 20);
  hudPulse("#hud-money", d > 0 ? "gain" : "hit");
  if (d < 0) { flash("red"); shake($("#appwin")); Sfx.bad(); }
}
function loseLife() {
  if (G.lives > 0) G.lives--; hud(); hudPulse("#hud-lives", "hit");
  const [x, y] = center($("#hud-lives")); floatText("💔", "bad", x - 10, y + 20);
}
function checkFail() { if (G.alive && !G.done && (G.money <= 0 || G.lives <= 0)) later(() => endLevel(false), 900); }

/* ------------------------------------------------------------ contacts & chat rendering */
function clockStr() { G.clock++; const h = Math.floor(G.clock / 60) % 24, m = G.clock % 60; return `${h}:${String(m).padStart(2, "0")}`; }

function renderContact(chat) {
  let n = G.nodes[chat.id];
  if (!n) {
    n = document.createElement("div"); n.className = "contact"; G.nodes[chat.id] = n; $("#contacts").prepend(n);
    n.addEventListener("click", () => selectChat(chat.id));
  }
  const last = chat.msgs.filter(m => m.from !== "sys").slice(-1)[0];
  const prev = chat.typing ? "typing…" : last ? (last.from === "me" ? "You: " : "") + last.plain : "";
  let side = "";
  if (chat.verdict) side = `<span class="verdict-mark">${chat.correct ? "✅" : "❌"}</span>`;
  else if (chat.unread) side = `<span class="badge-un">${chat.unread}</span>`;
  n.classList.toggle("active", G.active === chat.id);
  n.innerHTML = `<div class="avatar">${chat.def.avatar}</div><div class="c-main"><div class="c-name">${esc(chat.def.name)}</div>
    <div class="c-prev ${chat.typing ? "typing" : ""}">${esc(prev.slice(0, 60))}</div></div><div class="c-side">${side}</div>`;
}

// Automated senders (SMS alerts, system notices) can't answer questions, so you may judge them straight away.
const isAuto = c => c.def.style === "bot" || !!c.def.auto;
function canJudge(chat) { return isAuto(chat) || !!(chat.open && (chat.open.over || chat.open.n >= G.minQ)); }   // humans: no verdict until you have questioned them
function renderHead(chat) {
  const h = $("#chat-head");
  if (!chat) { h.innerHTML = `<div class="empty-head">📨 Waiting for messages…</div>`; return; }
  let btns;
  if (chat.verdict) btns = `<span class="pill ${chat.correct ? "good" : "bad"}" style="margin-left:auto">${chat.correct ? "✅ You got it" : "❌ You missed it"}</span>`;
  else if (!canJudge(chat)) {
    const need = G.minQ - (chat.open ? chat.open.n : 0);
    btns = `<span class="pill lock" style="margin-left:auto" title="Investigate before you accuse">🔒 Ask ${need} more question${need === 1 ? "" : "s"} before you decide</span>`;
  } else btns = `<div class="verdict-btns"><button class="vbtn scam" data-v="scam">🚩 Scam!</button><button class="vbtn real" data-v="real">✅ Real</button></div>`;
  h.innerHTML = `<div class="avatar">${chat.def.avatar}</div><div class="who"><b>${esc(chat.def.name)}</b><small>${esc(chat.def.sub)}</small></div>${btns}`;
  $$(".vbtn", h).forEach(b => b.addEventListener("click", () => verdict(chat, b.dataset.v)));
}

function selectChat(id) {
  G.active = id; const chat = G.chats[id]; chat.unread = 0;
  for (const c of Object.values(G.chats)) if (c.started) renderContact(c);
  renderHead(chat);
  const box = $("#messages"); box.innerHTML = "";
  chat.msgs.forEach((m, i) => box.appendChild(makeBubble(chat, m, i, true)));
  syncTyping(); box.scrollTop = box.scrollHeight;
  $("#casefile").classList.remove("show");
  if (chat.verdict) showCasefile(chat);
  syncComposer();
}

function makeBubble(chat, m, i, instant) {
  if (m.from === "sys") { const d = document.createElement("div"); d.className = "sys"; d.textContent = m.plain; return d; }
  const d = document.createElement("div"); d.className = `bubble ${m.from}` + (instant ? " instant" : "");
  d.innerHTML = bubbleHTML(m, chat.id, i) + `<time>${m.time}</time>`;
  $$(".f", d).forEach(f => {
    if (G.foundSet.has(f.dataset.key)) f.classList.add("found");
    else if (chat.verdict && chat.def.truth === "scam") f.classList.add("missed");
  });
  const labels = $$(".f.found", d).map(f => f.dataset.label);
  if (labels.length) { const wrap = document.createElement("div"); wrap.className = "chip-wrap"; wrap.innerHTML = labels.map(l => `<span class="flag-chip">🚩 ${esc(l)}</span>`).join(""); d.insertBefore(wrap, d.querySelector("time")); }
  return d;
}

function syncTyping() {
  $$(".typing-dots").forEach(n => n.remove());
  const chat = G.chats[G.active];
  if (chat && chat.typing) {
    const d = document.createElement("div"); d.className = "typing-dots"; d.innerHTML = "<i></i><i></i><i></i>";
    $("#messages").appendChild(d); $("#messages").scrollTop = $("#messages").scrollHeight;
  }
}

function addMsg(chat, from, text) {
  const { parts: p, plain } = parseMarkup(text);
  const m = { from, parts: p, plain, time: clockStr(), seq: G.seq++ }; chat.msgs.push(m);
  if (from === "them") Sfx.ping(); else Sfx.send();
  if (G.active === chat.id) {
    $$(".typing-dots").forEach(n => n.remove());
    $(".empty-chat") && $(".empty-chat").remove();
    $("#messages").appendChild(makeBubble(chat, m, chat.msgs.length - 1, false));
    if (chat.typing) syncTyping();
    $("#messages").scrollTop = $("#messages").scrollHeight;
  } else if (from === "them") {
    chat.unread++;
    const n = G.nodes[chat.id]; if (n) { n.classList.remove("ring"); void n.offsetWidth; n.classList.add("ring"); }
  }
  renderContact(chat);
}
function addSys(chat, text) {
  const m = { from: "sys", parts: [], plain: text, time: "" }; chat.msgs.push(m);
  if (G.active === chat.id) $("#messages").appendChild(makeBubble(chat, m, 0, false));
}

/* ------------------------------------------------------------ scripted pitch + the open (typed) conversation */
function startChat(chat) {
  if (!G || !G.alive || chat.started || chat.cancelled) return;
  chat.started = true; G.order.push(chat.id);
  renderContact(chat);
  toast(`📩 New message from ${chat.def.name}`, "info"); Sfx.ping();
  if (!G.active || (G.chats[G.active] && G.chats[G.active].verdict)) selectChat(chat.id);
  runScript(chat);
}

async function typingThen(chat, text, quick = false) {
  chat.typing = true; renderContact(chat); if (G.active === chat.id) syncTyping();
  const plain = parseMarkup(text).plain;
  await wait(quick ? Math.min(1400, 350 + plain.length * 9) : Math.min(2400, 650 + plain.length * 16));
  chat.typing = false;
  if (!alive(chat)) { renderContact(chat); if (G && G.active === chat.id) syncTyping(); return; }
  addMsg(chat, "them", text);
  await wait(350);
}

async function runScript(chat) {
  for (const step of chat.def.script) {
    if (!alive(chat)) return;
    if (typeof step === "string") await typingThen(chat, step);
    else if (step.w) await wait(step.w);
    else if (step.sys) addSys(chat, step.sys);
    else if (step.go) { const c = G.chats[step.go]; if (c && alive(chat)) startChat(c); }
    else if (step.open) await runOpen(chat, step.open);
  }
  chat.finished = true; checkDone();
}

function mergeSpec(chat, spec) {
  const st = STYLES[chat.def.style || "business"] || STYLES.business;
  const strip = o => Object.fromEntries(Object.entries(o || {}).filter(([, v]) => v));
  return { budget: spec.budget || 7, vars: { ...(st.vars || {}), ...(spec.vars || {}) }, replies: { ...(st.replies || {}), ...(spec.replies || {}) },
           tells: strip({ ...(st.tells || {}), ...(spec.tells || {}) }), clears: strip({ ...(st.clears || {}), ...(spec.clears || {}) }),
           loss: spec.loss || {}, events: spec.events || {}, fallback: spec.fallback || st.fallback || ["Please answer my question."], ultimatum: spec.ultimatum || [] };
}

function runOpen(chat, rawSpec) {
  const m = mergeSpec(chat, rawSpec);
  chat.open = { m, left: m.budget, n: 0, over: false, seen: new Set(), sigSeen: new Set(), counts: {}, icount: {}, fcount: {}, tells: new Set(), clears: new Set(), contras: 0 };
  renderHead(chat); syncComposer();
  if (!G.tipShown) { G.tipShown = true; toast("⌨️ TYPE like you would in real life. Ask questions. Limited questions per chat!", "info"); }
  return new Promise(res => { chat.open.end = res; });
}
function endOpen(chat) {
  const o = chat.open; if (!o || o.over) return;
  o.over = true; chat.finished = true; renderHead(chat); syncComposer(); o.end && o.end(); checkDone();
}

/* ---- classification: the REAL LLM (via the local server) understands what you typed; regex is the offline fallback */
let serverLLM = false;
fetch("/api/info").then(r => r.json()).then(j => { serverLLM = !j.demo; }).catch(() => { serverLLM = false; });
function kwIntent(text) { for (const id of INTENT_ORDER) if (INTENTS[id].keys.test(text)) return id; return null; }
async function classify(text) {
  if (serverLLM) {
    try {
      const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), 9000);
      const r = await fetch("/api/probe", { method: "POST", headers: { "Content-Type": "application/json" }, signal: ctl.signal,
        body: JSON.stringify({ text, intents: INTENT_ORDER.map(id => ({ id, desc: INTENTS[id].desc })) }) });
      clearTimeout(t); const j = await r.json();
      if (j && !j.fallback && !j.error) return j.intent && j.intent !== "none" ? j.intent : null;
    } catch { /* fall through to keywords */ }
  }
  return kwIntent(text);
}

/* ---- composer */
function syncComposer() {
  const chat = G && G.chats[G.active], c = $("#composer");
  const on = !!(chat && chat.open && !chat.open.over && !chat.verdict);
  c.classList.toggle("show", on);
  if (!on) return;
  const q = chat.open.left;
  $("#comp-left").textContent = `❓ ${q} question${q === 1 ? "" : "s"} left`;
  $("#typed").disabled = chat.busy; $("#btn-send").disabled = chat.busy;
  $("#typed").placeholder = chat.busy ? "…" : "Type what you'd say: ask a question, or answer them…";
  if (!chat.busy && document.activeElement !== $("#typed")) $("#typed").focus({ preventScroll: true });
}
$("#composer").addEventListener("submit", e => { e.preventDefault(); sendTyped(); });
async function sendTyped() {
  if (!G || !G.alive) return;
  const chat = G.chats[G.active], inp = $("#typed"), text = inp.value.trim();
  if (!chat || !chat.open || chat.open.over || chat.busy || chat.verdict || !text) return;
  inp.value = ""; await handleTyped(chat, text.slice(0, 280));
}

async function handleTyped(chat, text) {
  const o = chat.open; chat.busy = true; o.n++; o.left--;
  addMsg(chat, "me", text); renderHead(chat); syncComposer();
  chat.typing = true; renderContact(chat); if (G.active === chat.id) syncTyping();
  let remote = null;
  if (serverLLM && chat.def.style !== "bot") remote = await askServer(chat, text);   // in-character reply written by the AI
  const intent = remote ? remote.intent : await classify(text);                      // else: classify + authored reply
  chat.typing = false;
  if (!alive(chat)) { chat.busy = false; syncComposer(); return; }
  if (intent) o.icount[intent] = (o.icount[intent] || 0) + 1;
  await respond(chat, intent, remote);
  if (!alive(chat)) { chat.busy = false; return; }
  const ev = o.m.events[o.n];
  if (ev && !o.over) for (const s of ev) { if (typeof s === "string") await typingThen(chat, s); else if (s.go && G.chats[s.go]) startChat(G.chats[s.go]); }
  if (o.left <= 0 && !o.over && alive(chat)) { for (const u of o.m.ultimatum) await typingThen(chat, u); endOpen(chat); }
  chat.busy = false; renderHead(chat); syncComposer();
}

async function askServer(chat, text) {
  try {
    const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), 25000);
    const hist = chat.msgs.filter(m => m.from !== "sys").slice(-11, -1).map(m => ({ from: m.from, text: m.plain }));
    const r = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, signal: ctl.signal,
      body: JSON.stringify({ case: G.L.id, chat: chat.id, history: hist, text, counts: chat.open.icount, factCounts: chat.open.fcount }) });
    clearTimeout(t); const j = await r.json();
    return j && j.reply && !j.fallback ? j : null;
  } catch { return null; }
}

async function respondRemote(chat, intent, r) {
  const o = chat.open, m = o.m;
  await typingThen(chat, r.reply, true);
  if (!alive(chat)) return;
  if (intent && intent.startsWith("comply_") && chat.def.truth === "scam") {      // falling for it costs real savings
    const loss = m.loss[intent] || { money: -1500, life: 1, say: "You fell for it. -$1,500." };
    changeMoney(loss.money); if (loss.life) loseLife(); toast(loss.say, "bad"); Sfx.bad();
    o.m.ultimatum = []; endOpen(chat); checkFail(); return;
  }
  if (r.go && G.chats[r.go]) startChat(G.chats[r.go]);
  if (r.signal && !o.sigSeen.has(r.signal.intent)) {                              // a clue, grounded by server-side code
    o.sigSeen.add(r.signal.intent);
    if (r.signal.kind === "tell") { o.tells.add(r.signal.intent); addFinding(chat, "tell", r.signal.label); }
    else { o.clears.add(r.signal.intent); addFinding(chat, "clear", r.signal.label); }
  } else if (intent && !o.seen.has(intent)) { o.seen.add(intent); addScore(5); }
  if (r.fact) { o.fcount[r.fact.key] = (o.fcount[r.fact.key] || 0) + 1; checkFact(chat, r.fact.key, r.fact.value); }
}

async function respond(chat, intent, remote) {
  if (remote && remote.reply) return respondRemote(chat, intent, remote);
  const o = chat.open, m = o.m, key = intent || "_none";
  // falling for it: agreeing to pay / share / install
  if (intent && intent.startsWith("comply_") && chat.def.truth === "scam") {
    const loss = m.loss[intent] || { money: -1500, life: 1, say: "You fell for it. -$1,500." };
    await typingThen(chat, fill((m.replies[intent] || ["Thank you. Processing now…"])[0], m.vars));
    if (!alive(chat)) return;
    changeMoney(loss.money); if (loss.life) loseLife(); toast(loss.say, "bad"); Sfx.bad();
    await typingThen(chat, "…");
    o.m.ultimatum = []; endOpen(chat); checkFail(); return;
  }
  let list = (intent && m.replies[intent]) || m.replies._all || null;
  if (!list) list = m.fallback;
  const k = o.counts[key] = (o.counts[key] || 0) + 1;
  let item = list === m.fallback ? list[(k - 1) % list.length] : list[Math.min(k - 1, list.length - 1)];
  if (k > 1 && list.length === 1 && intent) item = { m: `I already answered that. ${fill(m.fallback[0], m.vars)}` };
  const reply = typeof item === "string" ? { m: item } : item;
  await typingThen(chat, fill(reply.m, m.vars));
  if (!alive(chat)) return;
  if (reply.go && G.chats[reply.go]) startChat(G.chats[reply.go]);
  if (intent && !o.seen.has(intent)) {
    o.seen.add(intent);
    if (m.tells[intent]) { o.tells.add(intent); addFinding(chat, "tell", m.tells[intent]); }
    else if (m.clears[intent]) { o.clears.add(intent); addFinding(chat, "clear", m.clears[intent]); }
    else addScore(5);
  }
  if (reply.fact) checkFact(chat, reply.fact[0], reply.fact[1]);
}

function addFinding(chat, kind, label) {
  chat.evidence.push({ kind, label }); G.clues++;
  addScore(kind === "contra" ? 40 : 15); Sfx.clue();
  const ico = { tell: "🔎", clear: "✅", contra: "⚡" }[kind], word = { tell: "Warning sign", clear: "Good sign", contra: "Contradiction!" }[kind];
  toast(`${ico} ${word}: ${label}`, kind === "clear" ? "good" : "info");
  const ul = $("#flag-list"); if (ul.querySelector(".muted")) ul.innerHTML = "";
  ul.insertAdjacentHTML("afterbegin", `<li class="k-${kind}"><b>${ico} ${esc(chat.def.name)}</b><br>${esc(label)}</li>`);
  $("#flag-count").textContent = G.found + G.clues;
  const [x, y] = center($("#appwin")); confetti(x, y - 40, kind === "contra" ? 60 : 24, .7);
  if (kind === "contra") { shake($("#appwin")); flash("green"); }
}
function checkFact(chat, k, v) {
  const key = chat.def.group + ":" + k, list = G.facts[key] = G.facts[key] || [];
  const other = list.find(f => f.v !== v);
  list.push({ v, who: chat.def.name });
  if (other && !G.contra.has(key)) {
    G.contra.add(key); chat.open.contras++;
    addFinding(chat, "contra", `${other.who} said "${other.v}" but ${chat.def.name} said "${v}"`);
  }
}

$("#btn-hint").onclick = () => {
  const chat = G && G.chats[G.active]; if (!chat || !chat.open || chat.open.over) return;
  const m = chat.open.m;
  const useful = Object.keys(m.tells).concat(Object.keys(m.clears)).filter(i => !chat.open.seen.has(i) && INTENTS[i] && INTENTS[i].hint);
  addScore(-20);
  const picks = useful.slice(0, 4).map(i => `<li>${esc(INTENTS[i].hint)}</li>`).join("") || "<li>You've probed the main angles here. Decide!</li>";
  modal(`<h2>💡 Detective's hint</h2><p>Think about:</p><ul>${picks}</ul><p style="opacity:.7;font-size:13px">(−20 score. Real organisations welcome checking; scammers resist it.)</p><button class="big-btn small" onclick="document.getElementById('modal').classList.remove('show')">Got it</button>`);
};

/* ------------------------------------------------------------ red flags in message text */
$("#messages").addEventListener("click", e => {
  if (!G || !G.alive) return;
  const t = e.target.closest(".w, .f"); if (!t || !t.closest(".bubble.them")) return;
  const chat = G.chats[G.active]; if (chat.verdict) return;
  if (t.classList.contains("f")) {
    if (t.classList.contains("found")) return;
    G.foundSet.add(t.dataset.key); chat.found++; G.found++;
    t.classList.add("found");
    const b = t.closest(".bubble"); let wrap = $(".chip-wrap", b);
    if (!wrap) { wrap = document.createElement("div"); wrap.className = "chip-wrap"; b.insertBefore(wrap, $("time", b)); }
    wrap.insertAdjacentHTML("beforeend", `<span class="flag-chip">🚩 ${esc(t.dataset.label)}</span>`);
    addScore(10); Sfx.good(); confetti(e.clientX, e.clientY, 22, .6); floatText("🚩 Red flag!", "gold", e.clientX - 30, e.clientY - 30);
    const ul = $("#flag-list"); if (ul.querySelector(".muted")) ul.innerHTML = "";
    ul.insertAdjacentHTML("afterbegin", `<li class="k-flag"><b>🚩 ${esc(chat.def.name)}</b><br>${esc(t.dataset.label)}</li>`);
    $("#flag-count").textContent = G.found + G.clues;
  } else {
    t.classList.remove("wrong"); void t.offsetWidth; t.classList.add("wrong");
    addScore(-2); Sfx.tick(); floatText("meh…", "bad", e.clientX - 10, e.clientY - 20);
  }
});

/* ------------------------------------------------------------ verdicts */
function spawnChildren(chat) {
  // The ring does not stop when you expose one member: scammers use other numbers. The next members contact you anyway,
  // so you must cross-examine every voice. (Optional contacts only appear if you trigger them, e.g. by calling a saved number.)
  const kids = chat.children.map(id => G.chats[id]).filter(k => k && !k.started && !k.def.optional);
  kids.forEach((k, i) => later(() => {
    if (!G || !G.alive || k.started) return;
    toast(`📩 They're not giving up: ${k.def.name} is now texting you`, "info");
    startChat(k);
  }, 2500 / spd() + i * 1500));
}
function cluesOf(chat) { const o = chat.open; return o ? o.tells.size + o.clears.size + o.contras : 0; }

function verdict(chat, v) {
  if (chat.verdict || !G.alive || !canJudge(chat)) return;
  chat.halted = true; chat.typing = false;
  const truth = chat.def.truth === "scam" ? "scam" : "real";
  chat.verdict = v; chat.correct = v === truth;
  const clues = cluesOf(chat);
  const [cx, cy] = center($("#chat-head"));
  if (chat.correct) {
    const base = (clues >= 2 || isAuto(chat)) ? 100 : 40;   // an automated message is judged on its own content
    addScore(base); Sfx.stamp(); setTimeout(() => Sfx.good(), 250);
    stamp(truth === "scam" ? "SCAM BLOCKED" : "VERIFIED REAL", "good"); confetti(cx, cy + 120, 70);
    if (clues >= 1) { const bonus = Math.min(100, 20 * clues); addScore(bonus); toast(`🔎 Detective bonus +${bonus} for ${clues} solid clue${clues === 1 ? "" : "s"}`, "good"); }
    else toast("Right call, but a gut feeling. Asking the right questions makes you sure.", "info");
    if (truth === "scam") spawnChildren(chat);
  } else if (truth === "real") {
    loseLife(); addScore(-50); Sfx.bad(); flash("red"); stamp("THAT WAS REAL!", "badc");
    toast("Oops — you accused someone genuine. Trust −1 💔", "bad"); spawnChildren(chat);
  } else {
    changeMoney(-1000); loseLife(); stamp("IT WAS A SCAM!", "badc");
    toast("You trusted a scammer. −$1,000 and −1 trust", "bad"); spawnChildren(chat);
  }
  syncComposer(); renderHead(chat); renderContact(chat);
  $$("#messages .bubble.them .f:not(.found)").forEach(f => truth === "scam" && f.classList.add("missed"));
  later(() => showCasefile(chat), 1300);
  checkFail(); checkDone();
}

function stamp(text, cls) { const s = $("#stamp"); s.textContent = text; s.className = "stamp " + cls; void s.offsetWidth; s.classList.add("show"); }
function totalFlags(chat) { return chat.msgs.reduce((n, m) => n + m.parts.filter(p => p.label).length, 0); }
function showCasefile(chat) {
  const c = $("#casefile"), truth = chat.def.truth, clues = cluesOf(chat);
  c.innerHTML = `<button class="close">×</button><h4>${truth === "scam" ? "🕵️ Case file: SCAM" : "📘 Case file: genuine"} — ${esc(chat.def.name)}</h4>
    <p>${esc(chat.def.explain)}</p>
    <div class="row"><span class="pill">${esc(nameOfTypology(chat.def.typology))}</span>
    ${truth === "scam" ? `<span class="pill ${chat.found >= totalFlags(chat) ? "good" : ""}">🚩 ${chat.found}/${totalFlags(chat)} red flags</span>` : ""}
    <span class="pill ${clues >= 2 ? "good" : ""}">🔎 ${clues} clue${clues === 1 ? "" : "s"} from questioning</span></div>`;
  c.classList.add("show"); $(".close", c).onclick = () => c.classList.remove("show");
}

/* ------------------------------------------------------------ level lifecycle */
function checkDone() {
  if (!G || !G.alive || G.done) return;
  const ready = Object.values(G.chats).every(c => (c.started && c.verdict) || c.cancelled || (c.def.optional && !c.started));
  if (ready) { G.done = true; later(() => endLevel(true), 1800); }
}

function startLevel(idx) {
  newGame(idx);
  const L = G.L;
  shownMoney = L.savings;
  $("#appwin").className = "appwin " + L.theme;
  $("#app-title").textContent = L.theme === "telegram" ? "Telegram Desktop" : "WhatsApp Web";
  $("#contacts").innerHTML = ""; $("#messages").innerHTML = `<div class="empty-chat"><div>🔔</div><p>Your inbox is quiet…<br>for now.</p></div>`;
  $("#composer").classList.remove("show"); $("#casefile").classList.remove("show"); $("#stamp").className = "stamp";
  $("#mission").textContent = L.mission;
  $("#life-list").innerHTML = L.life.map(x => `<li>${esc(x)}</li>`).join("");
  $("#flag-list").innerHTML = `<li class="muted">Tap suspicious words, and note what your questions reveal…</li>`; $("#flag-count").textContent = "0";
  renderHead(null); hud(); animateMoney();
  show("game");
  const diffTxt = { easy: "EASY", medium: "MEDIUM", hard: "HARD", expert: "EXPERT" }[L.diff] || "";
  modal(`<div class="brief"><div class="brief-em">${L.emoji}</div><h2>Case ${L.id}: ${esc(L.name)} <span class="diff ${L.diff}">${diffTxt}</span></h2>
    <p>${esc(L.briefing)}</p><h3>🧾 Your life (the facts you can check claims against)</h3><ul>${L.life.map(x => `<li>${esc(x)}</li>`).join("")}</ul>
    <p class="brief-goal">🎯 <b>Goal:</b> for each chat decide 🚩 Scam or ✅ Real, <b>without losing your savings or accusing real people</b>. You can't decide until you've asked questions. <b>Type your own.</b></p>
    <button class="big-btn small" id="brief-go">Start the case ▶</button></div>`, true);
  $("#brief-go").onclick = () => {
    $("#modal").classList.remove("show");
    for (const c of Object.values(G.chats)) if (c.def.start != null) later(() => startChat(c), c.def.start / spd());
  };
}

function starsFor(ok) {
  if (!ok) return 0;
  const chats = Object.values(G.chats).filter(c => c.started);
  const wellInvestigated = chats.length > 0 && chats.filter(c => c.verdict && (isAuto(c) || cluesOf(c) >= 2)).length >= Math.ceil(.75 * chats.length);
  if (G.lives === 3 && G.money >= .9 * G.L.savings && wellInvestigated) return 3;   // flawless AND thorough
  if (G.lives >= 2 && G.money >= .5 * G.L.savings) return 2;
  return 1;
}

function endLevel(ok) {
  if (!G || G.finished) return; G.finished = true; G.done = true;
  $("#toasts").innerHTML = ""; $("#modal").classList.remove("show");
  const stars = starsFor(ok);
  const prev = save.stars[G.L.id] || 0; if (stars > prev) save.stars[G.L.id] = stars; Store.save(save);
  const lvl = G.idx, L = G.L, snap = { money: G.money, lives: G.lives, score: G.score, found: G.found, clues: G.clues };
  const chats = Object.values(G.chats).filter(c => c.started);
  endGame(); shownMoney = snap.money;
  $("#result-banner").textContent = ok ? (stars === 3 ? "🏆 CASE CRACKED!" : "CASE CLOSED") : "💥 CASE LOST";
  $("#result-stars").innerHTML = [0, 1, 2].map(i => `<span style="animation-delay:${.4 + i * .35}s;opacity:${i < stars ? 1 : .22}">${i < stars ? "⭐" : "☆"}</span>`).join("");
  $("#result-stats").innerHTML = `<div><small>SAVINGS LEFT</small><b>$${snap.money.toLocaleString()}</b></div><div><small>TRUST</small><b>${"❤️".repeat(snap.lives) || "💔"}</b></div>
    <div><small>SCORE</small><b>${snap.score}</b></div><div><small>CLUES</small><b>🔎 ${snap.clues} · 🚩 ${snap.found}</b></div>`;
  $("#result-debrief").innerHTML = `<h3>🕵️ How the operation worked</h3><p>${esc(L.debrief)}</p>`;
  $("#result-cases").innerHTML = chats.map((c, i) => `<div class="case" style="animation-delay:${i * .08}s"><h4>${c.def.avatar} ${esc(c.def.name)}
    <span class="pill ${c.def.truth === "scam" ? "bad" : "good"}">${c.def.truth === "scam" ? "SCAM" : "REAL"}</span>
    <span class="pill ${c.verdict ? (c.correct ? "good" : "bad") : ""}">${c.verdict ? (c.correct ? "✅ you got it" : "❌ you missed it") : "⏭ not judged"}</span></h4>
    <p>${esc(c.def.explain)}</p><span class="pill">${esc(nameOfTypology(c.def.typology))}</span> <span class="pill">🔎 ${cluesOf(c)} clues</span></div>`).join("");
  $("#res-next").style.display = ok && lvl < LEVELS.length - 1 ? "" : "none";
  $("#res-next").onclick = () => startLevel(lvl + 1); $("#res-retry").onclick = () => startLevel(lvl);
  $("#res-menu").onclick = () => { renderLevels(); show("levels"); };
  show("result");
  if (ok) { Sfx.win(); [0.25, 0.5, 0.75].forEach((f, i) => setTimeout(() => confetti(innerWidth * f, innerHeight * .35, 90, 1.3), i * 350)); }
  else Sfx.lose();
  if (ok && lvl === LEVELS.length - 1) setTimeout(() => toast("🎉 You finished every case. Now go warn someone you love!", "good"), 1500);
}

/* ------------------------------------------------------------ level select */
function unlocked(i) { return i === 0 || (save.stars[LEVELS[i - 1].id] || 0) > 0 || location.hash.includes("unlock"); }
function renderLevels() {
  const g = $("#level-grid"); g.innerHTML = ""; let total = 0;
  const diffName = { easy: "EASY", medium: "MEDIUM", hard: "HARD", expert: "EXPERT" };
  LEVELS.forEach((L, i) => {
    const st = save.stars[L.id] || 0; total += st; const open = unlocked(i);
    const d = document.createElement("div"); d.className = "lvl" + (open ? "" : " locked");
    d.style.setProperty("--a", L.colors[0]); d.style.setProperty("--b", L.colors[1]); d.style.animationDelay = i * .07 + "s";
    d.innerHTML = `<span class="num">${L.id}</span><span class="em">${L.emoji}</span><h3>${esc(L.name)}</h3><p>${esc(L.blurb)}</p>
      <div class="stars">${[0, 1, 2].map(k => k < st ? "⭐" : "☆").join("")}</div><span class="badge">${diffName[L.diff]} · ${L.chats.length} chats</span>`;
    if (open) d.onclick = () => startLevel(i); else d.title = "Crack the previous case to unlock";
    g.appendChild(d);
  });
  $("#total-stars").textContent = `⭐ ${total} / ${LEVELS.length * 3}`;
}

/* ------------------------------------------------------------ ScamSense scanner (real pipeline via the local server) */
async function scan() {
  if (!G || !G.alive || G.scans <= 0) return;
  const cur = G.chats[G.active]; if (!cur) { toast("Open a chat first, then scan it.", "info"); return; }
  const group = Object.values(G.chats).filter(c => c.started && c.def.group === cur.def.group);
  const msgs = [];
  for (const c of group) for (const m of c.msgs) if (m.from !== "sys") msgs.push({ seq: m.seq, sender: m.from === "me" ? "You" : c.def.name, text: m.plain });
  if (!msgs.some(m => m.sender !== "You")) { toast("Nothing to scan yet — wait for a message.", "info"); return; }
  msgs.sort((a, b) => a.seq - b.seq);
  modal(`<h2>🛡️ ScamSense is scanning…</h2><div class="radar"></div><p style="text-align:center">Removing personal details → reading every message → comparing with known scams</p>`);
  const t0 = Date.now(); let res = null, err = null;
  try {
    const r = await fetch("/api/scan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages: msgs.map(({ sender, text }) => ({ sender, text })) }) });
    res = await r.json(); if (!r.ok || res.error) throw new Error(res.error || "scan failed");
  } catch (e) { err = e; }
  await new Promise(r => setTimeout(r, Math.max(0, 1500 - (Date.now() - t0))));
  if (err || !res) { modal(`<h2>📡 Scanner offline</h2><p>Couldn't reach ScamSense. This didn't cost you a scan.</p><button class="big-btn small" onclick="document.getElementById('modal').classList.remove('show')">OK</button>`); return; }
  G.scans--; hud();
  const col = { "Likely scam": "#d32f2f", "Suspicious": "#ef6c00", "Can't tell": "#546e7a" }[res.verdict] || "#546e7a";
  const emo = { "Likely scam": "🔴", "Suspicious": "🟠", "Can't tell": "⚪" }[res.verdict] || "⚪";
  modal(`<h2>🛡️ ScamSense says</h2><div class="verdict-big" style="color:${col}">${emo} ${esc(res.verdict)} <small style="font-size:16px">(${Math.round(res.confidence * 100)}% sure)</small></div>
    <p>${esc(res.reason || "")}</p>
    ${(res.signals || []).map(s => `<p>🔗 <b>${esc(s)}</b></p>`).join("")}
    ${res.typology ? `<p>📚 Closest known scam type: <b>${esc(res.typology)}</b></p>` : ""}
    ${res.demo ? `<p style="color:#b26a00">⚠️ DEMO MODE: offline keyword stand-in, not a real AI model.</p>` : ""}
    <p style="font-size:13px;opacity:.7">The Scanner reads the chats as one storyline. It's an aid, not a guarantee — you make the final call.</p>
    <button class="big-btn small" onclick="document.getElementById('modal').classList.remove('show')">Got it</button>`);
  Sfx.good();
}

/* ------------------------------------------------------------ modal / wiring */
function modal(html, lock = false) { $("#modal-card").innerHTML = html; $("#modal").dataset.lock = lock ? "1" : ""; $("#modal").classList.add("show"); }
$("#modal").addEventListener("click", e => { if (e.target.id === "modal" && !$("#modal").dataset.lock) $("#modal").classList.remove("show"); });
function howTo() {
  modal(`<h2>How to play 🎮</h2><ol>
    <li>Each <b>case</b> is one organised scam operation: its members hand you to each other and back each other up. A few <b>real</b> contacts are mixed in, and some real ones sound as pushy as the scammers.</li>
    <li><b>You TYPE.</b> Ask who they are, whether you can check them, what they know, whether you can video call… Use <b>🧾 Your life</b> to spot claims that don't fit.</li>
    <li>You can't judge a chat until you've asked questions. <b>Clues</b> (🔎 warning signs, ✅ good signs, ⚡ contradictions between members) earn points and bonuses.</li>
    <li>Careful: saying "ok, sending it" to a scammer <b>costs real savings</b>. Accusing a genuine sender costs <b>trust</b>. Exposing one ring member doesn't stop the ring: <b>the next voice will contact you</b>. 3 stars need a thorough investigation of most chats, not just survival.</li>
    <li>Tap suspicious words for 🚩 red flags. Stuck? <b>💡 Hint</b> (−20) or the <b>🛡️ ScamSense Scanner</b> (real AI, 3 per case).</li></ol>
    <button class="big-btn small" onclick="document.getElementById('modal').classList.remove('show')">Let's go!</button>`);
}
function setSound(on) { save.sound = on; Store.save(save); $$("#snd-levels,#snd-game").forEach(b => b.textContent = on ? "🔊" : "🔇"); }
$("#btn-play").onclick = () => { Sfx.ping(); renderLevels(); show("levels"); };
$("#btn-how").onclick = howTo;
$("#levels-back").onclick = () => show("title");
$("#game-menu").onclick = () => { endGame(); G = null; renderLevels(); show("levels"); };
$("#btn-scan").onclick = scan;
$("#btn-speed").onclick = () => { const i = SPEEDS.findIndex(s => s[0] === save.speed); save.speed = SPEEDS[(i + 1) % SPEEDS.length][0]; Store.save(save); if (G) hud(); };
["#snd-levels", "#snd-game"].forEach(s => $(s).onclick = () => setSound(!save.sound));
setSound(save.sound);
window.__game = { start: i => { renderLevels(); startLevel(i); }, state: () => G, classify, kwIntent, begin: () => $("#brief-go") && $("#brief-go").click() };
const q = new URLSearchParams(location.search).get("level"); if (q) window.__game.start(+q - 1);
})();
