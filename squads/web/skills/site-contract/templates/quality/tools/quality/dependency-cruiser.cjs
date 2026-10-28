"use strict";
const ATOMS = "^src/components/atoms/";
const MOLECULES = "^src/components/molecules/";
const ORGANISMS = "^src/components/organisms/";
const TEMPLATES = "^src/components/templates/";
const PAGES = "^src/(pages|routes|app)/";
const TEST_FILE = "[.](test|spec)[.][cm]?[jt]sx?$";
const UI_FOLDERS = "^src/(components|pages|routes|app|layouts)/";

module.exports = {
  forbidden: [
    {
      comment: "A cycle couples two modules for good: extract what both need into a third.",
      from: {},
      name: "no-circular",
      severity: "error",
      to: { circular: true },
    },
    {
      comment:
        "A module nothing reaches and that reaches nothing is dead code: delete it or wire it up.",
      from: {
        orphan: true,
        pathNot: [
          "[.]d[.]ts$",
          "[.]config[.](ts|mjs|cjs)$",
          "^src/routeTree[.]gen[.]ts$",
          PAGES,
          "__tests__/",
          TEST_FILE,
          "^e2e/",
          "^workers/[^/]+/src/index[.]ts$",
        ],
      },
      name: "no-orphans",
      severity: "error",
      to: {},
    },
    {
      comment: "An import that resolves to nothing is a bug the bundler ships to the browser.",
      from: {},
      name: "not-to-unresolvable",
      severity: "error",
      to: { couldNotResolve: true },
    },
    {
      comment: "One module is imported in one way (value or type), never both.",
      from: {},
      name: "no-duplicate-dep-types",
      severity: "error",
      to: { dependencyTypesNot: ["type-only"], moreThanOneDependencyType: true },
    },
    {
      comment: "An atom uses no other component level (Atomic Design).",
      from: { path: ATOMS },
      name: "atoms-stay-atoms",
      severity: "error",
      to: { path: [MOLECULES, ORGANISMS, TEMPLATES, PAGES] },
    },
    {
      comment: "A molecule composes atoms only (Atomic Design).",
      from: { path: MOLECULES },
      name: "molecules-use-atoms",
      severity: "error",
      to: { path: [ORGANISMS, TEMPLATES, PAGES] },
    },
    {
      comment: "An organism composes molecules and atoms only (Atomic Design).",
      from: { path: ORGANISMS },
      name: "organisms-use-molecules-and-atoms",
      severity: "error",
      to: { path: [TEMPLATES, PAGES] },
    },
    {
      comment: "A template composes organisms and below (Atomic Design).",
      from: { path: TEMPLATES },
      name: "templates-use-organisms-down",
      severity: "error",
      to: { path: [PAGES] },
    },
    {
      comment:
        "A page renders a template; organisms and below are composed inside templates (Atomic Design).",
      from: { path: PAGES },
      name: "pages-compose-templates",
      severity: "error",
      to: { path: [ATOMS, MOLECULES, ORGANISMS] },
    },
    {
      comment:
        "Domain and helpers (src/lib, src/domain, src/server, src/utils, src/hooks) stay testable without the UI (dependency inversion).",
      from: { path: "^src/(lib|domain|server|utils|hooks)/" },
      name: "logic-never-imports-ui",
      severity: "error",
      to: { path: UI_FOLDERS },
    },
    {
      comment: "A component is reused by pages; it never reaches back into one.",
      from: { path: "^src/components/" },
      name: "components-never-import-pages",
      severity: "error",
      to: { path: "^src/(pages|routes|app)/" },
    },
    {
      comment:
        "Business rules in src/domain depend on no UI or framework package: they stay portable and unit-testable.",
      from: { path: "^src/domain/" },
      name: "domain-is-framework-free",
      severity: "error",
      to: { dependencyTypes: ["npm"], path: "^(react|react-dom|astro|next|@tanstack/[^/]+)(/|$)" },
    },
    {
      comment: "A utility is plain logic: no hooks, no React, no UI.",
      from: { path: "^src/utils/" },
      name: "utils-are-pure",
      severity: "error",
      to: { path: ["^src/hooks/", "^src/components/", "^react$", "^react-dom"] },
    },
    {
      comment: "Server-only code (secrets, database) must not reach a client bundle.",
      from: { path: "^src/(components|hooks|utils)/" },
      name: "client-never-imports-server",
      severity: "error",
      to: { path: "^src/server/" },
    },
    {
      comment: "Only logic is tested: hooks, utils, domain, lib and the server. Renders never.",
      from: { path: ["__tests__/", TEST_FILE] },
      name: "tests-never-test-renders",
      severity: "error",
      to: { path: [UI_FOLDERS, "^src/scene/"] },
    },
    {
      comment: "Shipped code never imports a devDependency.",
      from: { path: "^src/", pathNot: TEST_FILE },
      name: "no-dev-dependency-in-src",
      severity: "error",
      to: { dependencyTypes: ["npm-dev"] },
    },
    {
      comment: "Every imported package is declared in package.json.",
      from: {},
      name: "no-unlisted-package",
      severity: "error",
      to: {
        dependencyTypes: ["unknown", "undetermined", "npm-no-pkg", "npm-unknown"],
        pathNot: "^vite/client$",
      },
    },
  ],
  options: {
    doNotFollow: { path: "node_modules" },
    enhancedResolveOptions: {
      conditionNames: ["import", "require", "node", "default"],
      exportsFields: ["exports"],
      extensions: [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json"],
    },
    exclude: {
      path: "(^|/)(node_modules|dist|\\\\.next|\\\\.astro|tools)/|routeTree\\\\.gen\\\\.ts$|paraglide/",
    },
    tsConfig: { fileName: "tsconfig.json" },
    tsPreCompilationDeps: true,
  },
};
