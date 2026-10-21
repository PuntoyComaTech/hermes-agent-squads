import { expect, test } from "bun:test";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const POSTING = "4000000003";
const endpoint = `https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/${POSTING}`;
const cliPath = join(import.meta.dir, "../src/cli.ts");
const fixture = Bun.file(join(import.meta.dir, "fixtures/detail-closed-excerpt.html"));

async function detail(format: "json" | "plain") {
  const requests: string[] = [];
  const server = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    fetch(request) {
      requests.push(new URL(request.url).pathname);
      return new Response(fixture, { headers: { "Content-Type": "text/html" } });
    },
  });
  const dir = mkdtempSync(join(tmpdir(), "linkedin-description-"));
  const preload = join(dir, "fetch.ts");
  // Run the CLI in a fresh process. Any request other than the one posting fails before network access.
  writeFileSync(preload, `
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (input, init) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url !== ${JSON.stringify(endpoint)}) throw new Error("Unexpected fixture request");
      return originalFetch(${JSON.stringify(server.url.origin)} + new URL(url).pathname, init);
    };
  `);
  try {
    const proc = Bun.spawn([
      process.execPath, "run", "--preload", preload, cliPath,
      "detail", POSTING, "--format", format,
    ], { stdout: "pipe", stderr: "pipe" });
    const [stdout, stderr, exitCode] = await Promise.all([
      new Response(proc.stdout).text(),
      new Response(proc.stderr).text(),
      proc.exited,
    ]);
    expect(exitCode).toBe(0);
    expect(stderr).toBe("");
    expect(requests).toEqual([`/jobs-guest/jobs/api/jobPosting/${POSTING}`]);
    return stdout;
  } finally {
    server.stop(true);
    rmSync(dir, { recursive: true, force: true });
  }
}

test("detail JSON preserves paragraph and list boundaries from a captured guest response", async () => {
  const job = JSON.parse(await detail("json"));
  expect(job.description).toContain("Example Logistics needs a data analyst");
  expect(job.description).toContain("Designing and building reporting pipelines & dashboards\nDeveloping SQL models");
  expect(job.description).not.toContain("<p>");
});

test("detail plain output preserves the same description boundaries", async () => {
  const output = await detail("plain");
  expect(output).toContain("Designing and building reporting pipelines & dashboards\nDeveloping SQL models");
  expect(output).toContain("Status: CLOSED / EXPIRED");
});

test("description formatting keeps the other fields of the posting", async () => {
  const job = JSON.parse(await detail("json"));
  expect(job.id).toBe(POSTING);
  expect(job.title).toBe("Data Analyst (Lima)");
  expect(job.seniority).toBe("Mid-Senior level");
  expect(job.employmentType).toBe("Full-time");
  expect(job.isActive).toBe(false);
});
