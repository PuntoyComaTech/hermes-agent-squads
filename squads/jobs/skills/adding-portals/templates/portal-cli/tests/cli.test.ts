import { describe, expect, test } from "bun:test"
import { join } from "node:path"

// Offline tests: a loopback server stands in for the board. Nothing here reaches the network.
const CLI = join(import.meta.dir, "../src/cli.ts")

interface Captured {
  urls: URL[]
}

function serve(body: unknown, captured: Captured) {
  return Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    fetch(request) {
      captured.urls.push(new URL(request.url))
      return Response.json(body)
    },
  })
}

async function run(args: string[], base?: string) {
  const proc = Bun.spawn([process.execPath, "run", CLI, ...args], {
    stdout: "pipe",
    stderr: "pipe",
    env: { ...process.env, ...(base ? { EXAMPLE_BOARD_API_URL: base } : {}) },
  })
  const [stdout, stderr, exitCode] = await Promise.all([
    new Response(proc.stdout).text(),
    new Response(proc.stderr).text(),
    proc.exited,
  ])
  return { stdout: stdout.trim(), stderr: stderr.trim(), exitCode }
}

const FIXTURE = {
  data: [
    {
      id: "100",
      title: "Data Analyst &amp; BI ",
      company: "Acme",
      location: "Lima, Peru",
      posted_at: "2026-10-14T00:00:00Z",
      url: "https://jobs.acme.example/100",
    },
  ],
  meta: { total: 1 },
}

describe("search", () => {
  test("prints the portal contract envelope with a decoded title and a date", async () => {
    const captured: Captured = { urls: [] }
    const server = serve(FIXTURE, captured)
    try {
      const result = await run(["search", "-q", "analyst", "--limit", "5"], server.url.origin)
      expect(result.exitCode).toBe(0)
      const out = JSON.parse(result.stdout)
      expect(out.meta).toEqual({ count: 1, page: 1, total: 1 })
      expect(out.results[0]).toEqual({
        id: "100",
        title: "Data Analyst & BI",
        company: "Acme",
        location: "Lima, Peru",
        date: "2026-10-14",
        url: "https://jobs.acme.example/100",
      })
      expect(captured.urls[0].searchParams.get("q")).toBe("analyst")
      expect(captured.urls[0].searchParams.get("limit")).toBe("5")
    } finally {
      server.stop(true)
    }
  })

  test("--jobage maps to the board's posted-within parameter", async () => {
    const captured: Captured = { urls: [] }
    const server = serve({ data: [], meta: { total: 0 } }, captured)
    try {
      const result = await run(["search", "-q", "analyst", "--jobage", "14"], server.url.origin)
      expect(result.exitCode).toBe(0)
      expect(captured.urls[0].searchParams.get("posted_within_days")).toBe("14")
    } finally {
      server.stop(true)
    }
  })

  test("a missing query exits 1 with BAD_ARG before any request", async () => {
    const captured: Captured = { urls: [] }
    const server = serve(FIXTURE, captured)
    try {
      const result = await run(["search"], server.url.origin)
      expect(result.exitCode).toBe(1)
      expect(JSON.parse(result.stderr).code).toBe("BAD_ARG")
      expect(captured.urls).toHaveLength(0)
    } finally {
      server.stop(true)
    }
  })

  test("an unknown flag exits 1 with UNKNOWN_FLAG and no stdout", async () => {
    const result = await run(["search", "-q", "analyst", "--bogus", "x"])
    expect(result.exitCode).toBe(1)
    expect(result.stdout).toBe("")
    expect(JSON.parse(result.stderr).code).toBe("UNKNOWN_FLAG")
  })
})

describe("detail", () => {
  test("reads a bare id and returns a cleaned description", async () => {
    const captured: Captured = { urls: [] }
    const server = serve(
      { data: { ...FIXTURE.data[0], description: "<p>Build reports</p><ul><li>SQL &amp; Python</li></ul>" } },
      captured,
    )
    try {
      const result = await run(["detail", "100"], server.url.origin)
      expect(result.exitCode).toBe(0)
      const job = JSON.parse(result.stdout)
      expect(job.description).toBe("Build reports\nSQL & Python")
      expect(captured.urls[0].pathname).toBe("/api/jobs/100")
    } finally {
      server.stop(true)
    }
  })

  test("a URL on another host is rejected with BAD_ID before any request", async () => {
    const captured: Captured = { urls: [] }
    const server = serve(FIXTURE, captured)
    try {
      const result = await run(["detail", "https://jobs.other.example/jobs/100"], server.url.origin)
      expect(result.exitCode).toBe(1)
      expect(JSON.parse(result.stderr).code).toBe("BAD_ID")
      expect(captured.urls).toHaveLength(0)
    } finally {
      server.stop(true)
    }
  })
})
