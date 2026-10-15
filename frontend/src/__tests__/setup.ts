import { afterEach, beforeEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

beforeEach(() => {
  // All tests are offline. An accidental network request must never reach an API.
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new Error("Unmocked network request blocked by test setup");
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
