# Engineering rules

What every builder writes to and what the code lens reviews against. The gate (`pnpm quality`) enforces the
measurable part; the rest is judgment, and review reads the diff for it.

## Contents

1. Layers
2. SOLID in this stack
3. Scalability
4. Security coding
5. Errors and tests
6. Code rules
7. Gate and review

## 1. Layers

| Folder | Holds | May import |
|---|---|---|
| `src/domain` | business rules, pure functions, types | nothing from UI or frameworks |
| `src/lib` | shared helpers, adapters to outside services | `domain` |
| `src/server` | data access, auth, integrations, API handlers | `domain`, `lib` |
| `src/components` | reusable UI | `domain`, `lib`; never `pages`, `routes`, `server` |
| `src/pages`, `src/routes`, `src/app` | one entry per URL, thin: fetch, call logic, render | everything above |

The direction is one way, from the edges inward. `dependency-cruiser` fails any other direction and any cycle. A rule
the stack needs to bend is a `decisions.md` line from the manager, never an inline exception.

Components follow the Atomic Design tree: `src/components/atoms/`, `src/components/molecules/`,
`src/components/organisms/` and `src/components/templates/`; a page is a route file in `src/pages/`, `src/routes/`
or `src/app/` and renders a template. Each level composes only the levels below it (an atom nothing, a molecule
atoms, an organism molecules and atoms, a template organisms and below, a page a template). `dependency-cruiser`
fails any other direction.

## 2. SOLID in this stack

- Single responsibility: a module changes for one reason. A route handler parses input, calls one function and
  returns; it never holds the business rule, the query and the formatting together.
- Open for extension: add behavior by adding a case, a strategy or a registry entry, not by growing a `switch` or an
  `if` chain in five places. Every `switch` over a union is exhaustive.
- Substitutable: an implementation of an interface honors its whole contract (same errors, same ranges); a component
  accepting `children` or a render prop never assumes what they are.
- Small interfaces: props and function parameters carry what the callee uses, not a whole record. More than three
  parameters becomes one typed object.
- Depend on abstractions: logic receives its collaborators (a clock, a fetcher, a repository) as parameters or
  through a thin port in `domain`, so a test passes a fake. No `new Date()`, `fetch` or database client inside a rule.

## 3. Scalability

- No work per item that could be work per batch: no query or network call inside a loop (N+1); fetch in bulk, then
  map. Lists that can grow are paginated or streamed; nothing loads "all" rows.
- Expensive and repeated reads are cached at the boundary with an explicit lifetime; nothing is cached without one.
- State lives at the lowest level that needs it; no module-level mutable state shared between requests.
- Configuration comes from the environment through one typed module, validated at start; no value inlined twice.
- Public routes are idempotent where the verb says so; a retry never double-charges, double-sends or double-writes.
- Ship less to the browser: split routes, lazy-load what is below the fold, no library for twenty lines of code.
- A module over 300 lines, a function over 60 or a file of unrelated exports is already the sign to split.

## 4. Security coding

- Validate every external input at the edge with a schema (body, query, headers, cookies, webhook payloads) and
  trust only the parsed value afterwards. Output is encoded for its context; never `dangerouslySetInnerHTML`,
  `innerHTML` or string-built HTML or SQL from input.
- Authorization is checked where the data is read or written, per resource, not only by hiding a button.
- Secrets exist only as environment variable names in code; none in source, logs, error messages or client bundles.
  Compare secrets and tokens in constant time; hash passwords with a slow hash, never a fast one.
- Outbound requests built from user input go through an allow-list of hosts; redirects only to allow-listed targets.
- Cookies are `Secure`, `HttpOnly` where script does not need them, `SameSite=Lax` or stricter; state-changing
  requests are protected against cross-site forgery.

## 5. Errors and tests

- Failures cross a boundary as typed results or errors the caller must handle; nothing is caught and ignored, and
  every caught error is logged with context but without personal data.
- Each acceptance criterion has a test that fails when the feature breaks: real inputs, the edge (empty, huge,
  malformed, repeated) and the failure path. A test asserting what the code merely returns is no test.
- **Only logic is tested.** Logic lives in `src/lib`, `src/domain`, `src/server`, `src/hooks` and `src/utils`, and
  it stays covered at 100 % of lines, branches, functions and statements. **Renders are never tested and never
  count toward coverage**: no test imports a component or a page (`dependency-cruiser` and the lint rules fail it);
  a hook is tested with `renderHook`, never with `render` or `screen`. UI correctness is covered by the end-to-end
  flow of the criteria. Tests do not depend on order, the clock or the network.

## 6. Code rules

- **Zero comments in code.** Code explains itself through names, types and small functions; comments and docstrings
  are forbidden. The per-file ratchet counts them (`tools/quality/ratchet.mjs`) and a file may never exceed its
  baseline count; a new file starts at zero.
- **Copy is data.** A render never carries its text as a JSX literal: the words come from props, a constant beside
  the component or a message catalog (`noJsxLiterals` fails a text literal in JSX). This keeps copy reviewable in
  one place and makes a later translation trivial.
- **Functions carry an explicit return type.** A named function states what it returns (`: string`,
  `: React.JSX.Element`, `: Promise<void>`); the lint rules fail an untyped one. The arrow callbacks of tests and
  library APIs are exempt.
- **A render holds no logic.** A component (a render) calls hooks and returns markup. Logic lives in custom hooks
  (`src/hooks/`), pure utilities (`src/utils/`) and the `domain`/`lib`/`server` layers. A render's cognitive
  complexity is 1 in Biome and 0 in SonarJS: branching beyond a simple conditional means the branch is a hook or a
  helper, not JSX.
- **The React Compiler memoizes.** `useMemo`, `useCallback` and `memo` are never written (the lint rules fail
  their import). Derived values are calculated from their sources; effects connect to external systems and clean
  up, they are not transformation pipelines.
- **Only logic is tested** (section 5). Test files end in `.test.ts` or `.test.tsx`.
- **Atomic Design tree** (section 1): components live in `atoms/`, `molecules/`, `organisms/`, `templates/`; each
  level composes only the levels below it and a page renders a template.

## 7. Gate and review

| The gate fails it | Review judges it |
|---|---|
| types, `any`, unsafe `any` flows | whether the types model the domain or only silence the compiler |
| complexity, nesting, size, parameters | whether the split follows responsibilities |
| duplication (4+ lines), dead code and exports | near-duplicates with other shape; code that is used but pointless |
| layer and cycle rules | whether new code sits in the right layer |
| known vulnerable or malicious packages, secrets, licenses | whether a new dependency is justified at all |
| unsafe patterns of the lint, Sonar and Semgrep rules | exploit paths no rule models: missing authorization, SSRF, logic flaws |
| missing tests, coverage floor | whether the tests would catch a regression |
