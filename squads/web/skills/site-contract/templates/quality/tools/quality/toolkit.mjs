import { spawnSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

class QualityError extends Error {}

function readJsonFile(file, hint) {
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch (error) {
    const reason = String(error instanceof Error ? error.message : error);
    const follow = hint ? `; run: ${hint}` : "";
    cannotRun(`${file} could not be read: ${reason}${follow}`);
  }
}

function baselineFile(name) {
  return path.join(process.cwd(), "tools/quality", name);
}

function readBaseline(name, hint) {
  return readJsonFile(baselineFile(name), hint);
}

function writeBaseline(name, data) {
  writeFileSync(baselineFile(name), `${JSON.stringify(data, undefined, 2)}\n`);
}

function say(message) {
  process.stderr.write(`${message}\n`);
}

function cannotRun(message) {
  throw new QualityError(message);
}

function run(command, args, root) {
  const done = spawnSync(command, args, {
    cwd: root,
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
  });
  if (done.error) {
    cannotRun(`${command} could not run: ${done.error.message}`);
  }
  return { status: done.status, text: `${done.stdout ?? ""}${done.stderr ?? ""}`.trim() };
}

function output(command, args, root) {
  return run(command, args, root).text;
}

function jsonOrEmpty(printed, empty) {
  const text = printed.trim();
  const isJson = text.startsWith("{") || text.startsWith("[");
  try {
    return JSON.parse(isJson ? text : empty);
  } catch {
    return JSON.parse(empty);
  }
}

function runMain(main) {
  try {
    main();
  } catch (error) {
    say(String(error instanceof Error ? error.message : error));
    process.exitCode = 2;
  }
}

export {
  cannotRun,
  jsonOrEmpty,
  output,
  readBaseline,
  readJsonFile,
  run,
  runMain,
  say,
  writeBaseline,
};
