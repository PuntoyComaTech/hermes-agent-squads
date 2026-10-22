# Project base: strict tooling and access

## Contents

1. The strict base
2. What the gate enforces
3. Access: GitHub and the hosting provider
4. What the user sees

## 1. The strict base

Builders read `engineering-rules.md` (layers, SOLID, scalability, security coding) before writing code; QA's code lens
reviews against it.

A new repo also gets one seed test (`src/lib/slug.ts` and its test): the gate fails with no tests at all, so deleting
every test can never keep it green.

Run it yourself right after `site.yaml` exists, before the first card, for every site (new or existing repo):

```bash
python3 "$HERMES_HOME/skills/squad-web/site-contract/scripts/site_base.py" --site <site folder> --json
```

One command: it reads `stack`, `slug`, `provider` and `repo.path` from `site.yaml` and does everything below.

Every install goes through an official installer; nothing an installer owns is written by hand, and no version is
typed from memory:

- Empty repo: the stack's own create CLI (`stacks.json -> stacks.<stack>.create`: `create-astro`, `create-next-app`,
  the TanStack CLI) through `pnpm dlx` under the 3-day rule; pnpm pinned to its newest release 3 days old
  (`npm view pnpm time`, then `npm pkg set packageManager`); each package the template named re-added with
  `pnpm add <name>@<its major>` (the major the framework chose, the newest release of it 3 days old); the squad's
  tools with `pnpm add -D <name>`, no version; framework additions through the framework's command
  (`astro add tailwind`); Biome's config from `biome init` (unless the create CLI wrote one), extending the squad's
  rules in `tools/quality/biome.strict.jsonc`; then the quality configs, `git init` on `main`, hooks, the gate,
  first commit.
- Gate red on the template's own code (`next` in the JSON): fix that code so it meets the rule (for example props
  marked `Readonly`), never a rule, threshold or ignore; run the same command again. It keeps every file, runs the
  gate and makes the first commit.
- Existing repo: every file it already has is kept (listed under `kept`); its own pnpm pin stays; `package.json`
  gains the squad's `quality*` scripts (a repo's own `quality*` script is replaced and listed under `replaced_scripts`),
  `tsconfig.json` the strict options (a commented tsconfig that needs one is rewritten without its comments, and the
  JSON says so under `notes`); a weaker pnpm supply-chain setting is raised to the base's (`strengthened`). A `manual` item in the JSON is a strict option the script
  could not set: `ok` is false until you set it. Report the `kept` configs to the user only when one is weaker than the
  base, as one plain line with a proposal.
- Scanner install: osv-scanner and gitleaks are installed before the gate runs (step `security tools`); offline or an
  unsupported platform fails that step, never silently skips it.
- `ok: false`: the JSON names the failed step and its output tail. Fix what the base itself wrote; a failure in the
  user's existing code becomes the first milestone (`change: make the code pass the quality gate`), never a relaxed
  rule.
