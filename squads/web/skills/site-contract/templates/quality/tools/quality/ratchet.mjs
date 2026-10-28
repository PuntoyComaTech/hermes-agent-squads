import { readFileSync } from "node:fs";
import path from "node:path";
import { parse } from "@babel/parser";
import {
  cannotRun,
  jsonOrEmpty,
  output,
  readBaseline,
  runMain,
  say,
  writeBaseline,
} from "./toolkit.mjs";

const ROOT = process.cwd();
const BASELINE = "baseline.json";
const RECORD_HINT = "node tools/quality/ratchet.mjs record";
const CODE_FILE = /\.(?:ts|tsx|mts|cts|js|jsx|mjs|cjs)$/u;
const DECLARATION = /[.]d[.]ts$/u;
const GENERATED = /[.]gen[.]ts$/u;
const VENDORED = /(?:^|\/)(?:node_modules|dist|coverage)\//u;
const TYPE_ERROR = /^(?<file>[^(]+)\(\d+,\d+\): error TS\d+/u;
const TSC = "node_modules/.bin/tsc";
const BIOME = "node_modules/.bin/biome";
const OXLINT = "node_modules/.bin/oxlint";
const ESLINT = "tools/quality/node_modules/.bin/eslint";
const ESLINT_CONFIG = "tools/quality/eslint.config.mjs";
const TOOLS = ["biome", "comments", "oxlint", "sonar", "types"];
const NO_FINDINGS = { biome: 0, comments: 0, oxlint: 0, sonar: 0, types: 0 };
const EMPTY_BIOME = '{"diagnostics":[]}';
const EMPTY_ESLINT = "[]";

function tally(files) {
  const counts = new Map();
  for (const file of files) {
    counts.set(file, (counts.get(file) ?? 0) + 1);
  }
  return counts;
}

function biomeCounts(targets) {
  const args = [
    "check",
    "--reporter=json",
    "--max-diagnostics=none",
    "--no-errors-on-unmatched",
    ...targets,
  ];
  const report = jsonOrEmpty(output(BIOME, args, ROOT), EMPTY_BIOME);
  return tally(
    (report.diagnostics ?? []).flatMap((item) =>
      item.location?.path ? [relative(item.location.path)] : [],
    ),
  );
}

function oxlintCounts(targets) {
  if (targets.length === 0) {
    return new Map();
  }
  const args = [
    "--format=json",
    "--config=tools/quality/oxlintrc.json",
    "--ignore-pattern",
    "**/*.gen.ts",
    "--ignore-pattern",
    "src/paraglide/**",
    ...targets,
  ];
  const report = jsonOrEmpty(output(OXLINT, args, ROOT), EMPTY_BIOME);
  return tally((report.diagnostics ?? []).map((item) => relative(item.filename)));
}

function sonarCounts(targets) {
  const args = ["--config", ESLINT_CONFIG, "--format", "json", "--no-warn-ignored", ...targets];
  const report = jsonOrEmpty(output(ESLINT, args, ROOT), EMPTY_ESLINT);
  return new Map(report.map((item) => [relative(item.filePath), (item.messages ?? []).length]));
}

function typeFiles() {
  const printed = output(TSC, ["--noEmit", "--pretty", "false", "-p", "tsconfig.json"], ROOT);
  return printed
    .split("\n")
    .map((line) => TYPE_ERROR.exec(line.trim())?.groups?.["file"])
    .filter((file) => file !== undefined)
    .map(relative);
}

function commentCount(file) {
  const source = readFileSync(path.join(ROOT, file), "utf8");
  const plugins = file.endsWith("x") ? ["typescript", "jsx"] : ["typescript"];
  const program = parse(source, { errorRecovery: true, plugins, sourceType: "module" });
  return program.comments?.length ?? 0;
}

function relative(file) {
  return path.relative(ROOT, path.resolve(ROOT, file));
}

function codeFiles(targets) {
  return output("git", ["ls-files", "--cached", "--others", "--exclude-standard", ...targets], ROOT)
    .split("\n")
    .filter(
      (file) =>
        CODE_FILE.test(file) &&
        !DECLARATION.test(file) &&
        !GENERATED.test(file) &&
        !VENDORED.test(file),
    );
}

function countsOf(file, tallies) {
  return {
    biome: tallies.biome.get(file) ?? 0,
    comments: tallies.comments.get(file) ?? 0,
    oxlint: tallies.oxlint.get(file) ?? 0,
    sonar: tallies.sonar.get(file) ?? 0,
    types: tallies.types.get(file) ?? 0,
  };
}

function oxlintScope(files) {
  return files.filter((file) => file.startsWith("src/") || file.startsWith("e2e/"));
}

function measure(targets) {
  const code = codeFiles(targets);
  const tallies = {
    biome: biomeCounts(targets),
    comments: new Map(code.map((file) => [relative(file), commentCount(file)])),
    oxlint: oxlintCounts(oxlintScope(code)),
    sonar: code.length > 0 ? sonarCounts(code) : new Map(),
    types: tally(typeFiles()),
  };
  const files = new Set(TOOLS.flatMap((tool) => [...tallies[tool].keys()]));
  return new Map([...files].map((file) => [file, countsOf(file, tallies)]));
}

function record(zero) {
  const measured = zero ? new Map() : measure([]);
  const withFindings = [...measured.entries()].filter(([, counts]) =>
    TOOLS.some((tool) => counts[tool] > 0),
  );
  const entries = Object.fromEntries(withFindings);
  writeBaseline(BASELINE, entries);
  say(
    `Baseline written for ${Object.keys(entries).length} files${zero ? " (zero: a new repo starts at zero)" : ""}.`,
  );
}

function worseThan(measured, baseline) {
  const worse = [];
  for (const [file, found] of measured) {
    const allowed = baseline[file] ?? NO_FINDINGS;
    for (const tool of TOOLS) {
      if (found[tool] > allowed[tool]) {
        worse.push(`${file}: ${tool} ${found[tool]} > ${allowed[tool]}`);
      }
    }
  }
  return worse;
}

function check(targets) {
  const worse = worseThan(measure(targets), readBaseline(BASELINE, RECORD_HINT));
  for (const line of worse) {
    say(line);
  }
  if (worse.length > 0) {
    say(
      "A new file has zero findings and zero comments; a touched file never exceeds its baseline.",
    );
    process.exitCode = 1;
  }
}

function main() {
  const [mode, ...paths] = process.argv.slice(2);
  if (mode === "record") {
    record(paths.includes("--zero"));
  } else if (mode === "check") {
    check(paths.filter((arg) => !arg.startsWith("--")));
  } else {
    cannotRun("Usage: node tools/quality/ratchet.mjs record [--zero] | check [files...]");
  }
}

runMain(main);
