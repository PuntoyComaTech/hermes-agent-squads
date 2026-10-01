# Scripts: web development squad

> Script specifications. The builder writes them in step 9 of the installation, on the user's computer; they also work as prompts for any coding AI.
> Level 1: `deliver.py` and `check_site.py`, plus the shared `heavy_lock.py`. Deploy commands are not scripts: `web-deployer` runs them following `deploy-cloudflare` (`02-architecture.md` §5).

## Common preamble

```markdown
Project: {{W}} = {{ROOT}}/projects/web. Python 3.11+ (venv in {{W}}/.venv), same script on Mac,
Windows and Linux; no .sh or .ps1. The interpreter that creates the venv must be 3.11+:
`python3 --version` first, because macOS ships 3.9.x and `python3 -m venv` then silently builds a
venv that cannot run these scripts (`04-installation.md` step 3g). Deterministic code, no LLM. Each script is an argparse CLI:
--json when requested, logs to stderr, exit 0 on success, 1 on a data error, 2 on a network or
external tool error. Idempotent. Tests with pytest in {{W}}/tests/; a short README in
{{W}}/scripts/. pathlib paths; absolute or relative to {{W}}. Never read or write outside {{W}},
except: reading {{ROOT}}/user/; {{ROOT}}/scripts/heavy_lock.py and {{ROOT}}/.heavy-lock; reading
the orchestrator's config when stated; deliver.py's daily commit in {{ROOT}}. No secrets: these
scripts never need the Cloudflare or GitHub tokens. Everything that opens Chrome or runs
Lighthouse goes through the lock. Data contracts: 02-architecture.md (attached).
```

Traps already hit by other squads apply here too (`squads/marketing/05-scripts.md`, "Traps"): weekday keys normalized to English, PyYAML dates converted to strings before `json.dumps`, cron scripts only inside `$HERMES_HOME/scripts/`, the reentrant lock token, the gateway's `HERMES_BIN`, Discord's User-Agent and `DISCORD_HOME_CHANNEL` as a bare ID.

## Level 1

### `heavy_lock.py` (shared)

Specified in `squads/marketing/05-scripts.md`. Create it in `{{ROOT}}/scripts/` only if it does not exist. This squad uses the CLI form for installs and builds (`python {{ROOT}}/scripts/heavy_lock.py run --name pnpm-build --wait 1800 -- pnpm build`) and the module form inside `check_site.py`.

### `check_site.py`

```markdown
Create {{W}}/scripts/check_site.py. Run by web-reviewer (full) and web-deployer (--smoke).
Input: --site <slug> --id <ID> --round R (--url <https url> | --dir <static build folder>)
[--smoke] [--pages <path,...>]. Pages default to the Pages table of sites/<slug>/spec.md, per
language. --dir serves the folder on 127.0.0.1 on a free port for the duration of the run and
stops it before exiting (tests and local fixtures only; nothing is left running).

Output folder: sites/<slug>/reviews/<ID>-r<R>/ (--smoke: smoke.json in the same folder).
checks.json: {"id","round","url","date","thresholds","checks":[{"name","page","ok","detail",
"severity":"critical|warn"}],"scores":{...},"all_ok":bool}.

Checks, full mode:
- HTTP: every page returns 200; a missing path returns 404; redirects at most 1 hop.
- Links: crawl same-origin links from the pages (max 200 URLs); every internal link and asset
  200 (critical). External links: HEAD, then GET on 405; failures are warn only.
- Meta: title, description, lang, canonical, Open Graph title and image, viewport; sitemap.xml
  and robots.txt present when the spec has more than one page; hreflang per language.
- Lighthouse (npx lighthouse, pinned, --only-categories=performance,accessibility,best-practices,seo,
  mobile form factor, --output json, system Chrome through CHROME_PATH): the four categories per page
  against thresholds in web-profile.yaml (lighthouse_mobile_ssr for dynamic_seo and saas). Under
  threshold: critical. Lighthouse's category ids use hyphens (`best-practices`) while the YAML keys in
  web-profile.yaml use underscores (`best_practices`): map each key to its category id explicitly, or
  that check reads as `None (min 90)` and fails on every page while reporting no score.
- Accessibility: Playwright (system Chrome) loads each page, injects axe-core (pinned, from
  {{W}}/node_modules), runs WCAG 2.2 AA rules; counts by impact against axe_max.
- Screenshots: each page at 390x844 (mobile-<page>.png) and 1440x900 (desktop-<page>.png),
  full page. Console errors per page (warn; uncaught exceptions critical).
- Security: response headers (Content-Security-Policy or at least X-Content-Type-Options,
  Referrer-Policy, frame protection, HSTS on https); mixed content; secret patterns in every
  loaded JS and HTML (API key shapes: sk_live_, AKIA, ghp_, github_pat_, xox, private key
  headers, JWT-like strings next to "secret"), critical. With --repo sites/<slug>/repo also scan
  the working tree and git history of the branch for the same patterns and for committed .env
  or .dev.vars files; and run pnpm audit --json --prod (high or critical: warn, listed).
- Forms: every form has an action or a handler and labeled inputs (static check).

Smoke mode (deployer, after each deploy): HTTP 200 on every page, the home page's title matches
the spec site name, no uncaught console exception, no secret pattern. No Lighthouse or axe.
Under 60 s.

Lock: one heavy_lock("check_site", max_wait=1800) around everything that opens Chrome or
Lighthouse; the HTTP-only checks run outside it. With 8 GB RAM, one page at a time.
Exit 0 if the checks ran (results in the JSON, even when some fail); 1 if the site cannot be
reached or the spec cannot be read; 2 if Chrome or Lighthouse cannot start.
Tests: a fixture static site with one broken link, one image without alt, one leaked fake key,
and a clean page; smoke and full modes; the lock waits when held.
```

