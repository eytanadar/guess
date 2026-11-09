// Regenerate demo/script.json with Claude from the current docs, the CHI 2006
// paper (for voice) and demo/PROMPT.md. Then `npm run demo` records it.
//
//   cd web && npm run demo:script                  # writes demo/script.json (old one → script.prev.json)
//   npm run demo:script -- --notes "focus on the new timeline and presentation mode"
//
// Needs ANTHROPIC_API_KEY (the repo's .env is read) or an `ant auth login` profile.
import Anthropic from "@anthropic-ai/sdk";
import { copyFileSync, existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..", "..");
const args = process.argv.slice(2);
const notesAt = args.indexOf("--notes");
const notes = notesAt >= 0 ? args[notesAt + 1] : "";
const outAt = args.indexOf("--out");
const outFile = outAt >= 0 ? resolve(args[outAt + 1]) : null;   // default: replace demo/script.json

// the repo's .env (ANTHROPIC_API_KEY)
const envFile = join(root, ".env");
if (existsSync(envFile)) {
  for (const line of readFileSync(envFile, "utf8").split("\n")) {
    const m = /^\s*([A-Za-z_]\w*)\s*=\s*(.*)\s*$/.exec(line);
    if (m && !(m[1] in process.env)) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
}

const read = (p) => readFileSync(join(root, p), "utf8");
const paperDir = join(root, "output-md", "guess-chi2006");
const paper = readdirSync(paperDir).filter((f) => /^0[1-4].*\.md$/.test(f)).sort()
  .map((f) => readFileSync(join(paperDir, f), "utf8")).join("\n\n");
const plan = read("PLAN.md");
const recent = plan.slice(plan.indexOf("### Cell console"), plan.indexOf("### Gephi-inspired candidates"));
const current = readFileSync(join(here, "script.json"), "utf8");

const documents = [
  ["The prompt (your instructions)", readFileSync(join(here, "PROMPT.md"), "utf8")],
  ["CHI 2006 paper excerpts (voice and style)", paper],
  ["User guide", read("docs/USER_GUIDE.md")],
  ["API reference (every command)", read("docs/API.md")],
  ["Recent changes (from PLAN.md)", recent],
  ["The current script.json (keep voice/ttsModel; reuse what works)", current],
];

const VERBS = new Set(["run", "wait", "title", "caption", "menu", "click", "select", "fill", "key", "typeKeys",
  "hoverNode", "hoverOutput", "hoverText", "dragNode", "dragIntoGroup", "zoom"]);
const MODIFIERS = new Set(["subtitle", "close", "alt", "visible"]);

/** Problems with a script, as messages Claude can act on (empty = fine). */
function validate(s) {
  const errs = [];
  if (!Array.isArray(s.scenes) || !s.scenes.length) return ["`scenes` must be a non-empty array"];
  let words = 0;
  s.scenes.forEach((sc, i) => {
    if (typeof sc.id !== "string" || typeof sc.narration !== "string") errs.push(`scene ${i}: needs string id and narration`);
    words += (sc.narration ?? "").split(/\s+/).filter(Boolean).length;
    (sc.actions ?? []).forEach((a, k) => {
      const verbs = Object.keys(a).filter((x) => VERBS.has(x));
      const unknown = Object.keys(a).filter((x) => !VERBS.has(x) && !MODIFIERS.has(x));
      if (verbs.length !== 1) errs.push(`scene ${sc.id} action ${k}: needs exactly one verb, got ${JSON.stringify(a)}`);
      if (unknown.length) errs.push(`scene ${sc.id} action ${k}: unknown keys ${unknown.join(", ")}`);
    });
  });
  if (words > 720) errs.push(`narration has ${words} words; the limit is about 700 (5 minutes)`);
  return errs;
}

const client = new Anthropic();

async function ask(extra) {
  const content = [
    ...documents.map(([title, text]) => ({ type: "text", text: `<document title="${title}">\n${text}\n</document>` })),
    { type: "text", text: `Write the new script.json now.${notes ? `\n\nAuthor's notes for this version: ${notes}` : ""}${extra ? `\n\n${extra}` : ""}` },
  ];
  const stream = client.beta.messages.stream({
    model: "claude-opus-5-5",
    max_tokens: 64000,
    betas: ["server-side-fallback-2026-07-01"],
    fallbacks: "default",
    output_config: { effort: "high" },
    system: "You write narrated demo scripts for GUESS, following the prompt document exactly. Reply with the JSON object only.",
    messages: [{ role: "user", content }],
  });
  const msg = await stream.finalMessage();
  if (msg.stop_reason === "refusal") throw new Error(`the model declined: ${msg.stop_details?.explanation ?? "no details"}`);
  if (msg.stop_reason === "max_tokens") throw new Error("the response was cut off (max_tokens)");
  const text = msg.content.filter((b) => b.type === "text").map((b) => b.text).join("");
  const json = text.slice(text.indexOf("{"), text.lastIndexOf("}") + 1);
  return JSON.parse(json);
}

let script, errs = [];
for (let attempt = 0; attempt < 2; attempt++) {
  try {
    script = await ask(errs.length ? `Your previous script had these problems; fix them:\n- ${errs.join("\n- ")}` : "");
    errs = validate(script);
  } catch (e) {
    if (e instanceof Anthropic.APIError) throw e;
    errs = [`the reply was not valid JSON (${e.message})`];
  }
  if (!errs.length) break;
  console.warn(`attempt ${attempt + 1}: ${errs.length} problems; asking again`);
}
if (errs.length) {
  console.error("could not get a valid script:\n- " + errs.join("\n- "));
  process.exit(1);
}
const old = JSON.parse(current);
script.voice ??= old.voice;
script.pronounce ??= old.pronounce;
script.ttsModel ??= old.ttsModel;
if (outFile) {
  writeFileSync(outFile, JSON.stringify(script, null, 2) + "\n");
} else {
  copyFileSync(join(here, "script.json"), join(here, "script.prev.json"));
  writeFileSync(join(here, "script.json"), JSON.stringify(script, null, 2) + "\n");
}
const words = script.scenes.reduce((n, s) => n + s.narration.split(/\s+/).length, 0);
console.log(`wrote ${outFile ?? "demo/script.json"}: ${script.scenes.length} scenes, ${words} words (≈ ${Math.round(words / 2.5)} s of narration)`);
console.log("previous version: demo/script.prev.json. Next: npm run demo -- --dry-run, then npm run demo");
