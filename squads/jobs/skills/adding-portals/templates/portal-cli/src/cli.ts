#!/usr/bin/env bun
// Portal CLI template. Copy this directory to scripts/<portal-name>/, rename it, and replace the example
// host, endpoints and field names after investigating the real board. Zero runtime dependencies: bun runs it.
// It follows the portal contract: `search` and `detail`, one JSON envelope on stdout, errors on stderr as
// {"error","code"} with exit 1, backoff on 429 and 5xx, and no credentials on the command line.

const BASE_URL = (process.env.EXAMPLE_BOARD_API_URL ?? "https://board.example").replace(/\/+$/, "")
const HOSTS = ["board.example"]
const UA = "example-board-cli/1.0"
const MAX_RETRIES = 6
const FORMATS = ["json", "table", "plain"]

interface Row {
  id: string
  title: string
  company: string | null
  location: string | null
  date: string | null
  url: string
  description?: string | null
}

class CliError extends Error {
  constructor(message: string, readonly code: string) {
    super(message)
  }
}

const ALIAS: Record<string, string> = { q: "query", n: "limit" }
const KNOWN: Record<string, Set<string>> = {
  search: new Set(["query", "jobage", "limit", "page", "format", "help"]),
  detail: new Set(["format", "help"]),
}

function fail(error: string, code: string): number {
  process.stderr.write(JSON.stringify({ error, code }) + "\n")
  return 1
}

function parseArgs(argv: string[]): { positional: string[]; flags: Map<string, string | true> } {
  const positional: string[] = []
  const flags = new Map<string, string | true>()
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i]
    if (!arg.startsWith("-")) {
      positional.push(arg)
      continue
    }
    const raw = arg.replace(/^-+/, "")
    const key = ALIAS[raw] ?? raw
    const next = argv[i + 1]
    if (next === undefined || next.startsWith("-")) flags.set(key, true)
    else {
      flags.set(key, next)
      i++
    }
  }
  return { positional, flags }
}

function wholeNumber(name: string, raw: string | true | undefined, fallback: number): number {
  if (raw === undefined) return fallback
  const value = typeof raw === "string" ? Number(raw.trim()) : NaN
  if (!Number.isInteger(value) || value < 1) {
    throw new CliError(`--${name} must be a whole number of at least 1, got "${raw}"`, "BAD_ARG")
  }
  return value
}

function decodeEntities(text: string): string {
  return text
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&amp;/g, "&")
}

function cleanHtml(html: string): string {
  const text = html.replace(/<br\s*\/?>/gi, "\n").replace(/<\/(p|li|div|h\d)>/gi, "\n").replace(/<[^>]+>/g, " ")
  return decodeEntities(text)
    .split("\n")
    .map((line) => line.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .join("\n")
}

// Replace these field names with the board's own after capturing a real response.
function toRow(job: Record<string, unknown>): Row {
  const posted = typeof job.posted_at === "string" ? /^\d{4}-\d{2}-\d{2}/.exec(job.posted_at) : null
  return {
    id: String(job.id ?? ""),
    title: decodeEntities(String(job.title ?? "")).trim() || "(untitled)",
    company: typeof job.company === "string" && job.company.trim() ? job.company.trim() : null,
    location: typeof job.location === "string" && job.location.trim() ? job.location.trim() : null,
    date: posted ? posted[0] : null,
    url: String(job.url ?? ""),
  }
}

async function getJson(path: string, params: URLSearchParams): Promise<{ data: unknown; meta?: Record<string, unknown> } | null> {
  const url = `${BASE_URL}${path}${params.toString() ? `?${params}` : ""}`
  let delay = 500
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    let response: Response
    try {
      response = await fetch(url, {
        headers: { "User-Agent": UA, Accept: "application/json" },
        signal: AbortSignal.timeout(15000),
      })
    } catch (e) {
      throw new CliError(`could not reach ${BASE_URL} (${e instanceof Error ? e.message : String(e)})`, "UNREACHABLE")
    }
    if (response.status === 429 || response.status >= 500) {
      if (attempt === MAX_RETRIES) throw new CliError(`request failed: ${response.status} ${response.statusText}`, "SEARCH_FAILED")
      await new Promise((r) => setTimeout(r, delay + Math.floor(Math.random() * 500)))
      delay = Math.min(delay * 2, 8000)
      continue
    }
    if (response.status === 404) return null
    if (!response.ok) throw new CliError(`request failed: ${response.status} ${response.statusText}`, "SEARCH_FAILED")
    return (await response.json()) as { data: unknown; meta?: Record<string, unknown> }
  }
  throw new CliError("request failed after retries", "SEARCH_FAILED")
}