### `deliver.py`

```markdown
Create {{W}}/scripts/deliver.py. Runs every 15 min via cron --no-agent in the orchestrator
profile. The only exit point toward the user for this squad.

0. Own lock {{W}}/outbox/.deliver.lock: if another run is active, exit silently.
1. Load user/profile.md (main channel), web-profile.yaml (notify_window, quiet_until,
   technical_level) and the settings.yaml of every site.
2. Destination per site, read-only from the orchestrator's config:
   - destination topic: thread_id of the "<emoji> <name>" topic in
     platforms.telegram.extra.dm_topics; send with --to telegram:<chat_id>:<thread_id>;
   - destination channel: --to discord:#<slug>;
   - main, or a topic without thread_id yet: the main channel, prefixed "<emoji> <Name> ·".
   Never edit Hermes config or restart the gateway.
3. Outbox, only inside notify_window and after quiet_until. For each outbox/ready/*.json, by
   kind:
   - spec: "<emoji> <Name> · Your site plan" + the 3-5 summary lines + monthly cost line + open
     questions numbered + "Reply "ok" to start, or tell me what to change". Attach spec.md.
   - preview: title, URL, summary lines, the mobile screenshot of the home page
     (as a photo), the reply line. With approver client, add a
     forwardable paragraph.
   - production: "✅ <Name> is live: <url>" + what changed + "Say "rollback" if something is
     wrong."
   - domain: the registrar steps as a numbered list, then the confirmation question as sent by
     the deployer; or "✅ <domain> works with HTTPS".
   - rollback: "↩️ <Name> is back to the version from <date>: <url>".
   With technical_level developer, append PR and commit links from the deploy record.
   Send: hermes -p orchestrator send --to <destination> "<message> MEDIA:<absolute path> …".
   On success: move the JSON to outbox/sent/; for preview, set status delivered in the milestone
   note with a History line. On failure: leave it, print the error.
4. Blocked tasks: hermes kanban list --status blocked --json. For each task with a site tenant
   not yet notified (ids in outbox/.blocked_notified): "⚠️ <Name> · <title> needs your answer:
   <reason>. Reply to me here." A card blocked with kind dependency (a consultation) waits in
   todo, not blocked, so it is never reported.
5. Once a day after 23:00: a commit in {{ROOT}} with the squad's text (the .gitignore excludes
   sites/*/repo/).
6. Never publishes, deploys or writes to anyone but the user.
No output when all went well. --simulate prints the messages instead of sending. Tests: two
sites (one with topic, one main), each kind of outbox file, a blocked task notified once, a message held by quiet_until, the notify window with weekday
keys in two spellings.
```

