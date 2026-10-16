/* ScamSense: Inbox Defender — game engine. Vanilla JS, no dependencies. Content lives in levels.js (authored). */
(() => {
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const rnd = (a, b) => a + Math.random() * (b - a);

/* ------------------------------------------------------------ persistence (never required) */
const Store = {
  load() { try { return JSON.parse(localStorage.getItem("scamsense_game") || "{}"); } catch { return {}; } },
  save(o) { try { localStorage.setItem("scamsense_game", JSON.stringify(o)); } catch { /* ignore */ } },
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
  good() { [523, 659, 784, 1047].forEach((f, i) => this.tone(f, .14, "triangle", .12, i * .07)); },
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

/* ------------------------------------------------------------ game state */
let G = null;
const nameOfTypology = id => (TYPOLOGY_NAMES[id] || id);
function show(screen) { $$(".screen").forEach(s => s.classList.toggle("active", s.id === "screen-" + screen)); }
const spd = () => save.speed;
const alive = c => G && G.alive && !c.halted;

function later(fn, ms) { const id = setTimeout(() => { G && G.timeouts.delete(id); fn(); }, ms); if (G) G.timeouts.add(id); return id; }
function wait(ms) { return new Promise(res => later(res, ms / spd())); }

function newGame(idx) {
  endGame();
  const L = LEVELS[idx];
  G = { idx, L, money: L.savings, lives: 3, score: 0, scans: 3, alive: true, active: null, chats: {}, order: [], found: 0,
        timeouts: new Set(), clock: 9 * 60 + 41, done: false, nodes: {}, mistakes: 0, seq: 0, foundSet: new Set() };
  for (const def of L.chats) G.chats[def.id] = { def, id: def.id, msgs: [], unread: 0, started: false, halted: false, finished: false,
    verdict: null, typing: false, choice: null, cancelled: false, found: 0, correct: null };
  // parent links (who hands off to whom)
  for (const c of Object.values(G.chats)) c.children = c.def.script.filter(s => s && s.go).map(s => s.go);
}
function endGame() { if (G) { G.alive = false; G.timeouts.forEach(clearTimeout); G.timeouts.clear(); for (const c of Object.values(G.chats)) clearTimeout(c.tmo); } }

/* ------------------------------------------------------------ HUD */
function hud() {
  $("#hud-emoji").textContent = G.L.emoji; $("#hud-name").textContent = `Level ${G.L.id}: ${G.L.name}`;
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
  const last = chat.msgs[chat.msgs.length - 1];
  const prev = chat.typing ? "typing…" : last ? (last.from === "me" ? "You: " : "") + last.plain : "";
  let side = "";
  if (chat.verdict) side = `<span class="verdict-mark">${chat.correct ? "✅" : "❌"}</span>`;
  else if (chat.choice) side = `<span class="reply-needed">REPLY!</span>`;
  else if (chat.unread) side = `<span class="badge-un">${chat.unread}</span>`;
  n.classList.toggle("active", G.active === chat.id);
  n.innerHTML = `<div class="avatar">${chat.def.avatar}</div><div class="c-main"><div class="c-name">${esc(chat.def.name)}</div>
    <div class="c-prev ${chat.typing ? "typing" : ""}">${esc(prev.slice(0, 60))}</div></div><div class="c-side">${side}</div>`;
}

function renderHead(chat) {
  const h = $("#chat-head");
  if (!chat) { h.innerHTML = `<div class="empty-head">📨 Waiting for messages…</div>`; return; }
  const btns = chat.verdict ? `<span class="pill ${chat.correct ? "good" : "bad"}" style="margin-left:auto">${chat.correct ? "✅ You got it" : "❌ You missed it"}</span>`
    : `<div class="verdict-btns"><button class="vbtn scam" data-v="scam">🚩 Scam!</button><button class="vbtn real" data-v="real">✅ Real</button></div>`;
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
  syncTray();
}

function makeBubble(chat, m, i, instant) {
  if (m.from === "sys") { const d = document.createElement("div"); d.className = "sys"; d.textContent = m.plain; return d; }
  const d = document.createElement("div"); d.className = `bubble ${m.from}` + (instant ? " instant" : "");
  d.innerHTML = bubbleHTML(m, chat.id, i) + `<time>${m.time}</time>`;
  // restore found / missed state
  $$(".f", d).forEach(f => {
    if (G.foundSet.has(f.dataset.key)) { f.classList.add("found"); }
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
  if (from === "them") Sfx.ping(); else Sfx.tick();
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

/* ------------------------------------------------------------ scripted conversation engine */
function startChat(chat) {
  if (!G || !G.alive || chat.started || chat.cancelled) return;
  chat.started = true; G.order.push(chat.id);
  renderContact(chat);
  toast(`📩 New message from ${chat.def.name}`, "info"); Sfx.ping();
  if (!G.active || (G.chats[G.active] && G.chats[G.active].verdict)) selectChat(chat.id);
  runScript(chat);
}

async function typingThen(chat, text) {
  chat.typing = true; renderContact(chat); if (G.active === chat.id) syncTyping();
  const plain = parseMarkup(text).plain;
  await wait(Math.min(2200, 650 + plain.length * 16));
  chat.typing = false;
  if (!alive(chat)) { renderContact(chat); if (G && G.active === chat.id) syncTyping(); return; }
  addMsg(chat, "them", text);
  await wait(450);
}

async function runScript(chat) {
  for (const step of chat.def.script) {
    if (!alive(chat)) return;
    if (typeof step === "string") await typingThen(chat, step);
    else if (step.me) { await wait(500); if (!alive(chat)) return; addMsg(chat, "me", step.me); }
    else if (step.w) await wait(step.w);
    else if (step.sys) addSys(chat, step.sys);
    else if (step.go) { const c = G.chats[step.go]; if (c && alive(chat)) startChat(c); }
    else if (step.c) {
      const opt = await askChoice(chat, step);
      if (!alive(chat) && !opt) return;
      await applyOption(chat, opt);
      if (opt.end) { chat.finished = true; cancelChildren(chat, "good"); checkDone(); return; }
    }
  }
  chat.finished = true; checkDone();
}

function askChoice(chat, step) {
  return new Promise(resolve => {
    const total = step.timer ? step.timer * (spd() < 1 ? 1.4 : 1) * 1000 : 0;
    chat.choice = { step, resolve, total, deadline: total ? Date.now() + total : 0 };
    if (total) chat.tmo = setTimeout(() => pick(chat, step.def || 0, true), total);
    renderContact(chat); if (G.active === chat.id) syncTray();
    if (G.active !== chat.id && !total) toast(`💬 ${chat.def.name} needs your reply!`, "info");
  });
}

function pick(chat, index, auto = false) {
  const ch = chat.choice; if (!ch || !G.alive) return;
  clearTimeout(chat.tmo); chat.choice = null; syncTray(); renderContact(chat);
  const opt = ch.step.c[index];
  if (auto) toast("⏱️ Time's up! You froze and replied on instinct…", "bad");
  ch.resolve(opt);
}

async function applyOption(chat, opt) {
  const label = opt.t.replace(/\s*[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]+\s*$/u, "");
  addMsg(chat, "me", label);
  await wait(450);
  if (!G.alive) return;
  if (opt.pts) addScore(opt.pts);
  if (opt.money) changeMoney(opt.money);
  if (opt.life) loseLife();
  if (opt.ok) { Sfx.good(); flash("green"); const [x, y] = center($("#appwin")); confetti(x, y - 80, 26, .7); }
  toast(opt.say, opt.ok ? "good" : "bad");
  if (!opt.ok) G.mistakes++;
  checkFail();
  for (const msg of opt.then || []) { if (!alive(chat)) return; await typingThen(chat, msg); }
}

/* tray */
function syncTray() {
  const tray = $("#tray"), chat = G.chats[G.active];
  if (!chat || !chat.choice) { tray.classList.remove("show"); tray.innerHTML = ""; return; }
  const ch = chat.choice;
  tray.innerHTML = `<div class="tray-title">💬 YOUR REPLY${ch.total ? ` <div class="timerbar"><i></i></div>` : ""}</div>` +
    ch.step.c.map((o, i) => `<button class="opt" data-i="${i}">${esc(o.t)}</button>`).join("");
  tray.classList.add("show");
  $$(".opt", tray).forEach(b => b.addEventListener("click", () => pick(chat, +b.dataset.i)));
  if (ch.total) {
    const bar = $(".timerbar i", tray), remain = Math.max(0, ch.deadline - Date.now());
    bar.style.transform = `scaleX(${remain / ch.total})`;
    requestAnimationFrame(() => { bar.style.transition = `transform ${remain}ms linear`; bar.style.transform = "scaleX(0)"; });
  }
}

/* ------------------------------------------------------------ red flags */
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
    ul.insertAdjacentHTML("afterbegin", `<li><b>${esc(chat.def.name)}</b><br>${esc(t.dataset.label)}</li>`);
    $("#flag-count").textContent = G.found;
  } else {
    t.classList.remove("wrong"); void t.offsetWidth; t.classList.add("wrong");
    addScore(-2); Sfx.tick(); floatText("meh…", "bad", e.clientX - 10, e.clientY - 20);
  }
});

/* ------------------------------------------------------------ verdicts */
function cancelChildren(chat, why) {
  const cancelled = [];
  const walk = c => { for (const id of c.children) { const k = G.chats[id]; if (k && !k.started && !k.cancelled) { k.cancelled = true; cancelled.push(k); walk(k); } } };
  walk(chat);
  const direct = cancelled.filter(k => chat.children.includes(k.id));
  if (direct.length && why !== "silent") {
    const bonus = 50 * direct.length; addScore(bonus);
    toast(`🏆 Early bird! You stopped the chain before ${direct.map(k => k.def.name).join(" & ")} even texted you! +${bonus}`, "good");
    const [x, y] = center($("#appwin")); confetti(x, y - 60, 60);
  }
  return cancelled;
}

function verdict(chat, v) {
  if (chat.verdict || !G.alive) return;
  clearTimeout(chat.tmo); chat.choice = null; chat.typing = false; chat.halted = true;
  const truth = chat.def.truth === "scam" ? "scam" : "real";
  chat.verdict = v; chat.correct = v === truth;
  const [cx, cy] = center($("#chat-head"));
  if (chat.correct) {
    addScore(100); Sfx.stamp(); setTimeout(() => Sfx.good(), 250);
    stamp(truth === "scam" ? "SCAM BLOCKED" : "VERIFIED REAL", "good"); confetti(cx, cy + 120, 70);
    if (truth === "scam") cancelChildren(chat, "good");
  } else if (truth === "real") {
    loseLife(); addScore(-50); Sfx.bad(); flash("red"); stamp("THAT WAS REAL!", "badc");
    toast("Oops — you accused someone genuine. Trust −1 💔", "bad"); cancelChildren(chat, "silent");
  } else {
    changeMoney(-1000); loseLife(); stamp("IT WAS A SCAM!", "badc");
    toast("You trusted a scammer. −$1,000 and −1 trust", "bad"); cancelChildren(chat, "silent");
  }
  syncTray(); renderHead(chat); renderContact(chat);
  // reveal the flags the player missed
  $$("#messages .bubble.them .f:not(.found)").forEach(f => truth === "scam" && f.classList.add("missed"));
  later(() => showCasefile(chat), 1300);
  checkFail(); checkDone();
}

function stamp(text, cls) {
  const s = $("#stamp"); s.textContent = text; s.className = "stamp " + cls; void s.offsetWidth; s.classList.add("show");
}
function totalFlags(chat) { return chat.msgs.reduce((n, m) => n + m.parts.filter(p => p.label).length, 0); }
function showCasefile(chat) {
  const c = $("#casefile"), truth = chat.def.truth;
  c.innerHTML = `<button class="close">×</button><h4>${truth === "scam" ? "🕵️ Case file: SCAM" : "📘 Case file: genuine"} — ${esc(chat.def.name)}</h4>
    <p>${esc(chat.def.explain)}</p>
    <div class="row"><span class="pill">${esc(nameOfTypology(chat.def.typology))}</span>
    ${truth === "scam" ? `<span class="pill ${chat.found >= totalFlags(chat) ? "good" : ""}">🚩 ${chat.found}/${totalFlags(chat)} red flags found</span>` : ""}</div>`;
  c.classList.add("show"); $(".close", c).onclick = () => c.classList.remove("show");
}

/* ------------------------------------------------------------ level lifecycle */
function checkDone() {
  if (!G || !G.alive || G.done) return;
  const all = Object.values(G.chats);
  const ready = all.every(c => (c.started && c.verdict) || c.cancelled);
  if (ready) { G.done = true; later(() => endLevel(true), 1800); }
}

function startLevel(idx) {
  newGame(idx);
  const L = G.L;
  shownMoney = L.savings;
  $("#appwin").className = "appwin " + L.theme;
  $("#app-title").textContent = L.theme === "telegram" ? "Telegram Desktop" : "WhatsApp Web";
  $("#contacts").innerHTML = ""; $("#messages").innerHTML = `<div class="empty-chat"><div>🔔</div><p>Your inbox is quiet…<br>for now.</p></div>`;
  $("#tray").classList.remove("show"); $("#casefile").classList.remove("show"); $("#stamp").className = "stamp";
  $("#mission").textContent = L.mission; $("#flag-list").innerHTML = `<li class="muted">Tap suspicious words in scam messages…</li>`; $("#flag-count").textContent = "0";
  renderHead(null); hud(); animateMoney();
  show("game");
  toast(`${L.emoji} ${L.name} — ${L.blurb}`, "info");
  for (const c of Object.values(G.chats)) if (c.def.start != null) later(() => startChat(c), c.def.start / spd() + 900);
}

function starsFor(ok) {
  if (!ok) return 0;
  if (G.lives === 3 && G.money >= .9 * G.L.savings) return 3;
  if (G.lives >= 2 && G.money >= .5 * G.L.savings) return 2;
  return 1;
}

function endLevel(ok) {
  if (!G || G.finished) return; G.finished = true; G.done = true;
  $("#toasts").innerHTML = "";
  const stars = starsFor(ok);
  const prev = save.stars[G.L.id] || 0; if (stars > prev) save.stars[G.L.id] = stars; Store.save(save);
  const lvl = G.idx, L = G.L, snap = { money: G.money, lives: G.lives, score: G.score, found: G.found };
  const chats = Object.values(G.chats).filter(c => c.started);
  endGame(); shownMoney = snap.money;
  $("#result-banner").textContent = ok ? (stars === 3 ? "🏆 FLAWLESS!" : "LEVEL CLEARED!") : "💥 GAME OVER";
  $("#result-stars").innerHTML = [0, 1, 2].map(i => `<span style="animation-delay:${.4 + i * .35}s;opacity:${i < stars ? 1 : .22}">${i < stars ? "⭐" : "☆"}</span>`).join("");
  $("#result-stats").innerHTML = `<div><small>SAVINGS LEFT</small><b>$${snap.money.toLocaleString()}</b></div><div><small>TRUST</small><b>${"❤️".repeat(snap.lives) || "💔"}</b></div>
    <div><small>SCORE</small><b>${snap.score}</b></div><div><small>RED FLAGS</small><b>🚩 ${snap.found}</b></div>`;
  $("#result-cases").innerHTML = chats.map((c, i) => `<div class="case" style="animation-delay:${i * .08}s"><h4>${c.def.avatar} ${esc(c.def.name)}
    <span class="pill ${c.def.truth === "scam" ? "bad" : "good"}">${c.def.truth === "scam" ? "SCAM" : "REAL"}</span>
    <span class="pill ${c.verdict ? (c.correct ? "good" : "bad") : ""}">${c.verdict ? (c.correct ? "✅ you got it" : "❌ you missed it") : "⏭ not judged"}</span></h4>
    <p>${esc(c.def.explain)}</p><span class="pill">${esc(nameOfTypology(c.def.typology))}</span></div>`).join("");
  $("#res-next").style.display = ok && lvl < LEVELS.length - 1 ? "" : "none";
  $("#res-next").onclick = () => startLevel(lvl + 1); $("#res-retry").onclick = () => startLevel(lvl);
  $("#res-menu").onclick = () => { renderLevels(); show("levels"); };
  show("result");
  if (ok) { Sfx.win(); [0.25, 0.5, 0.75].forEach((f, i) => setTimeout(() => confetti(innerWidth * f, innerHeight * .35, 90, 1.3), i * 350)); }
  else Sfx.lose();
  if (ok && lvl === LEVELS.length - 1) setTimeout(() => toast("🎉 You finished the game — now go warn someone you love!", "good"), 1500);
}

/* ------------------------------------------------------------ level select */
function unlocked(i) { return i === 0 || (save.stars[LEVELS[i - 1].id] || 0) > 0 || location.hash.includes("unlock"); }
function renderLevels() {
  const g = $("#level-grid"); g.innerHTML = ""; let total = 0;
  LEVELS.forEach((L, i) => {
    const st = save.stars[L.id] || 0; total += st; const open = unlocked(i);
    const d = document.createElement("div"); d.className = "lvl" + (open ? "" : " locked");
    d.style.setProperty("--a", L.colors[0]); d.style.setProperty("--b", L.colors[1]); d.style.animationDelay = i * .07 + "s";
    d.innerHTML = `<span class="num">${L.id}</span><span class="em">${L.emoji}</span><h3>${esc(L.name)}</h3><p>${esc(L.blurb)}</p>
      <div class="stars">${[0, 1, 2].map(k => k < st ? "⭐" : "☆").join("")}</div><span class="badge">${L.chats.length} chats${L.timed ? " · ⏱️ timed" : ""}</span>`;
    if (open) d.onclick = () => startLevel(i); else d.title = "Clear the previous level to unlock";
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
    <p style="font-size:13px;opacity:.7">ScamSense is an aid, not a guarantee — you make the final call.</p>
    <button class="big-btn small" onclick="document.getElementById('modal').classList.remove('show')">Got it</button>`);
  Sfx.good();
}

/* ------------------------------------------------------------ modal / wiring */
function modal(html) { $("#modal-card").innerHTML = html; $("#modal").classList.add("show"); }
$("#modal").addEventListener("click", e => { if (e.target.id === "modal") $("#modal").classList.remove("show"); });
function howTo() {
  modal(`<h2>How to play 🎮</h2><ol>
    <li><b>Messages pop up</b> — some from friends, some from scammers. Often several people text you <i>at once</i>, and scammers <b>pass you to each other</b>.</li>
    <li><b>Reply</b> when asked. Wrong choices cost <b>💸 savings</b> or <b>❤️ trust</b>. Hard levels have <b>⏱️ timers</b>.</li>
    <li><b>Tap suspicious words</b> inside messages to find <b>🚩 red flags</b> (+10). Wrong taps cost a little.</li>
    <li>Judge each chat: <b>🚩 Scam!</b> or <b>✅ Real</b>. Stop a scam chain early for an <b>Early-bird bonus</b>. Don't accuse real friends!</li>
    <li>Stuck? Use the <b>🛡️ ScamSense Scanner</b> — it runs the real analyser on the whole storyline (3 per level).</li></ol>
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
addEventListener("keydown", e => {
  if (!G || !G.alive) return; const chat = G.chats[G.active]; if (!chat || !chat.choice) return;
  const i = parseInt(e.key, 10) - 1; if (i >= 0 && i < chat.choice.step.c.length) pick(chat, i);
});
setSound(save.sound);
window.__game = { start: i => { renderLevels(); startLevel(i); }, state: () => G }; // handy for demos/tests
const q = new URLSearchParams(location.search).get("level"); if (q) window.__game.start(+q - 1);
})();
