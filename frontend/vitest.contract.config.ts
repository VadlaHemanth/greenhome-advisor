import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["smoke/*.contract.ts"],
    testTimeout: 30_000,
    fileParallelism: false,
  },
});