## Quality gate (Level 1, shared)

> Added by D-033. Mandatory on every site repo; nothing ships without it. This is a **standard**,
> not a suggestion: the thresholds below are the user's, and relaxing any of them is a
> decision written into `decisions.md` with its reason. Written at install to `{{W}}/templates/quality/`
> and copied into each site repo at its first build.

### The standard in one table

Each tool has one job, so none fights another for the same file.

| Tool | Job | Verified version (2026-09-30) |
| --- | --- | --- |
| TypeScript | Type checking at maximum strictness | 5.x |
| `@biomejs/biome` | Formatting + base lint of TS/JS/JSON/CSS | 2.5.15 |
| `prettier` | **Only** `.astro` (Biome cannot format them) | 3.9.9 + `prettier-plugin-astro` |
| `eslint` | Only the rule families Biome lacks | 10.11.0 + `typescript-eslint` 8.71.0 |
| ↳ `eslint-plugin-sonarjs` | **Sonar's rules, local, no server** | 4.2.2 |
| ↳ `eslint-plugin-boundaries` | Architecture boundaries between layers (SOLID) | 7.2.0 |
| ↳ `eslint-plugin-security` | Dangerous patterns | 4.1.0 |
| ↳ `eslint-plugin-functional` | Immutability | 10.0.1 |
| ↳ `eslint-plugin-unicorn` | Modern best practices | 76.0.0 |
| `jscpd` | Duplication. Rust engine, self-contained binary | 5.4.0 |
| `knip` | Unused files, exports and dependencies | 6.39.0 |
| `osv-scanner` | Known vulnerabilities in every locked dependency. Local binary, offline, free (Apache 2.0) | 2.6.0 |
| Vitest + Playwright | Tests and coverage | — |

**Sonar without a server.** `eslint-plugin-sonarjs` brings Sonar's rules locally. A real SonarQube
needs a server, and `base/01-principles.md` §1.8 forbids Docker, servers and databases. **Do not
install SonarQube**; if a user ever wants one, that is a change to a base rule and needs its own
decision entry.

**`osv-scanner` runs offline.** Google's scanner against the public OSV database, as a single Go
binary outside the repo (`brew install osv-scanner`, or the release binary). The scan always runs
with `--offline`: no project or dependency data leaves the machine, no account, no server, no cost.
The database is a local cache in `{{ROOT}}/.cache/osv` (`OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY`),
refreshed by the gate when older than 24 h with `--download-offline-databases`, which only
downloads the public database. Strict: any known vulnerability, of any severity, fails the gate
(exit 1), and so does a missing lockfile (exit 128). The only exception is an `[[IgnoredVulns]]`
entry in the repo's `osv-scanner.toml` with `reason` and an `ignoreUntil` at most 30 days away,
recorded in `decisions.md`; an expired one fails again.

**`jscpd` is not replaced.** Checked against the package registry on 2026-09-30: still published
(same day), Rust engine, HTML/JSON/SARIF reports, and it fails CI over a threshold. Nothing better
exists for duplication in the JS ecosystem.

**`eslint-plugin-jsx-a11y` is deliberately excluded.** Verified against real `peerDependencies`:
its three latest versions (6.10.0–6.10.2) cap at `eslint ^9`, while `eslint-plugin-unicorn` (70–76,
all of them) requires `eslint >=10.4`. **No combination makes them coexist.** ESLint 10 + unicorn
was chosen because the rest of the set fits whole. Accessibility is covered, better, by Biome's
`a11y: all` while writing and by **axe-core against WCAG 2.2 AA** on the deployed preview at review
time — a browser check rather than a static guess. Add `jsx-a11y` when it supports ESLint 10.

### `{{W}}/templates/quality/quality.json` — the only file anyone tunes

```json
{
  "version": 1,
  "typescript": { "strict_max": true, "skipLibCheck": false },
  "complexity": {
    "cognitive_max": 10, "cyclomatic_max": 10, "max_lines_per_function": 50,
    "max_params": 3, "max_depth": 3, "max_nested_callbacks": 3,
    "max_lines_per_file": 300, "max_statements": 20, "max_classes_per_file": 1
  },
  "duplication": { "tool": "jscpd", "max_percent": 0, "min_tokens": 50 },
  "dead_code": { "tool": "knip", "exit_code_on_findings": true },
  "coverage": { "lines_min": 80, "branches_min": 80, "per_acceptance_criterion": true },
  "gates_block": true,
  "layers": ["ui", "features", "domain"]
}
```

