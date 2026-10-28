# Rule exceptions of the strict base

Every rule of Biome, oxlint and SonarJS is an error. These are the only exceptions, each in the config file
(`tools/quality/biome.strict.jsonc`, `tools/quality/oxlintrc.json`, `tools/quality/eslint.config.mjs`) with its
reason. A new exception is a manager decision in `decisions.md`, never an inline disable.

| Rule | Scope | Reason |
|---|---|---|
| Biome `security.noSecrets` | `tools/**`, config files | its entropy heuristic flags path regexes and CSP strings; gitleaks (`quality:secrets`) scans files and history |
| Biome `style.useNamingConvention` (`strictCase: false`) | `playwright.config.ts`, `e2e/**` | Playwright's API names (`baseURL`) carry consecutive uppercase |
| Biome `nursery.useLayeredStyles` | `**/*.css` | it fires on Tailwind 4's `@import "tailwindcss"`; layering it changes utility precedence |
| Biome `style.noHeadElement` | `src/routes/__root.tsx` | a server-rendered app's document shell renders `<head>` |
| Biome Tailwind nursery family, `style.noHexColors` | `**/*.tsx`, `**/*.css` | they reject the create CLIs' own templates and next/font's runtime variables |
| Biome `style.noImplicitBoolean` | global | contradicts oxlint `react/jsx-boolean-value` (`prop`, not `prop={true}`) |
| oxlint `import/no-relative-parent-imports` | global | needs an import alias the create CLIs do not set up; dependency-cruiser enforces layer direction |
| oxlint `import/no-unassigned-import` | global | `import "./globals.css"` is how the frameworks load styles |
| oxlint `react/jsx-max-depth`, `react/forbid-component-props`, `react/only-export-components`, `react-perf/jsx-no-new-*` | `**/*.tsx` | depth 2 forces a component per element; `className` pass-through is a standard API; framework exports (`metadata`, `Route`) sit beside components; react-perf prescribes `memo`/`useMemo`, which this base bans |
| oxlint `typescript/prefer-readonly-parameter-types` | renders, `src/hooks`, `e2e` | React's and the DOM's types are not deeply readonly |
| oxlint `vitest/prefer-importing-vitest-globals`, `vitest/require-test-timeout` | `e2e/**` | Playwright tests use Playwright's `test` and `expect` |
| oxlint whole layer | `tools/**`, `**/*.astro` | the gate's `.mjs` tools are outside the TypeScript program; Biome, jscpd and the ratchet cover them. Biome's astro domain covers `.astro` |
| SonarJS `file-name-differ-from-class` | route and render files | frameworks name route files by path (`page.tsx`, `__root.tsx`) |
| dependency-cruiser `components-hold-no-logic` | not used | components may import `domain` and `lib`; render complexity 1 (Biome) and 0 (SonarJS) keep logic out of renders |

## Tool facts that shape the configs

- oxlint ignores the config's `ignorePatterns`, and an `overrides` glob must start with `**/`: the gate passes
  `src e2e` and `--ignore-pattern` for generated code, and the ratchet counts oxlint the same way.
- A project's own `biome.json` (from `biome init` or a create CLI) overrides the extended formatter:
  `site_base.py` normalizes `formatter` to spaces, width 2, line 100.
