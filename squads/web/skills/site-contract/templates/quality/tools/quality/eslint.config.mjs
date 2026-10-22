// SonarJS (the Sonar rules, run locally) plus typed TypeScript rules: complexity, duplication, bugs and unsafe any.
// Written by site_base.py. Workers never relax it; a rule that blocks real work goes to the manager.
import { fileURLToPath } from "node:url";
import noUnsanitized from "eslint-plugin-no-unsanitized";
import security from "eslint-plugin-security";
import sonarjs from "eslint-plugin-sonarjs";
import tseslint from "typescript-eslint";

const ROOT = fileURLToPath(new URL("../..", import.meta.url));

export default [
  {
    basePath: ROOT,
    ignores: [
      "**/node_modules/**",
      "dist/**",
      ".next/**",
      ".astro/**",
      ".wrangler/**",
      "coverage/**",
      "playwright-report/**",
      "tools/**",
      "src/routeTree.gen.ts",
      "**/*.d.ts",
    ],
  },
  {
    basePath: ROOT,
    files: ["**/*.{ts,tsx,mts,cts}"],
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: { projectService: true, tsconfigRootDir: ROOT },
    },
    linterOptions: { reportUnusedDisableDirectives: "error" },
    plugins: { sonarjs, security, "no-unsanitized": noUnsanitized, "@typescript-eslint": tseslint.plugin },
    rules: {
      ...sonarjs.configs.recommended.rules,
      ...security.configs.recommended.rules,
      "security/detect-object-injection": "off", // flags every obj[key]: far more noise than signal
      "no-unsanitized/method": "error",
      "no-unsanitized/property": "error",
      "no-eval": "error",
      "no-implied-eval": "error",
      "no-new-func": "error",
      "sonarjs/cognitive-complexity": ["error", 10],
      "sonarjs/expression-complexity": ["error", { max: 3 }],
      "sonarjs/nested-control-flow": ["error", { maximumNestingLevel: 3 }],
      "sonarjs/no-duplicate-string": ["error", { threshold: 3 }],
      "sonarjs/max-lines": ["error", { maximum: 300 }],
      "sonarjs/max-lines-per-function": ["error", { maximum: 60 }],
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unsafe-argument": "error",
      "@typescript-eslint/no-unsafe-assignment": "error",
      "@typescript-eslint/no-unsafe-call": "error",
      "@typescript-eslint/no-unsafe-member-access": "error",
      "@typescript-eslint/no-unsafe-return": "error",
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/no-misused-promises": "error",
      "@typescript-eslint/switch-exhaustiveness-check": "error",
    },
  },
];