- pnpm missing: the script enables it through corepack (`corepack enable pnpm`), else `npm install -g pnpm`; inside
  the repo the pinned version runs either way. Node or Homebrew missing: the one install the user does
  (https://nodejs.org, LTS; https://brew.sh); say it in one line with the link.

## 2. What the gate enforces

`pnpm quality` runs these steps in order. lefthook runs Biome on every commit (each progress save included) and the
whole gate before every push; every builder runs the whole gate when its card's work is complete:

| Step | Tool | Blocks |
|---|---|---|
| `quality:types` | TypeScript strict (`noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, ...) | type errors, implicit `any` |
| `quality:lint` | Biome | `any`, `@ts-ignore`, `!` assertions, `console`, import cycles, barrel files, cognitive complexity > 10, functions > 60 lines, files > 300 lines, > 3 parameters, formatting |
| `quality:sonar` | ESLint with SonarJS, `eslint-plugin-security`, `no-unsanitized` and typed TypeScript rules (the Sonar rules, local and free) | code smells, bug patterns, weak hashes and random, command injection, unsanitized DOM writes, duplicated strings, nesting > 3, unsafe `any` flows, floating promises, non-exhaustive switches |
| `quality:arch` | dependency-cruiser | cycles, logic (`src/lib`, `src/domain`, `src/server`) importing UI, `src/domain` importing a framework, components importing pages, client code importing server code, dev dependencies in shipped code |
| `quality:dupes` | jscpd | copy-paste blocks (4+ lines) |
| `quality:unused` | knip | dead files, unused exports and dependencies |
| `quality:typecov` | type-coverage (strict) | any identifier whose type resolves to `any`, including through a library: 100 % required |
| `quality:secrets` | gitleaks | a key or token in the files or in any commit of the history |
| `quality:licenses` | `pnpm licenses` | GPL, AGPL, SSPL, BUSL, non-commercial or unknown licenses in what ships (LGPL and MPL pass) |
| `quality:deps` | osv-scanner on the lockfile, `pnpm audit` | a package with a known vulnerability or a malicious-package advisory |
| `quality:fresh` | `tools/quality/fresh.mjs` | a version typed from memory: a dependency pnpm never resolved (package.json and lockfile disagree), an exact pin, a major behind the newest one old enough to install; exceptions only in `tools/quality/fresh-allow.json`, each with its reason |
| `quality:test` | Vitest with coverage | failing tests; < 80 % coverage on `src/lib`, `src/domain`, `src/server` |

Slow scanners do not run on every edit: Semgrep (SAST) and nuclei (DAST, against the deployed preview) run once per
review in `code_audit.py`, which installs them on first use. `security_tools.py` installs osv-scanner, gitleaks, nuclei
and Semgrep with Homebrew, their official installer (it keeps them current: `brew upgrade`), and nuclei's templates
with nuclei's own updater, else a shallow clone of the official template repository, refreshed weekly. It never
downloads a binary itself. Semgrep's rules fall under the Semgrep Rules License v1.0.

Supply chain, in the repo's `pnpm-workspace.yaml`: no release younger than 3 days (`minimumReleaseAge`; known npm
attacks were caught and pulled within hours to two days), no package whose publisher trust dropped (`trustPolicy`), no
install script nobody approved (`strictDepBuilds`: a new package that needs one is a `decisions.md` line adding it to
`allowBuilds`). When pnpm flags a trust drop on a package the base adds (a release published without the provenance
its earlier ones had: a possible takeover), the base holds that package at its last trusted release, lists it under
`held` and in `fresh-allow.json`; never let the flagged release in.

A security fix never waits. A `quality:deps` failure is fixed with one command, run by whoever hits it:

```bash
python3 "$HERMES_HOME/skills/squad-web/site-contract/scripts/security_fix.py" --repo <repo>
```

It installs the lowest release that clears every advisory (`pnpm add` for a direct dependency, an override for a
transitive one). When that release is younger than 3 days, that exact release and the packages released with it at
the same version (its own scope) go under `minimumReleaseAgeExclude`, and nothing else; the exception is removed once
the release is old enough. Each fix is a line in the site's `decisions.md`. `site_base.py` runs it before the first
gate. An `osv-scanner.toml` ignore is the manager's, with a reason and an expiry date.

Response headers (CSP, HSTS, framing, referrer, permissions, cross-origin) ship from the first commit: Astro in
`public/_headers` (or `vercel.json`), Next in `next.config.ts`. A TanStack Start site renders on the server, so its
headers go in the Start server middleware: make that the first card of a TanStack site (web-backend), or QA's nuclei
pass blocks the first preview.

The configs are the squad's (`site-contract/templates/quality`). Nobody relaxes them: a rule that blocks legitimate
work is a `decisions.md` line written by you, with the reason, never an inline disable.

## 3. Access: GitHub and the hosting provider

```bash
python3 "$HERMES_HOME/skills/squad-web/site-contract/scripts/web_access.py" status gh <cf, or vercel when provider is vercel>
```

- Logged in: reuse it. Say nothing about it to the user.
- Not logged in, or the CLI is missing: `web_access.py ensure <tool>` installs the CLI (gh with Homebrew; `cf`,
  `wrangler` and `vercel` run as `pnpm dlx <tool>@latest` under the 14-day rule) and starts its login in the background. Its JSON carries `url`
  and, for a device login, `code`:
  - open `url` as a tab beside the chat (`desktop_preview`, label "GitHub login", "Cloudflare login" or "Vercel
    login"); the Cloudflare and Vercel URLs already carry the code, the GitHub code is on the clipboard (macOS) and in the message;
  - tell the user one line: "Approve the access in the tab beside the chat (code `<code>`)." Never more;
  - `web_access.py wait <tool>` returns when the login is valid (5 minutes); then go on.
- A second `ensure` while the user has not approved yet returns the same URL and code; it never starts a second
  login. The scripts also search Homebrew, nvm and the user's local bin, so an installed CLI is never "missing".
- One tool at a time: GitHub first, then the provider. `wrangler` is logged in only when the site's deploy needs it
  (`deploying-sites` references), the same way.
- Outside the Desktop app, send the URL and the code instead of the tab.
- The bot never types a password, a code or a token. The user's approval on the provider's page is the credential.

## 4. What the user sees

```text
Your project is ready: strict code checks are installed and the site is open in the tab beside this chat.
Approve the GitHub access in the tab (code ABCD-1234).
```

No tool names, no install steps, no "I will check how Cloudflare works".
