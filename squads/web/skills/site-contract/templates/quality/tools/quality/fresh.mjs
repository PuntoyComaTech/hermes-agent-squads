// Versions gate of the strict base: every direct dependency arrived through `pnpm add` and sits on the newest major
// that is old enough to install. It catches a version typed from memory: an old major, an exact pin, or a line in
// package.json that pnpm never resolved. Written by site_base.py; workers never relax it.
// node tools/quality/fresh.mjs [--json]   (exit 0 current, 1 findings, 2 could not check)
// An exception is a manager decision: tools/quality/fresh-allow.json maps a package to the reason it stays behind.
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";

const ALLOW_FILE = "tools/quality/fresh-allow.json";
const MINUTE_MS = 60_000;
// pnpm add writes ^ (and ~ for a 0.x line); the rest are local or aliased packages
const RANGE_PREFIXES = ["^", "~", "workspace:", "catalog:", "link:", "file:", "npm:"];

function say(message) {
  process.stderr.write(`${message}\n`);
}

function cannotRun(message) {
  say(message);
  process.exit(2);
}

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    return cannotRun(`${path} could not be read: ${error.message}`);
  }
}

function pnpmJson(args) {
  const done = spawnSync("pnpm", args, { encoding: "utf8" });
  try {
    return JSON.parse(done.stdout || "null");
  } catch {
    return cannotRun(`pnpm ${args.join(" ")} gave no JSON (exit ${done.status})\n${done.stderr}`);
  }
}

// the age pnpm enforces here: minimumReleaseAge (minutes) in pnpm-workspace.yaml
function minimumAgeMs() {
  const text = existsSync("pnpm-workspace.yaml") ? readFileSync("pnpm-workspace.yaml", "utf8") : "";
  const hit = /^minimumReleaseAge:\s*(\d+)/m.exec(text);
  return hit ? Number(hit[1]) * MINUTE_MS : 0;
}

function unquote(text) {
  return text.trim().replace(/^'(.*)'$/, "$1");
}

// one lockfile line in the root importer: a package name (6 spaces) or its specifier (8 spaces)
function readImporterLine(line, state, out) {
  const name = /^ {6}(\S.*):$/.exec(line);
  if (name) {
    state.name = unquote(name[1]);
    return;
  }
  const spec = /^ {8}specifier: (.+)$/.exec(line);
  if (spec && state.name) {
    out.set(state.name, unquote(spec[1]));
  }
}

// name -> specifier of the root importer's dependencies (pnpm 9+ lockfiles, one or two YAML documents)
function lockedSpecifiers() {
  if (!existsSync("pnpm-lock.yaml")) {
    cannotRun("pnpm-lock.yaml is missing: run pnpm install first");
  }
  const out = new Map();
  const state = { root: false, group: false, name: "" };
  for (const line of readFileSync("pnpm-lock.yaml", "utf8").split("\n")) {
    readLockLine(line, state, out);
  }
  return out;
}

// where a lockfile line sits: a top section or importer (resets), a dependency group, or a package inside one
function readLockLine(line, state, out) {
  if (/^\S/.test(line) || /^ {2}\S/.test(line)) {
    state.root = /^ {2}(\.|'\.'):$/.test(line);
    state.group = false;
  } else if (state.root && /^ {4}\S/.test(line)) {
    state.group = /^ {4}(dependencies|devDependencies|optionalDependencies):$/.test(line);
  } else if (state.root && state.group) {
    readImporterLine(line, state, out);
  }
}

function directDependencies() {
  const pkg = readJson("package.json");
  return { ...(pkg.dependencies ?? {}), ...(pkg.devDependencies ?? {}), ...(pkg.optionalDependencies ?? {}) };
}

// the compatible line of a version: its major, or 0.<minor> for a 0.x package
function line(version) {
  const parts = /(\d+)\.(\d+)/.exec(String(version));
  if (!parts) {
    return null;
  }
  return parts[1] === "0" ? `0.${parts[2]}` : parts[1];
}

function lineValue(text) {
  return text.startsWith("0.") ? Number(text.slice(2)) / 1000 : Number(text);
}

// the newest line with a stable release at least `ageMs` old
function newestMatureLine(name, ageMs) {
  const times = pnpmJson(["view", name, "time", "--json"]) ?? {};
  const cutoff = Date.now() - ageMs;
  const lines = Object.entries(times)
    .filter(([version, stamp]) => /^\d+\.\d+\.\d+$/.test(version) && Date.parse(stamp) <= cutoff)
    .map(([version]) => line(version));
  return lines.reduce((best, next) => (best === null || lineValue(next) > lineValue(best) ? next : best), null);
}

function findSyncAndRange(declared, locked, allow) {
  const findings = [];
  for (const [name, spec] of Object.entries(declared)) {
    if (locked.get(name) !== spec) {
      findings.push({ name, kind: "not-resolved", detail: `package.json says ${spec}, the lockfile ${locked.get(name) ?? "nothing"}: add it with pnpm add ${name}` });
    } else if (!(name in allow) && !RANGE_PREFIXES.some((prefix) => spec.startsWith(prefix))) {
      findings.push({ name, kind: "exact-pin", detail: `${spec} is pinned: pnpm add ${name} writes a ^ range` });
    }
  }
  return findings;
}

function findBehind(allow, ageMs) {
  const outdated = pnpmJson(["outdated", "--format", "json"]) ?? {};
  const findings = [];
  for (const [name, row] of Object.entries(outdated)) {
    const current = line(row.current ?? row.wanted);
    if (name in allow || current === null || line(row.latest) === current) {
      continue;
    }
    const mature = newestMatureLine(name, ageMs);
    if (mature !== null && lineValue(mature) > lineValue(current)) {
      findings.push({ name, kind: "behind", current, mature, detail: `on ${current}, the newest line is ${mature}: pnpm add ${name}@${mature}` });
    }
  }
  return findings;
}

function readAllow() {
  const allow = existsSync(ALLOW_FILE) ? readJson(ALLOW_FILE) : {};
  const unexplained = Object.entries(allow).filter(([, reason]) => typeof reason !== "string" || reason.trim() === "");
  if (unexplained.length > 0) {
    cannotRun(`${ALLOW_FILE}: every exception needs its reason (${unexplained.map(([name]) => name).join(", ")})`);
  }
  return allow;
}

const allow = readAllow();
const findings = [
  ...findSyncAndRange(directDependencies(), lockedSpecifiers(), allow),
  ...findBehind(allow, minimumAgeMs()),
];
if (process.argv.includes("--json")) {
  process.stdout.write(`${JSON.stringify(findings)}\n`);
}
for (const row of findings) {
  say(`${row.name}: ${row.detail}`);
}
process.exit(findings.length === 0 ? 0 : 1);
