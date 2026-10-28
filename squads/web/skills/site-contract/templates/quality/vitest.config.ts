import { defineConfig } from "vitest/config";

const RENDERS = [
  "src/components/**",
  "src/pages/**",
  "src/routes/**",
  "src/app/**",
  "src/layouts/**",
  "src/scene/**",
  "src/router.tsx",
];
const TESTS = "src/**/*.{test,spec}.{ts,tsx}";

export default defineConfig({
  test: {
    clearMocks: true,
    coverage: {
      exclude: [
        ...RENDERS,
        "src/routeTree.gen.ts",
        "src/paraglide/**",
        "**/*.astro",
        TESTS,
        "**/*.d.ts",
      ],
      include: ["src/**/*.{ts,tsx}"],
      provider: "v8",
      thresholds: { branches: 100, functions: 100, lines: 100, statements: 100 },
    },
    include: [TESTS],
    passWithNoTests: false,
    projects: [
      {
        extends: true,
        test: {
          environment: "node",
          exclude: ["src/hooks/**", ...RENDERS],
          include: [TESTS],
          name: "logic",
        },
      },
      {
        extends: true,
        test: {
          environment: "happy-dom",
          include: ["src/hooks/**/*.{test,spec}.{ts,tsx}"],
          name: "hooks",
        },
      },
    ],
  },
});