`max_percent: 0` is zero tolerance: any 50-token block appearing twice fails the build. That is the
strictest the tool allows and it is intentional. `layers` becomes `["content","ui"]` for a site with
no app layers (a one-pager): the rule that matters is that the direction always points at the core.

### `tsconfig.json` — every extra switch on

```json
{
  "compilerOptions": {
    "strict": true, "noUncheckedIndexedAccess": true, "exactOptionalPropertyTypes": true,
    "noImplicitOverride": true, "noPropertyAccessFromIndexSignature": true,
    "noFallthroughCasesInSwitch": true, "noImplicitReturns": true,
    "noUnusedLocals": true, "noUnusedParameters": true,
    "allowUnreachableCode": false, "allowUnusedLabels": false,
    "forceConsistentCasingInFileNames": true, "isolatedModules": true,
    "verbatimModuleSyntax": true, "noUncheckedSideEffectImports": true,
    "skipLibCheck": false, "noEmit": true
  },
  "include": ["src", "tests", "*.config.ts", "*.config.mjs"],
  "exclude": ["node_modules", "dist", ".astro"]
}
```

`skipLibCheck: false` is deliberate: it type-checks the dependencies' own types too. Slower and
more annoying, and it is the standard the owner chose. When an unfixable third-party type breaks,
exclude **that** folder, never the whole project.

### `{{W}}/templates/quality/biome.json` — format + base lint

`recommended` plus every rule in `style`, `correctness`, `suspicious`, `complexity`, `performance`,
`a11y`, `security` and `nursery` set to `error` — each group as `{"preset": "all"}`, **never**
`{"all": true}` (Traps below). 2-space indent, line width 100, LF, double quotes, semicolons,
trailing commas. It ignores `.astro` (Prettier owns those). Tests may exceed the
cognitive-complexity limit; nothing else is relaxed. Verified content (2026-10-01, the gate runs
green on a real site with it):

```json
{
  "$schema": "https://biomejs.dev/schemas/2.5.15/schema.json",
  "assist": {
    "actions": { "source": { "preset": "all" } },
    "enabled": true
  },
  "css": { "parser": { "tailwindDirectives": true } },
  "files": {
    "ignoreUnknown": true,
    "includes": [
      "src/**",
      "tests/**",
      "*.config.ts",
      "*.config.mjs",
      "*.json",
      "*.css",
      "!**/*.astro"
    ]
  },
  "formatter": {
    "enabled": true,
    "indentStyle": "space",
    "indentWidth": 2,
    "lineEnding": "lf",
    "lineWidth": 100
  },
  "javascript": {
    "formatter": { "quoteStyle": "double", "semicolons": "always", "trailingCommas": "all" }
  },
  "linter": {
    "enabled": true,
    "rules": {
      "a11y": { "preset": "all" },
      "complexity": { "preset": "all" },
      "correctness": { "preset": "all" },
      "nursery": { "preset": "all" },
      "performance": { "preset": "all" },
      "security": { "preset": "all" },
      "style": { "preset": "all" },
      "suspicious": { "preset": "all" }
    }
  },
  "overrides": [
    {
      "assist": {
        "actions": {
          "source": {
            "useSortedAttributes": "on",
            "useSortedKeys": "off",
            "useSortedPackageJson": "on"
          }
        }
      },
      "includes": ["package.json"]
    },
    {
      "includes": ["**/*.test.ts", "**/*.spec.ts", "tests/**"],
      "linter": { "rules": { "complexity": { "noExcessiveCognitiveComplexity": "off" } } }
    },
    {
      "includes": ["*.config.ts", "*.config.mjs", "run-gate.mjs", "eslint.config.mjs"],
      "linter": {
        "rules": {
          "correctness": { "noNodejsModules": "off", "noUnresolvedImports": "off" },
          "style": { "noDefaultExport": "off", "noTernary": "off" }
        }
      }
    },
    {
      "includes": ["tests/**"],
      "linter": {
        "rules": {
          "correctness": {
            "noNodejsModules": "off",
            "noUnresolvedImports": "off",
            "useQwikValidLexicalScope": "off"
          },
          "performance": { "noAwaitInLoops": "off" },
          "style": { "noTernary": "off" }
        }
      }
    }
  ],
  "vcs": { "clientKind": "git", "enabled": true, "useIgnoreFile": true }
}
```

