// Parity check: run the JS core from web/app.html against tests/vectors.json.
// Usage: node web/parity.test.mjs   (after: python tests/make_vectors.py)
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(join(here, "app.html"), "utf8");
const m = html.match(/<script id="core">([\s\S]*?)<\/script>/);
if (!m) {
  console.error('FAIL: no <script id="core"> block in app.html');
  process.exit(1);
}
const ctx = vm.createContext({});
vm.runInContext(m[1] + "\n;globalThis.CP = CP;", ctx, { filename: "app.html#core" });
const CP = ctx.CP;
const V = JSON.parse(readFileSync(join(here, "..", "tests", "vectors.json"), "utf8"));

const REL = 1e-9;
let checks = 0;
const failures = [];

function close(a, b) {
  if (a === b) return true;
  const scale = Math.max(Math.abs(a), Math.abs(b), 1e-300);
  return Math.abs(a - b) <= REL * scale;
}
function deepCompare(got, want, path) {
  checks++;
  if (want === null || typeof want !== "object") {
    if (typeof want === "number") {
      if (typeof got !== "number" || !close(got, want)) failures.push(`${path}: got ${got}, want ${want}`);
    } else if (got !== want) {
      failures.push(`${path}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);
    }
    return;
  }
  if (Array.isArray(want)) {
    if (!Array.isArray(got) || got.length !== want.length) {
      failures.push(`${path}: array length got ${got && got.length}, want ${want.length}`);
      return;
    }
    want.forEach((w, i) => deepCompare(got[i], w, `${path}[${i}]`));
    return;
  }
  if (got === null || typeof got !== "object") {
    failures.push(`${path}: got ${JSON.stringify(got)}, want object`);
    return;
  }
  const gk = Object.keys(got).sort().join(",");
  const wk = Object.keys(want).sort().join(",");
  if (gk !== wk) failures.push(`${path}: keys differ\n  got  ${gk}\n  want ${wk}`);
  for (const k of Object.keys(want)) deepCompare(got[k], want[k], `${path}.${k}`);
}
function inRealm(x) { return vm.runInContext("(" + JSON.stringify(x) + ")", ctx); }
function plain(x) { return JSON.parse(JSON.stringify(x)); }
function expectError(fn, want, path) {
  checks++;
  try {
    fn();
    failures.push(`${path}: did not throw`);
  } catch (e) {
    if (e.code !== want.code || e.message !== want.message) {
      failures.push(`${path}: got ${e.code} "${e.message}", want ${want.code} "${want.message}"`);
    }
  }
}

// Constants must match so both sides group and spread identically.
deepCompare(plain(CP.SPREADS), V.spread_defs, "SPREADS");
deepCompare(plain(CP.CODE_GROUPS), V.code_groups, "CODE_GROUPS");
deepCompare(plain(CP.NAME_KEYWORDS), V.name_keywords, "NAME_KEYWORDS");

const datasets = {};
for (const k of Object.keys(V.datasets)) datasets[k] = inRealm(V.datasets[k]);

V.summarize.forEach((v, i) => deepCompare(plain(CP.summarize(inRealm(v.series), v.kind)), v.out, `summarize[${i}:${v.series.id}:${v.kind}]`));
V.zscore_percentile.forEach((v, i) => {
  const s = inRealm(V.synth[v.series]);
  deepCompare(CP.zscore(s, v.idx, v.window), v.z, `zscore[${i}]`);
  deepCompare(CP.percentile(s, v.idx), v.pct, `percentile[${i}]`);
});
V.rebase.forEach((v, i) => deepCompare(plain(CP.rebase(inRealm(v.series), v.base)), v.out, `rebase[${i}]`));
V.window.forEach((v, i) => deepCompare(plain(CP.window(inRealm(v.series), v.first, v.last)), v.out, `window[${i}]`));
V.window_errors.forEach((v, i) => expectError(() => CP.window(inRealm(V.synth[0]), v.first, v.last), v, `window_errors[${i}]`));
V.combine.forEach((v, i) => deepCompare(plain(CP.combine(inRealm(v.a), inRealm(v.b), v.op)), v.out, `combine[${i}]`));
V.spreads.forEach((v, i) => deepCompare(plain(CP.spreads(datasets[v.dataset])), v.out, `spreads[${i}]`));
V.movers.forEach((v, i) => deepCompare(plain(CP.movers(datasets[v.dataset], v.group, v.by, v.top)), v.out,
  `movers[${i}:${v.group}:${v.by}:${v.top}]`));
V.classify.forEach((v) => deepCompare(CP.classify(v.code, v.name), v.group, `classify(${v.code},${v.name})`));
V.format.forEach((v) => {
  const x = v.x;
  deepCompare(CP.roundHalfAway(x, 0), v.r0, `round0(${x})`);
  deepCompare(CP.roundHalfAway(x, 1), v.r1, `round1(${x})`);
  deepCompare(CP.roundHalfAway(x, 2), v.r2, `round2(${x})`);
  deepCompare(CP.formatValue(x), v.value, `formatValue(${x})`);
  deepCompare(CP.formatPct(x), v.pct, `formatPct(${x})`);
  deepCompare(CP.formatSigned(x), v.signed, `formatSigned(${x})`);
});
V.months.forEach((v) => {
  deepCompare(CP.parseMonth(v.month), v.idx, `parseMonth(${v.month})`);
  deepCompare(CP.monthAdd(v.month, 13), v.plus, `monthAdd(${v.month},13)`);
  deepCompare(CP.monthAdd(v.month, -13), v.minus, `monthAdd(${v.month},-13)`);
});
V.month_errors.forEach((v, i) => expectError(() => CP.parseMonth(inRealm(v.input)), v, `month_errors[${i}]`));
V.validate_ok.forEach((v, i) => deepCompare(plain(CP.validateDataset(inRealm(v.input))), v.out, `validate_ok[${i}]`));
V.validate_errors.forEach((v, i) => expectError(() => CP.validateDataset(inRealm(v.input)), v, `validate_errors[${i}]`));
V.csv.forEach((v, i) => {
  if (v.code) expectError(() => CP.parseTidyCsv(v.text), v, `csv[${i}]`);
  else deepCompare(plain(CP.parseTidyCsv(v.text)), v.out, `csv[${i}]`);
});

V.csv_text.forEach((v) => deepCompare(CP.csvText(v.x), v.out, `csvText(${JSON.stringify(v.x)})`));

// Row cap, generated here to keep vectors.json small.
const big = [];
for (let k = 0; k < 50001; k++) {
  const mi = Math.floor(k / 40);
  big.push(`S${k % 40},${1960 + Math.floor(mi / 12)}-${String((mi % 12) + 1).padStart(2, "0")},1`);
}
expectError(() => CP.parseTidyCsv(big.join("\n")), { code: "too_many_rows", message: "More than 50,000 rows. Load monthly.json for long histories." }, "csv row cap");

if (failures.length) {
  console.error(`FAIL: ${failures.length} of ${checks} checks`);
  for (const f of failures.slice(0, 40)) console.error("  " + f);
  process.exit(1);
}
console.log(`parity ok: ${checks} checks (${V.summarize.length} summarize, ${V.zscore_percentile.length} z/pct, ` +
  `${V.rebase.length} rebase, ${V.combine.length} combine, ${V.movers.length} movers, ${V.format.length} format, ` +
  `${V.csv.length} csv, ${V.validate_errors.length + V.validate_ok.length} validation vectors; rel tol ${REL})`);
