import { defineConfig } from "vitest/config";

// Explicit opt-in. The ordinary unit suite blocks network access.
export default defineConfig({
  test: {
    environment: "node",
    include: ["smoke/api.smoke.ts"],
    testTimeout: 30_000,
    fileParallelism: false,
  },
});
