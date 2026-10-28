import { fileURLToPath } from "node:url";
import noUnsanitized from "eslint-plugin-no-unsanitized";
import security from "eslint-plugin-security";
import sonarjs from "eslint-plugin-sonarjs";
import tseslint from "typescript-eslint";

const ROOT = fileURLToPath(new URL("../..", import.meta.url));
const MAX_COGNITIVE_COMPLEXITY = 10;
const MAX_RENDER_COGNITIVE_COMPLEXITY = 0;
const MAX_SWITCH_CASES = 10;
const MAX_FILE_LINES = 300;
const MAX_FUNCTION_LINES = 50;
const MAX_NESTING = 3;
const MAX_EXPRESSION_OPERATORS = 3;
const DUPLICATE_STRING_THRESHOLD = 2;
const sonarRules = sonarjs.rules ?? {};
const everySonarRule = Object.fromEntries(
  Object.keys(sonarRules)
    .filter((name) => sonarRules[name]?.meta?.deprecated !== true)
    .map((name) => [`sonarjs/${name}`, "error"]),
);

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
      "test-results/**",
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
    linterOptions: { reportUnusedDisableDirectives: "error", reportUnusedInlineConfigs: "error" },
    plugins: {
      "@typescript-eslint": tseslint.plugin,
      "no-unsanitized": noUnsanitized,
      security,
      sonarjs,
    },
    rules: {
      ...everySonarRule,
      ...security.configs.recommended.rules,
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/no-misused-promises": "error",
      "@typescript-eslint/no-unsafe-argument": "error",
      "@typescript-eslint/no-unsafe-assignment": "error",
      "@typescript-eslint/no-unsafe-call": "error",
      "@typescript-eslint/no-unsafe-member-access": "error",
      "@typescript-eslint/no-unsafe-return": "error",
      "@typescript-eslint/switch-exhaustiveness-check": "error",
      "no-eval": "error",
      "no-implied-eval": "error",
      "no-new-func": "error",
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              importNames: ["useCallback", "useMemo", "memo"],
              message: "The React Compiler memoizes; write plain code.",
              name: "react",
            },
            {
              importNames: ["useCallback", "useMemo"],
              message: "The React Compiler memoizes; write plain code.",
              name: "preact/hooks",
            },
            {
              importNames: ["render", "screen", "fireEvent", "within", "cleanup", "waitFor"],
              message:
                "Only logic is tested: test a hook with renderHook; renders are never tested.",
              name: "@testing-library/react",
            },
            {
              message: "Only logic is tested; renders are never tested.",
              name: "@testing-library/dom",
            },
          ],
        },
      ],
      "no-restricted-syntax": [
        "error",
        {
          message: "The React Compiler memoizes; write plain code.",
          selector: 'CallExpression[callee.name="memo"]',
        },
        {
          message: "The React Compiler memoizes; write plain code.",
          selector: 'MemberExpression[object.name="React"][property.name="memo"]',
        },
      ],
      "no-unsanitized/method": "error",
      "no-unsanitized/property": "error",
      "security/detect-object-injection": "off",
      "sonarjs/arrow-function-convention": [
        "error",
        { requireBodyBraces: false, requireParameterParentheses: true },
      ],
      "sonarjs/cognitive-complexity": ["error", MAX_COGNITIVE_COMPLEXITY],
      "sonarjs/expression-complexity": ["error", { max: MAX_EXPRESSION_OPERATORS }],
      "sonarjs/file-header": "off",
      "sonarjs/function-name": ["error", { format: "^[_a-zA-Z][a-zA-Z0-9]*$" }],
      "sonarjs/max-lines": ["error", { maximum: MAX_FILE_LINES }],
      "sonarjs/max-lines-per-function": ["error", { maximum: MAX_FUNCTION_LINES }],
      "sonarjs/max-switch-cases": ["error", MAX_SWITCH_CASES],
      "sonarjs/nested-control-flow": ["error", { maximumNestingLevel: MAX_NESTING }],
      "sonarjs/no-duplicate-string": ["error", { threshold: DUPLICATE_STRING_THRESHOLD }],
      "sonarjs/no-implicit-dependencies": "off",
      "sonarjs/no-reference-error": "off",
      "sonarjs/shorthand-property-grouping": "off",
    },
  },
  {
    basePath: ROOT,
    files: [
      "src/components/**/*.tsx",
      "src/pages/**/*.tsx",
      "src/routes/**/*.tsx",
      "src/app/**/*.tsx",
    ],
    rules: {
      "sonarjs/cognitive-complexity": ["error", MAX_RENDER_COGNITIVE_COMPLEXITY],
    },
  },
  {
    basePath: ROOT,
    files: [
      "*.config.ts",
      "*.config.mjs",
      "tools/quality/*.config.ts",
      "tools/quality/*.config.mjs",
    ],
    rules: { "sonarjs/file-name-differ-from-class": "off" },
  },
  {
    basePath: ROOT,
    files: ["src/components/**", "src/pages/**", "src/routes/**", "src/app/**"],
    rules: { "sonarjs/file-name-differ-from-class": "off" },
  },
];
