import { readFileSync } from "node:fs";
import { cannotRun, output, readBaseline, runMain, say, writeBaseline } from "./toolkit.mjs";

const GATES = ["clones", "depcruise", "knip"];
const ROOT = process.cwd();
const BASELINE = "regression-baseline.json";
const RECORD_HINT = "node tools/quality/regressions.mjs record";
const JSCPD = "node_modules/.bin/jscpd";
const JSCPD_CONFIGS = [".jscpd.json", ".jscpd-css.json"];
const KNIP = "node_modules/.bin/knip";
const DEPCRUISE = "tools/quality/node_modules/.bin/depcruise";
const DEPCRUISE_ARGS = ["src", "--config", "tools/quality/dependency-cruiser.cjs", "-T", "json"];
const CLONES_PATTERN = /Found (?<count>\d+) clones/u;
const KNIP_SECTION_PATTERN = /^[A-Z][^\n()]*\((?<count>\d+)\)$/gmu;

function clonesOf(printed) {
  return Number(CLONES_PATTERN.exec(printed)?.groups?.["count"] ?? 0);
}

function knipIssuesOf(printed) {
  let total = 0;
  for (const section of printed.matchAll(KNIP_SECTION_PATTERN)) {
    total += Number(section.groups?.["count"]);
  }
  return total;
}

function depcruiseErrorsOf(printed) {
  const report = JSON.parse(printed.trim().startsWith("{") ? printed : '{"summary":{"error":0}}');
  return report.summary?.error ?? 0;
}

function cloneTotal() {
  const configs = JSCPD_CONFIGS.filter((config) => {
    try {
      readFileSync(`${ROOT}/${config}`, "utf8");
      return true;
    } catch {
      return false;
    }
  });
  return configs
    .map((config) => clonesOf(output(JSCPD, ["--config", config], ROOT)))
    .reduce((sum, count) => sum + count, 0);
}

function measure() {
  return {
    clones: cloneTotal(),
    depcruise: depcruiseErrorsOf(output(DEPCRUISE, DEPCRUISE_ARGS, ROOT)),
    knip: knipIssuesOf(output(KNIP, [], ROOT)),
  };
}

function parseTotals(totals) {
  for (const gate of GATES) {
    if (!Number.isInteger(totals[gate]) || totals[gate] < 0) {
      cannotRun(`${BASELINE}: ${gate} must be a non-negative integer`);
    }
  }
  return totals;
}

function record() {
  const totals = measure();
  writeBaseline(BASELINE, totals);
  say(`Regression baseline: ${JSON.stringify(totals)}`);
}

function check() {
  const baseline = parseTotals(readBaseline(BASELINE, RECORD_HINT));
  const current = measure();
  const regressed = GATES.filter((gate) => current[gate] > baseline[gate]);
  for (const gate of regressed) {
    say(`${gate}: ${current[gate]} > ${baseline[gate]}`);
  }
  if (regressed.length > 0) {
    say("A quality total rose above its recorded baseline.");
    process.exitCode = 1;
  }
}

function main() {
  const [, , mode] = process.argv;
  if (mode === "record") {
    record();
  } else if (mode === "check") {
    check();
  } else {
    cannotRun("Usage: node tools/quality/regressions.mjs record | check");
  }
}

runMain(main);