Four things in that file are load-bearing and were found the hard way:

- **`files.includes` must exclude `.astro`** (`!**/*.astro`). Biome cannot parse them: sweeping
  `src/**` flags code that is not wrong (13 `lint/correctness` diagnostics on the two `.astro`
  files of a real site), none of them defects.
- **`css.parser.tailwindDirectives: true`**: without it the Tailwind v4 `@theme` block is a parse
  error and `biome check` cannot even format the CSS.
- **The `package.json` override**: `useSortedKeys` wants pure alphabetical order while
  `useSortedPackageJson` wants the manifest's canonical order — both come with `"preset": "all"`
  and they contradict each other. The override lets the manifest's order win
  (`useSortedKeys: "off"`); without it `package.json` always shows an `assist/source` finding.
- **Three rules are scoped off by a reproducible false positive**, not for convenience:
  `useQwikValidLexicalScope` (flags closures in files that are not Qwik), `noUnresolvedImports`
  (does not follow `@playwright/test` → `playwright/test` under pnpm's isolation) and
  `noNodejsModules` (tests and config files read the disk on purpose).

### `{{W}}/templates/quality/eslint.config.mjs` — only what Biome cannot do

Flat config, everything in `error`, `warn` is not a level this gate uses. The rule families are
the ones D-033 lists (`typescript-eslint` typed, `sonarjs`, size and shape, `boundaries`,
`security`, `functional`, `unicorn`), and the file below is the shape that actually runs: the
typed rules are scoped to the files that have a TypeScript program, or ESLint aborts before
linting anything (Traps below).

```js
// ESLint only brings what Biome does not have. Do not duplicate rules between the two tools
// or they will fight over the same file.
//
// ENGINEERING DECISION, 2026-09-30 (verified against real peerDependencies):
//   eslint-plugin-jsx-a11y is NOT included: its three latest versions (6.10.0-6.10.2) cap at
//   eslint ^9, and eslint-plugin-unicorn (70-76, all of them) requires eslint >=10.4. They
//   cannot coexist. ESLint 10 + unicorn wins. Accessibility is covered by Biome (a11y: preset
//   all) and, above all, by axe-core against WCAG 2.2 AA run by the reviewer on the real
//   preview. Add jsx-a11y when it supports ESLint 10.
import eslint from "@eslint/js";
import boundaries from "eslint-plugin-boundaries";
import functional from "eslint-plugin-functional";
import security from "eslint-plugin-security";
import sonarjs from "eslint-plugin-sonarjs";
import unicorn from "eslint-plugin-unicorn";
import tseslint from "typescript-eslint";

import quality from "./quality.json" with { type: "json" };

const c = quality.complexity ?? {};

// Layers: the dependency direction ALWAYS points at the core. That is SOLID's Dependency
// Inversion, enforced rather than described. On a site without layers (a landing page) change
// this to ['content', 'ui'].
const layers = quality.layers ?? ["ui", "features", "domain"];

export default tseslint.config(
  { ignores: ["dist/**", "node_modules/**", ".astro/**", "coverage/**", "public/**"] },

  eslint.configs.recommended,

  // Rules that need type information apply ONLY to TypeScript files: `eslint.config.mjs` and
  // `astro.config.mjs` sit outside the tsconfig `include`, so typescript-eslint cannot give
  // them a program and aborts with "requires type information". Plain JS keeps
  // `recommended`, without the typed rules.
  //
  // `projectService: true` is what gives those rules their TypeScript program: the
  // `strictTypeChecked` / `stylisticTypeChecked` configs bring the rules but NOT the
  // parserOptions, and without this none of them can run.
  {
    extends: [...tseslint.configs.strictTypeChecked, ...tseslint.configs.stylisticTypeChecked],
    files: ["**/*.ts"],
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
  },
  {
    extends: [tseslint.configs.recommended],
    files: ["**/*.js", "**/*.mjs", "**/*.cjs"],
  },

  // ---- Sonar's rules, local and with NO server (SOLID: Single Responsibility) ----
  sonarjs.configs.recommended,
  {
    rules: {
      "sonarjs/cognitive-complexity": ["error", c.cognitive_max ?? 10],
      // eslint-plugin-sonarjs 4.x takes the threshold as an object (`{ threshold }`),
      // not as a number.
      "sonarjs/cyclomatic-complexity": ["error", { threshold: c.cyclomatic_max ?? 10 }],
    },
  },

  // ---- Size and shape: one function = one thing ----
  {
    rules: {
      "max-classes-per-file": ["error", c.max_classes_per_file ?? 1],
      "max-depth": ["error", c.max_depth ?? 3],
      "max-lines": [
        "error",
        { max: c.max_lines_per_file ?? 300, skipBlankLines: true, skipComments: true },
      ],
      "max-lines-per-function": [
        "error",
        { max: c.max_lines_per_function ?? 50, skipBlankLines: true, skipComments: true },
      ],
      "max-nested-callbacks": ["error", c.max_nested_callbacks ?? 3],
      "max-params": ["error", c.max_params ?? 3],
      "max-statements": ["error", c.max_statements ?? 20],
    },
  },

  // ---- Architecture: boundaries between layers (Open/Closed + Dependency Inversion) ----
  {
    plugins: { boundaries },
    rules: {
      "boundaries/element-types": [
        "error",
        {
          default: "disallow",
          rules: layers.map((layer, index) => ({
            allow: index + 1 < layers.length ? [layers[index + 1]] : [],
            from: [layer],
          })),
        },
      ],
      "boundaries/entry-point": ["error", { default: "disallow" }],
    },
    settings: {
      // `mode` is deprecated in eslint-plugin-boundaries 7: "folder" is already the default.
      "boundaries/elements": layers.map((t) => ({ pattern: `src/${t}/*`, type: t })),
      "boundaries/include": ["src/**"],
    },
  },

  // ---- Security ----
  security.configs.recommended,
  {
    rules: {
      // Excepted only where the code justifies it, never by default.
      "security/detect-object-injection": "error",
    },
  },

  // ---- Immutability (predictability, Liskov Substitution) ----
  // `eslint-plugin-functional` mixes rules that READ TYPES (`immutable-data`,
  // `no-return-void`, `prefer-readonly-type`) with rules that do not (`no-let`). Applying all
  // of them to the `.mjs` config files aborts the run: those files are outside the tsconfig
  // `include` and have no TypeScript program. Plain JS/TS keeps `no-let`.
  {
    plugins: { functional },
    rules: {
      "functional/no-let": "error",
    },
  },
  {
    extends: [functional.configs.recommended],
    files: ["**/*.ts"],
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
  },
  {
    files: ["**/*.ts"],
    rules: {
      "functional/immutable-data": "error",
      "functional/no-let": "error",
      "functional/no-return-void": "error",
      "functional/prefer-readonly-type": "error",
    },
  },

  // ---- Modern best practices ----
  unicorn.configs.recommended,
  {
    rules: {
      "unicorn/no-null": "error",
      "unicorn/prefer-module": "error",
      "unicorn/prefer-top-level-await": "error",
    },
  },

  // ---- Never take the shortcut ----
  // These rules are TypeScript ones (with type information), so they are also scoped to the
  // `.ts` files. `no-warning-comments` needs no types and applies to every file.
  {
    files: ["**/*.ts"],
    rules: {
      "@typescript-eslint/consistent-type-imports": ["error", { prefer: "type-imports" }],
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/no-misused-promises": "error",
    },
  },
  {
    // ESLint 10 removed this rule's `message` option; only `terms`, `location` and
    // `decoration` exist. A pending task with no linked issue does not enter the repo.
    rules: {
      "no-warning-comments": ["error", { terms: ["todo", "fixme", "hack"] }],
    },
  },

  // Test files allow more complexity and callbacks, and nothing else is relaxed.
  {
    files: ["**/*.test.ts", "**/*.spec.ts", "tests/**"],
    rules: {
      "functional/immutable-data": "off",
      "functional/no-conditional-statements": "off",
      // A Playwright test is an imperative script: `await page.goto("/")` is an EXPRESSION
      // with an effect and has no equivalent statement form, and walking a list of buttons to
      // check each one is the natural shape. Off only here, by file type; the site's code and
      // its data (`copy.ts`) keep requiring immutability. Reason: the shape of Playwright
      // tests, not the style of the code.
      "functional/no-expression-statements": "off",
      "functional/no-loop-statements": "off",
      "functional/no-return-void": "off",
      "max-nested-callbacks": ["error", 5],
      "sonarjs/cognitive-complexity": "off",
    },
  },
);
```

### `{{W}}/templates/quality/.prettierrc.json` — `.astro` only

Named `.prettierrc.json` so the format is explicit (both names resolve; verified 2026-10-01). The
content is what matters: a `$comment` key is not a Prettier option — Prettier ignores it with
`Ignored unknown option` on **every** file it formats (Traps below). Verified content:

```json
{
  "endOfLine": "lf",
  "overrides": [{ "files": "*.astro", "options": { "parser": "astro" } }],
  "plugins": ["prettier-plugin-astro"],
  "printWidth": 100,
  "semi": true,
  "singleQuote": false,
  "tabWidth": 2,
  "trailingComma": "all"
}
```

`overrides` sets `parser: astro` for `*.astro`. Never let Prettier format anything Biome also
formats: the two will fight.

### `run-gate.mjs` — one command, stops at the first failure

Written as a prompt here like every script (`05-scripts.md` preamble applies): `node` only, no
dependencies of its own, argparse-equivalent flags `--fix` and `--skip-tests`, logs to stderr, exit 1 at the first
failing step and 0 when everything passes, idempotent. It reads `quality.json`, runs every step
through the shared heavy-work lock (`python {{ROOT}}/scripts/heavy_lock.py run --name gate-<step> --wait 1800 -- <cmd>`), and runs in this fixed order:

1. `tsc --noEmit` — types.
2. `biome check .` (or `--write` with `--fix`).
3. `eslint .` (or `--fix`).
4. `prettier --check "**/*.astro"` (or `--write`).
5. `knip` — dead code.
6. `jscpd . --threshold <max_percent> --min-tokens <min_tokens> --reporters json,console`.
7. `osv-scanner scan source --offline -L pnpm-lock.yaml` (with `--config osv-scanner.toml` if the
   repo has one). Any exit other than 0 fails. If the local database is older than 24 h, first
   `osv-scanner scan source --offline-vulnerabilities --download-offline-databases -L pnpm-lock.yaml`;
   if that download fails, scan the cached database and say how old it is; no database at all fails.
8. `vitest run --coverage` — skipped with `--skip-tests`; otherwise coverage must meet
   `coverage.lines_min` and `coverage.branches_min`.

On failure it prints which step failed and: *"No hay commit, ni PR, ni preview. Arregla esto y
repite. Atajo legítimo: cambia el umbral en quality.json y anótalo en decisions.md."*

`--fix` repairs formatting and what is auto-fixable. It **never** lowers a threshold and never
disables a rule.

### `pnpm-workspace.yaml` — pin `rollup` (third-party types)

`tsconfig.json` turns on `exactOptionalPropertyTypes` and `skipLibCheck: false`, and with those,
vite 6.4.3 and rollup 4.63.5 declare the same `Plugin` interface in incompatible ways: vite builds
`{ ssr?: boolean | undefined, attributes?: … }` and rollup expects `ssr?: boolean` without
`undefined`. The error lives in both third-party `.d.ts` files and cannot be fixed from the
project. Pin rollup to the last version where both coexisted, in `pnpm-workspace.yaml`:

```yaml
overrides:
  rollup: 4.55.1
