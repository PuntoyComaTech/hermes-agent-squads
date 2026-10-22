import { defineConfig } from "vitest/config";

// Logic lives in src/lib (and src/domain, src/server): it is unit-tested and must stay covered.
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    passWithNoTests: false,
    coverage: {
      provider: "v8",
      include: ["src/lib/**", "src/domain/**", "src/server/**"],
      exclude: ["**/*.{test,spec}.{ts,tsx}"],
      thresholds: { lines: 80, functions: 80, branches: 80, statements: 80 },
    },
  },
});
