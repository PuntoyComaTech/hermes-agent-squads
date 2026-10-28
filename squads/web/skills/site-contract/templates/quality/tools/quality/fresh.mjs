import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { cannotRun, readJsonFile, runMain, say } from "./toolkit.mjs";

const ALLOW_FILE = "tools/quality/fresh-allow.json";
const MINUTE_MS = 60_000;
const RANGE_PREFIXES = ["^", "~", "workspace:", "catalog:", "link:", "file:", "npm:"];
const STABLE = /^\d+\.\d+\.\d+$/u;
const LINE_PATTERN = /(?<major>\d+)\.(?<minor>\d+)/u;
const MINIMUM_AGE = /^minimumReleaseAge:\s*(?<minutes>\d+)/mu;
const SINGLE_QUOTED = /^'(?<body>.*)'$/u;
const DOUBLE_QUOTED = /^"(?<body>.*)"$/u;
const IMPORTER_NAME = /^ {6}(?<name>\S.*):$/u;
const SPECIFIER = /^ {8}specifier: (?<spec>.+)$/u;
const TOP_LEVEL = /^\S/u;
const TWO_SPACES = /^ {2}\S/u;
const ROOT_ENTRY = /^ {2}['"]?\.['"]?:$/u;
const FOUR_SPACES = /^ {4}\S/u;
const GROUP = /^ {4}(?:dependencies|devDependencies|optionalDependencies):$/u;

function pnpmJson(args) {
  const done = spawnSync("pnpm", args, { encoding: "utf8" });
  try {
    return JSON.parse(done.stdout || "null");
  } catch {
    cannotRun(`pnpm ${args.join(" ")} gave no JSON (exit ${done.status})\n${done.stderr}`);
  }
}

function minimumAgeMs() {
  const text = existsSync("pnpm-workspace.yaml") ? readFileSync("pnpm-workspace.yaml", "utf8") : "";
  const hit = MINIMUM_AGE.exec(text);
  return hit ? Number(hit.groups.minutes) * MINUTE_MS : 0;
}

function unquote(text) {
  return text.trim().replace(SINGLE_QUOTED, "$<body>").replace(DOUBLE_QUOTED, "$<body>");
}

function readImporterLine(line, state, out) {
  const name = IMPORTER_NAME.exec(line);
  if (name) {
    state.name = unquote(name.groups.name);
    return;
  }
  const spec = SPECIFIER.exec(line);
  if (spec && state.name) {
    out.set(state.name, unquote(spec.groups.spec));
  }
}

function readLockLine(line, state, out) {
  if (TOP_LEVEL.test(line) || TWO_SPACES.test(line)) {
    state.root = ROOT_ENTRY.test(line);
    state.group = false;
  } else if (state.root && FOUR_SPACES.test(line)) {
    state.group = GROUP.test(line);
  } else if (state.root && state.group) {
    readImporterLine(line, state, out);
  }
}

function lockedSpecifiers() {
  if (!existsSync("pnpm-lock.yaml")) {
    cannotRun("pnpm-lock.yaml is missing: run pnpm install first");
  }
  const out = new Map();
  const state = { group: false, name: "", root: false };
  for (const line of readFileSync("pnpm-lock.yaml", "utf8").split("\n")) {
    readLockLine(line, state, out);
  }
  return out;
}

function directDependencies() {
  const pkg = readJsonFile("package.json", "pnpm install");
  return {
    ...(pkg.dependencies ?? {}),
    ...(pkg.devDependencies ?? {}),
    ...(pkg.optionalDependencies ?? {}),
  };
}

function releaseLine(version) {
  const parts = LINE_PATTERN.exec(String(version));
  if (!parts) {
    return null;
  }
  return parts.groups.major === "0" ? `0.${parts.groups.minor}` : parts.groups.major;
}

function lineValue(text) {
  return text.startsWith("0.") ? Number(text.slice(2)) / 1000 : Number(text);
}

function newestMatureLine(name, ageMs) {
  const times = pnpmJson(["view", name, "time", "--json"]) ?? {};
  const cutoff = Date.now() - ageMs;
  const lines = Object.entries(times)
    .filter(([version, stamp]) => STABLE.test(version) && Date.parse(stamp) <= cutoff)
    .map(([version]) => releaseLine(version));
  return lines.reduce(
    (best, next) => (best === null || lineValue(next) > lineValue(best) ? next : best),
    null,
  );
}

function findSyncAndRange(declared, locked, allow) {
  const findings = [];
  for (const [name, spec] of Object.entries(declared)) {
    if (locked.get(name) !== spec) {
      findings.push({
        detail: `package.json says ${spec}, the lockfile ${locked.get(name) ?? "nothing"}: add it with pnpm add ${name}`,
        kind: "not-resolved",
        name,
      });
    } else if (!(name in allow || RANGE_PREFIXES.some((prefix) => spec.startsWith(prefix)))) {
      findings.push({
        detail: `${spec} is pinned: pnpm add ${name} writes a ^ range`,
        kind: "exact-pin",
        name,
      });
    }
  }
  return findings;
}

function behindFinding([name, row], allow, ageMs) {
  const current = releaseLine(row.current ?? row.wanted);
  if (current === null || name in allow || releaseLine(row.latest) === current) {
    return null;
  }
  const mature = newestMatureLine(name, ageMs);
  if (mature === null || lineValue(mature) <= lineValue(current)) {
    return null;
  }
  return {
    current,
    detail: `on ${current}, the newest line is ${mature}: pnpm add ${name}@${mature}`,
    kind: "behind",
    mature,
    name,
  };
}

function findBehind(allow, ageMs) {
  const outdated = pnpmJson(["outdated", "--format", "json"]) ?? {};
  return Object.entries(outdated)
    .map((entry) => behindFinding(entry, allow, ageMs))
    .filter((finding) => finding !== null);
}

function readAllow() {
  const allow = existsSync(ALLOW_FILE) ? readJsonFile(ALLOW_FILE, "") : {};
  const unexplained = Object.entries(allow).filter(
    ([, reason]) => typeof reason !== "string" || reason.trim() === "",
  );
  if (unexplained.length > 0) {
    cannotRun(
      `${ALLOW_FILE}: every exception needs its reason (${unexplained.map(([name]) => name).join(", ")})`,
    );
  }
  return allow;
}

function findingsOf(allow, ageMs) {
  return [
    ...findSyncAndRange(directDependencies(), lockedSpecifiers(), allow),
    ...findBehind(allow, ageMs),
  ];
}

function main() {
  const findings = findingsOf(readAllow(), minimumAgeMs());
  if (process.argv.includes("--json")) {
    process.stdout.write(`${JSON.stringify(findings)}\n`);
  }
  for (const row of findings) {
    say(`${row.name}: ${row.detail}`);
  }
  if (findings.length > 0) {
    process.exitCode = 1;
  }
}

runMain(main);