```

Verified 2026-10-01 on a real Astro site: with the pin, `tsc --noEmit` reports 0 errors. When a
third-party type breaks like this, pin the dependency and record the pin in `decisions.md`; do not
relax `skipLibCheck`, and exclude only the offending package's folder as a last resort, never the
whole project.

### Traps already hit (2026-10-01)

Each row is a config written from the text above in a real installation that did not run. The
error is the exact one the tool printed. They stay here so no installer writes them again.

| Written | Exact error | Right |
| --- | --- | --- |
| Rule groups as `{"all": true}` | `deserialize ━ Found an unknown key 'all'.` (once per group) | `{"preset": "all"}` |
| A `$comment` key in `biome.json` | `deserialize ━ Found an unknown key '$comment'.` | No comment keys: Biome only accepts its schema |
| `files.includes` sweeping `src/**` | False `lint/correctness` diagnostics on every `.astro` file (13 on the two pages of a real site) | `"!**/*.astro"` in `files.includes`; Prettier owns `.astro` |
| `eslint.config.mjs` without `projectService` | `Error while loading rule '@typescript-eslint/await-thenable': You have used a rule which requires type information, but don't have parserOptions set to generate type information for this file.` | `parserOptions: { projectService: true }` on the typed block |
| Typed rules over the `.mjs` config files | `Error while loading rule '@typescript-eslint/no-floating-promises': … Occurred while linting …/eslint.config.mjs` | Scope the typed rules to `files: ["**/*.ts"]`, as above |
| `sonarjs/cyclomatic-complexity` with a number | `Key "rules": Key "sonarjs/cyclomatic-complexity": Value 10 should be object.` | `["error", { threshold: 10 }]` (eslint-plugin-sonarjs 4.x takes an object) |
| `no-warning-comments` with a `message` option | `Key "rules": Key "no-warning-comments": … Unexpected property "message". Expected properties: "terms", "location", "decoration".` | Only `terms`, `location`, `decoration` (ESLint 10 removed `message`) |
| `run-gate.mjs` running `knip --no-exit-code=false` | `Option '--no-exit-code' does not take an argument` | Plain `knip`: it already exits non-zero on findings, which is what the gate wants |
| A `$comment` key in `.prettierrc*` | `[warn] Ignored unknown option { $comment: … }.` on every file | No comment keys |
| `boundaries/elements` with `mode: "folder"` | `[boundaries][warning]: The 'mode' option in element descriptors is deprecated and will be removed in a future major version.` | Omit `mode` ("folder" is already the default) |