async function search(flags: Map<string, string | true>): Promise<number> {
  const query = flags.get("query")
  if (typeof query !== "string" || !query.trim()) throw new CliError("--query is required", "BAD_ARG")
  const format = String(flags.get("format") ?? "json")
  if (!FORMATS.includes(format)) throw new CliError(`--format must be one of json|table|plain, got "${format}"`, "BAD_ARG")
  const limit = wholeNumber("limit", flags.get("limit"), 25)
  const page = wholeNumber("page", flags.get("page"), 1)
  const params = new URLSearchParams({ q: query, limit: String(limit), offset: String((page - 1) * limit) })
  if (flags.has("jobage")) params.set("posted_within_days", String(wholeNumber("jobage", flags.get("jobage"), 0)))

  const envelope = await getJson("/api/jobs", params)
  if (!envelope) throw new CliError("search endpoint not found", "SEARCH_FAILED")
  const rows = (Array.isArray(envelope.data) ? envelope.data : []).map((j) => toRow(j as Record<string, unknown>))
  const total = typeof envelope.meta?.total === "number" ? envelope.meta.total : rows.length

  if (format === "json") {
    process.stdout.write(JSON.stringify({ meta: { count: rows.length, page, total }, results: rows }, null, 2) + "\n")
  } else if (format === "table") {
    for (const r of rows) process.stdout.write(`${r.id}  ${r.title}  ${r.company ?? "-"}  ${r.location ?? "-"}  ${r.date ?? "-"}\n`)
  } else {
    for (const r of rows) process.stdout.write(`${r.title}\n  ${r.company ?? "-"} · ${r.location ?? "-"} · ${r.date ?? "-"}\n  id: ${r.id}\n  ${r.url}\n\n`)
  }
  return 0
}

// Accept a bare id or a URL on one of this board's own hosts. Any other host is rejected before a request.
function detailId(input: string): string | null {
  const trimmed = input.trim()
  if (/^[a-z0-9][a-z0-9-]*$/i.test(trimmed)) return trimmed
  const candidate = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`
  let parsed: URL
  try {
    parsed = new URL(candidate)
  } catch {
    return null
  }
  const host = parsed.hostname.toLowerCase()
  if (!HOSTS.some((h) => host === h || host.endsWith(`.${h}`))) return null
  const match = /^\/jobs\/([a-z0-9][a-z0-9-]*)\/?$/i.exec(parsed.pathname)
  return match ? match[1] : null
}

async function detail(flags: Map<string, string | true>, positional: string[]): Promise<number> {
  const target = positional[1]
  if (!target) throw new CliError("detail requires an <id|url>", "NO_ID")
  const id = detailId(target)
  if (!id) throw new CliError(`could not read an id from "${target}" on ${HOSTS.join(", ")}`, "BAD_ID")
  const format = String(flags.get("format") ?? "json")
  if (!["json", "plain"].includes(format)) throw new CliError(`--format must be one of json|plain, got "${format}"`, "BAD_ARG")

  const envelope = await getJson(`/api/jobs/${encodeURIComponent(id)}`, new URLSearchParams())
  if (!envelope || !envelope.data || typeof envelope.data !== "object") throw new CliError("job not found", "NOT_FOUND")
  const job = envelope.data as Record<string, unknown>
  const row: Row = { ...toRow(job), description: typeof job.description === "string" ? cleanHtml(job.description) || null : null }

  if (format === "json") process.stdout.write(JSON.stringify(row, null, 2) + "\n")
  else process.stdout.write(`${row.title}\n${row.company ?? "-"} · ${row.location ?? "-"}\n\n${row.description ?? "(no description)"}\n\nURL: ${row.url}\n`)
  return 0
}

async function main(): Promise<number> {
  const { positional, flags } = parseArgs(process.argv.slice(2))
  const command = positional[0]
  if (!command || flags.has("help")) {
    process.stderr.write("usage: bun run src/cli.ts search --query <text> [--jobage N] [--limit N] [--page N] [--format json|table|plain]\n" +
      "       bun run src/cli.ts detail <id|url> [--format json|plain]\n")
    return command ? 0 : 1
  }
  const known = KNOWN[command]
  if (!known) return fail(`Unknown command "${command}"`, "BAD_CMD")
  for (const key of flags.keys()) {
    if (!known.has(key)) return fail(`unknown flag --${key} for '${command}'; flags are never silently ignored`, "UNKNOWN_FLAG")
  }
  try {
    return command === "search" ? await search(flags) : await detail(flags, positional)
  } catch (e) {
    if (e instanceof CliError) return fail(e.message, e.code)
    return fail(e instanceof Error ? e.message : String(e), "INTERNAL_ERROR")
  }
}

main().then((code) => process.exit(code))
