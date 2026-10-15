import { describe, expect, it } from "vitest";
import { ukCalendarDate } from "../workspaceModel";

describe("UK completion calendar", () => {
  it("uses the next local day during British Summer Time", () => {
    expect(ukCalendarDate(new Date("2026-10-10T23:30:00Z"))).toBe("2026-10-11");
  });
  it("uses GMT during winter independently of the browser timezone", () => {
    expect(ukCalendarDate(new Date("2026-12-10T23:30:00Z"))).toBe("2026-12-10");
  });
});
