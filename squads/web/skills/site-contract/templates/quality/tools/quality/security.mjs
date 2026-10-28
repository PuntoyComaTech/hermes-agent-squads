import { spawnSync } from "node:child_process";
import { accessSync, constants, existsSync, readFileSync } from "node:fs";
import { delimiter, isAbsolute, join } from "node:path";
import { cannotRun, run, runMain, say } from "./toolkit.mjs";

const BREW_BINS = process.env["HOMEBREW_PREFIX"]
  ? [join(process.env["HOMEBREW_PREFIX"], "bin")]
  : ["/opt/homebrew/bin", "/home/linuxbrew/.linuxbrew/bin", "/usr/local/bin"];
const SEARCH = [...(process.env["PATH"] ?? "").split(delimiter), ...BREW_BINS].filter(
  (dir) => dir !== "" && isAbsolute(dir),
);
const ALLOWED_LICENSES = new Set([
  "0BSD",
  "Apache-2.0",
  "Artistic-2.0",
  "BlueOak-1.0.0",
  "BSD-2-Clause",
  "BSD-3-Clause",
  "BSL-1.0",
  "CC-BY-3.0",
  "CC-BY-4.0",
  "CC0-1.0",
  "ISC",
  "LGPL-2.1",
  "LGPL-2.1-only",
  "LGPL-2.1-or-later",
  "LGPL-3.0",
  "LGPL-3.0-only",
  "LGPL-3.0-or-later",
  "MIT",
  "MIT-0",
  "MPL-2.0",
  "Python-2.0",
  "Unicode-3.0",
  "Unicode-DFS-2016",
  "Unlicense",
  "WTFPL",
  "Zlib",
]);
const LICENSE_ALLOW_FILE = "tools/quality/license-allow.json";
const AUDIT_LEVEL = "moderate";
const LEAKS = 3;
const PARENS = /[()]/gu;
const OR_BRANCH = /\s+OR\s+/iu;
const AND_BRANCH = /\s+AND\s+/iu;
const TRAILING_PLUS = /\+$/u;
const DIGITS = /^\d+$/u;
const VULNERABILITY = /vulnerabilit/iu;
const GITLEAKS_ARGS = ["--no-banner", "--redact", "--exit-code", String(LEAKS)];

function executable(path) {
  try {
    accessSync(path, constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

function find(name) {
  const hit = SEARCH.map((dir) => join(dir, name)).find(
    (candidate) => existsSync(candidate) && executable(candidate),
  );
  if (!hit) {
    cannotRun(`${name} is not installed: the manager runs security_tools.py ensure ${name}`);
  }
  return hit;
}

function lastLines(text) {
  return text.split("\n").slice(-25).join("\n");
}

function judgeLeaks(label, row) {
  if (row.status !== 0 && row.status !== LEAKS) {
    cannotRun(`${label}: could not scan (exit ${row.status})\n${lastLines(row.text)}`);
  }
  if (row.status === LEAKS) {
    say(`${label}: secrets found\n${lastLines(row.text)}`);
  }
  return row.status === 0;
}

function scanHistory(gitleaks) {
  if (!existsSync(".git")) {
    return true;
  }
  const commits = run("git", ["rev-list", "--count", "--all"]);
  if (commits.status !== 0 || !DIGITS.test(commits.text)) {
    cannotRun(
      `git could not list the history (exit ${commits.status})\n${lastLines(commits.text)}`,
    );
  }
  if (commits.text === "0") {
    say(
      "gitleaks (history): no commit yet, nothing to scan; the files scan covered the whole tree",
    );
    return true;
  }
  return judgeLeaks("gitleaks (history)", run(gitleaks, ["git", ".", ...GITLEAKS_ARGS]));
}

function branchShips(branch) {
  return branch
    .split(AND_BRANCH)
    .every((id) => ALLOWED_LICENSES.has(id.trim().replace(TRAILING_PLUS, "")));
}

function licenseShips(expression) {
  const text = expression.replace(PARENS, " ").trim();
  if (text === "") {
    return false;
  }
  return text.split(OR_BRANCH).some(branchShips);
}

function osvScan() {
  const osv = run(find("osv-scanner"), ["scan", "source", "--lockfile", "pnpm-lock.yaml"]);
  if (osv.status > 1) {
    cannotRun(
      `osv-scanner could not read the lockfile (exit ${osv.status})\n${lastLines(osv.text)}`,
    );
  }
  return osv;
}

function pnpmAudit() {
  const audit = run("pnpm", ["audit", "--audit-level", AUDIT_LEVEL]);
  if (audit.status !== 0 && !VULNERABILITY.test(audit.text)) {
    cannotRun(
      `pnpm audit could not reach the advisory database (exit ${audit.status})\n${lastLines(audit.text)}`,
    );
  }
  return audit;
}

function reportVulnerabilities(rows) {
  for (const [label, row] of rows) {
    if (row.status !== 0) {
      say(`${label}: known vulnerabilities\n${lastLines(row.text)}`);
    }
  }
}

function deps() {
  if (!existsSync("pnpm-lock.yaml")) {
    cannotRun("pnpm-lock.yaml is missing: run pnpm install first (osv-scanner reads the lockfile)");
  }
  const rows = [
    ["osv-scanner", osvScan()],
    ["pnpm audit", pnpmAudit()],
  ];
  reportVulnerabilities(rows);
  const clean = rows.every(([, row]) => row.status === 0);
  if (!clean) {
    say(
      "fix: python3 <site-contract>/scripts/security_fix.py --repo . installs each fix, even one younger than the release-age rule",
    );
  }
  return clean;
}

function secrets() {
  const gitleaks = find("gitleaks");
  const files = judgeLeaks("gitleaks (files)", run(gitleaks, ["dir", ".", ...GITLEAKS_ARGS]));
  return scanHistory(gitleaks) && files;
}

function listedPackages() {
  const done = spawnSync("pnpm", ["licenses", "list", "--prod", "--json"], { encoding: "utf8" });
  if (done.status !== 0) {
    cannotRun(`pnpm licenses: exit ${done.status}\n${done.stderr}`);
  }
  return JSON.parse(done.stdout || "{}");
}

function allowedPackages() {
  return existsSync(LICENSE_ALLOW_FILE) ? JSON.parse(readFileSync(LICENSE_ALLOW_FILE, "utf8")) : [];
}

function badLicenses() {
  const allow = allowedPackages();
  return Object.entries(listedPackages())
    .filter(([license]) => !licenseShips(license))
    .flatMap(([license, packages]) => packages.map((pkg) => ({ license, name: pkg.name })))
    .filter((row) => !allow.includes(row.name));
}

function licenses() {
  const bad = badLicenses();
  for (const row of bad) {
    say(
      `${row.name}: license ${row.license} cannot ship in a site bundle (an exception is a manager decision)`,
    );
  }
  return bad.length === 0;
}

const gates = { deps, licenses, secrets };

function main() {
  const gate = gates[process.argv[2] ?? ""];
  if (!gate) {
    cannotRun(`usage: security.mjs ${Object.keys(gates).join("|")}`);
  }
  process.exitCode = gate() ? 0 : 1;
}

runMain(main);
