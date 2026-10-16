// Build game/personas.json from game/levels.js.  Run:  node game/build_personas.mjs
// The server only ever trusts personas.json (authored content), never persona text sent by a browser.
// That keeps /api/chat from being usable as a generic scam-text generator: it can only voice these fixed characters.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const src = fs.readFileSync(path.join(here, "levels.js"), "utf-8") + "\nreturn { LEVELS, STYLES, INTENTS, INTENT_ORDER };";
const { LEVELS, STYLES, INTENTS, INTENT_ORDER } = new Function(src)();

const strip = o => Object.fromEntries(Object.entries(o || {}).filter(([, v]) => v));
const textOf = r => (typeof r === "string" ? r : r.m);
const DOMAIN = /\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.(?:com|sg|xyz|top|cc|co|net|org)(?:\/[^\s"'<>)]*)?/gi;
const PHONE = /\+65[ \dx]*[\dx]/gi;

const out = { intents: Object.fromEntries(INTENT_ORDER.map(id => [id, INTENTS[id].desc])), cases: {} };
for (const L of LEVELS) {
  for (const c of L.chats) {
    const spec = (c.script.find(s => s && s.open) || {}).open || {};
    const st = STYLES[c.style] || {};
    const vars = { ...(st.vars || {}), ...(spec.vars || {}) };
    const replies = { ...(st.replies || {}), ...(spec.replies || {}) };
    const fill = str => String(str).replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");
    const tells = {}, clears = {}, facts = {}, go = {};
    for (const [intent, label] of Object.entries(strip({ ...(st.tells || {}), ...(spec.tells || {}) }))) {
      tells[intent] = { label, example: fill(textOf((replies[intent] || [""])[0])) };
    }
    for (const [intent, label] of Object.entries(strip({ ...(st.clears || {}), ...(spec.clears || {}) }))) {
      clears[intent] = { label, example: fill(textOf((replies[intent] || [""])[0])) };
    }
    for (const [intent, list] of Object.entries(replies)) {
      if (intent === "_all") continue;
      const withFact = list.filter(r => typeof r === "object" && r.fact);
      if (withFact.length) facts[intent] = { key: withFact[0].fact[0], values: withFact.map(r => r.fact[1]) };
      const g = list.find(r => typeof r === "object" && r.go);
      if (g) go[intent] = g.go;
    }
    // everything this character is allowed to mention: links, domains and numbers that appear in its authored content
    const blob = JSON.stringify([c.script.filter(s => typeof s === "string"), Object.values(vars), Object.values(replies)]);
    const allowed = [...new Set([...(blob.match(DOMAIN) || []), ...(blob.match(PHONE) || [])].map(x => x.toLowerCase().replace(/[.,;]+$/, "")))];
    out.cases[`${L.id}:${c.id}`] = {
      level: L.id, id: c.id, name: c.name, truth: c.truth, style: c.style, realism: L.realism || 1, persona: c.persona || "", knows: c.knows || "",
      llm: c.style !== "bot", tells, clears, facts, go, allowed,
    };
  }
}
fs.writeFileSync(path.join(here, "personas.json"), JSON.stringify(out, null, 1) + "\n", "utf-8");
console.log(`wrote ${Object.keys(out.cases).length} personas`);
