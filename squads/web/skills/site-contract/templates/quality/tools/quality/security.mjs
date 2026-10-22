// Security gates of the strict base: dependencies, secrets, licenses. Written by site_base.py; workers never relax it.
// node tools/quality/security.mjs deps|secrets|licenses   (exit 0 clean, 1 findings, 2 a scanner could not run)
// "Could not run" is never "clean": a missing lockfile, an empty history or a scanner error exits 2.
import { spawnSync } from "node:child_process";
import { accessSync, constants, existsSync, readFileSync } from "node:fs";
import { delimiter, isAbsolute, join } from "node:path";

// absolute folders only: an empty or relative PATH entry would run a file of that name committed in the repo
// the scanners come from Homebrew (security_tools.py): its bin folder is searched even on a bare PATH, from
// HOMEBREW_PREFIX (what `brew shellenv` exports) or else Homebrew's default prefixes
const BREW_BINS = process.env.HOMEBREW_PREFIX
  ? [join(process.env.HOMEBREW_PREFIX, "bin")]
  : ["/opt/homebrew/bin", "/home/linuxbrew/.linuxbrew/bin", "/usr/local/bin"];
const SEARCH = [...(process.env.PATH ?? "").split(delimiter), ...BREW_BINS].filter(
  (dir) => dir !== "" && isAbsolute(dir),
);
// default deny: only these licenses ship in a site bundle. Copyleft (GPL, AGPL), source-available (SSPL, BUSL,
// Elastic, PolyForm, Commons Clause), non-commercial or no-derivatives, custom ("SEE LICENSE IN") and unknown fail.
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
// pnpm audit fails on this level and above; osv-scanner fails on any known vulnerability or malicious package
const AUDIT_LEVEL = "moderate";
const LEAKS = 3;

function say(message) {
  process.stderr.write(`${message}\n`);
}

function cannotRun(message) {
  say(message);
  process.exit(2);
}

function executable(path) {
  try {
    accessSync(path, constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

function find(name) {
  const hit = SEARCH.map((dir) => join(dir, name)).find((candidate) => existsSync(candidate) && executable(candidate));
  if (!hit) {
    cannotRun(`${name} is not installed: the manager runs security_tools.py ensure ${name}`);
  }
  return hit;
}

function run(command, args) {
  const done = spawnSync(command, args, { encoding: "utf8" });
  if (done.error || done.status === null) {
    cannotRun(`${command}: could not run (${done.error?.message ?? "killed"})`);
  }
  return { status: done.status, text: `${done.stdout ?? ""}${done.stderr ?? ""}`.trim() };
}

function lastLines(text) {
  return text.split("\n").slice(-25).join("\n");
}

// one gitleaks run: true when clean, false on leaks; a scanner error never returns
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
  if (commits.status !== 0 || !/^\d+$/.test(commits.text)) {
    cannotRun(`git could not list the history (exit ${commits.status})\n${lastLines(commits.text)}`);
  }
  if (commits.text === "0") {
    // nothing committed yet: there is no history to leak from, and the files scan above read everything
    say("gitleaks (history): no commit yet, nothing to scan; the files scan covered the whole tree");
    return true;
  }
  return judgeLeaks("gitleaks (history)", run(gitleaks, ["git", ".", "--no-banner", "--redact", "--exit-code", String(LEAKS)]));
}

// one SPDX expression: "(MIT OR GPL-3.0)" ships under MIT; "(MIT AND GPL-3.0)" needs both
function licenseShips(expression) {
  const text = expression.replace(/[()]/g, " ").trim();
  if (text === "") {
    return false;
  }
  return text
    .split(/\s+OR\s+/i)
    .some((branch) => branch.split(/\s+AND\s+/i).every((id) => ALLOWED_LICENSES.has(id.trim().replace(/\+$/, ""))));
}

const gates = {
  deps() {
    if (!existsSync("pnpm-lock.yaml")) {
      cannotRun("pnpm-lock.yaml is missing: run pnpm install first (osv-scanner reads the lockfile)");
    }
    const osv = run(find("osv-scanner"), ["scan", "source", "--lockfile", "pnpm-lock.yaml"]);
    if (osv.status > 1) {
      cannotRun(`osv-scanner could not read the lockfile (exit ${osv.status})\n${lastLines(osv.text)}`);
    }
    const audit = run("pnpm", ["audit", "--audit-level", AUDIT_LEVEL]);
    if (audit.status !== 0 && !/vulnerabilit/i.test(audit.text)) {
      cannotRun(`pnpm audit could not reach the advisory database (exit ${audit.status})\n${lastLines(audit.text)}`);
    }
    for (const [label, row] of [
      ["osv-scanner", osv],
      ["pnpm audit", audit],
    ]) {
      if (row.status !== 0) {
        say(`${label}: known vulnerabilities\n${lastLines(row.text)}`);
      }
    }
    const clean = osv.status === 0 && audit.status === 0;
    if (!clean) {
      say("fix: python3 <site-contract>/scripts/security_fix.py --repo . installs each fix, even one younger than the release-age rule");
    }
    return clean;
  },
  secrets() {
    const gitleaks = find("gitleaks");
    // gitleaks also exits 1 on a fatal error, so leaks get their own exit code
    const files = judgeLeaks("gitleaks (files)", run(gitleaks, ["dir", ".", "--no-banner", "--redact", "--exit-code", String(LEAKS)]));
    const history = scanHistory(gitleaks);
    return files && history;
  },
  licenses() {
    const done = spawnSync("pnpm", ["licenses", "list", "--prod", "--json"], { encoding: "utf8" });
    if (done.status !== 0) {
      cannotRun(`pnpm licenses: exit ${done.status}\n${done.stderr}`);
    }
    const allow = existsSync(LICENSE_ALLOW_FILE) ? JSON.parse(readFileSync(LICENSE_ALLOW_FILE, "utf8")) : [];
    const bad = Object.entries(JSON.parse(done.stdout || "{}"))
      .filter(([license]) => !licenseShips(license))
      .flatMap(([license, packages]) => packages.map((pkg) => ({ license, name: pkg.name })))
      .filter((row) => !allow.includes(row.name));
    for (const row of bad) {
      say(`${row.name}: license ${row.license} cannot ship in a site bundle (an exception is a manager decision)`);
    }
    return bad.length === 0;
  },
};

const gate = gates[process.argv[2] ?? ""];
if (!gate) {
  cannotRun(`usage: security.mjs ${Object.keys(gates).join("|")}`);
}
process.exit(gate() ? 0 : 1);
