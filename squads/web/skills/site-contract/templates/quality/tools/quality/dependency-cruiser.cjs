// Architecture rules for every site: no cycles, logic never depends on UI, client code never imports server code,
// shipped code never imports dev-only packages. Written by site_base.py; workers never relax it.
/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [
    {
      name: "no-circular",
      severity: "error",
      comment: "A cycle couples two modules for good: extract what both need into a third.",
      from: {},
      to: { circular: true },
    },
    {
      name: "logic-never-imports-ui",
      severity: "error",
      comment: "Domain and helpers (src/lib, src/domain, src/server) stay testable without the UI (dependency inversion).",
      from: { path: "^src/(lib|domain|server)/" },
      to: { path: "^src/(components|pages|routes|app|layouts)/" },
    },
    {
      name: "components-never-import-pages",
      severity: "error",
      comment: "A component is reused by pages; it never reaches back into one.",
      from: { path: "^src/components/" },
      to: { path: "^src/(pages|routes|app)/" },
    },
    {
      name: "domain-is-framework-free",
      severity: "error",
      comment: "Business rules in src/domain depend on no UI or framework package: they stay portable and unit-testable.",
      from: { path: "^src/domain/" },
      to: { path: "^(react|react-dom|astro|next|@tanstack/[^/]+)(/|$)", dependencyTypes: ["npm"] },
    },
    {
      name: "client-never-imports-server",
      severity: "error",
      comment: "Server-only code (secrets, database) must not reach a client bundle.",
      from: { path: "^src/components/" },
      to: { path: "^src/server/" },
    },
    {
      name: "no-dev-dependency-in-src",
      severity: "error",
      comment: "Shipped code never imports a devDependency.",
      from: { path: "^src/", pathNot: "\\.(test|spec)\\.[cm]?[jt]sx?$" },
      to: { dependencyTypes: ["npm-dev"] },
    },
    {
      name: "no-unlisted-package",
      severity: "error",
      comment: "Every imported package is declared in package.json.",
      from: {},
      to: { dependencyTypes: ["unknown", "undetermined", "npm-no-pkg", "npm-unknown"], pathNot: "^vite/client$" },
    },
  ],
  options: {
    doNotFollow: { path: "node_modules" },
    exclude: { path: "(^|/)(node_modules|dist|\\.next|\\.astro|tools)/|routeTree\\.gen\\.ts$" },
    tsConfig: { fileName: "tsconfig.json" },
    tsPreCompilationDeps: true,
    enhancedResolveOptions: { exportsFields: ["exports"], conditionNames: ["import", "require", "node", "default"] },
  },
};