Two structural traps, same source:

- **The runner must find its own root.** `run-gate.mjs` is copied into each site repo and also
  lives in `{{W}}/templates/quality/`. It must detect whether it sits at the repo root (a
  `package.json` or `tsconfig.json` next to it) before running `tsc` and `eslint`: without that
  check, the gate ran on the template directory and passed without checking the site at all.
- **A `$comment` key is never valid** in a tool's config (`biome.json`, `.prettierrc*`, ESLint).
  Put explanations in `quality.json` (`comment` inside the section it explains) or in this file.

### Who runs it, and what a failure blocks

| Role | When | If it fails |
| --- | --- | --- |
| `web-developer` | Before **every** commit (BUILD) | No commit. Fix and repeat. Never `--force`, never relax a rule. |
| `web-deployer` | Before opening the PR (PREVIEW) | **No PR and no preview.** `kanban_block` naming the failing step. |
| `web-reviewer` | First step of REVIEW, before anything else | **Critical finding**: it does not approve. Goes in `critical` of `reviews/<ID>-r<R>.json`. |

The reviewer does not repair code: a failing gate is FIX to the developer.

### Never

Relax a rule, raise a threshold or add an exception **without writing it in `decisions.md`** with
the reason · `--force` · `skipLibCheck: true` · `@ts-ignore` · `any` · a file-wide `eslint-disable` ·
turning off `knip`, `jscpd` or `osv-scanner` to get unstuck · an `IgnoredVulns` entry without `ignoreUntil` · a server-based SonarQube. A `// eslint-disable` with
no written reason is a critical finding from the reviewer.

## Level 2

Specified when the user moves up (`06-testing-and-operations.md` §5):

- `deps_update.py` (`--no-agent` cron, weekly, profile `web-developer`): for each active site without PAUSE, if `pnpm outdated --json` in `repo/` shows updates, creates a developer BUILD kind `change` with the list (idempotency key `<slug>-deps-<YYYY-WNN>`). It never updates packages itself.
- `perf_monitor.py` (`--no-agent` cron, daily, profile `orchestrator`): runs `check_site.py --smoke` plus a Lighthouse performance pass on each live URL; appends to `sites/<slug>/perf.csv` (`date,page,performance,lcp_ms,cls,status`); writes an outbox `alert` file only when a page drops below threshold twice in a row or returns non-200.
