import { describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { validApiPayload } from "../apiValidation";
import { monthlyCsv, monthlyPreview } from "./energyFixtures";
import { health } from "./fixtures";

describe("monthly API and neutral provider contract", () => {
  it("rejects a preview for a different requested period", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify(monthlyPreview), { status: 200 }),
    );
    await expect(api.energyInputs(monthlyCsv, "2025-11")).rejects.toThrow(
      "different monthly period",
    );
  });
  it("posts only CSV and the chosen month to the checked endpoint", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify(monthlyPreview), { status: 200 }),
    );
    expect(await api.energyInputs(monthlyCsv, "2025-12")).toEqual(
      monthlyPreview,
    );
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/energy-inputs");
    expect(JSON.parse(init!.body as string)).toEqual({
      csv_text: monthlyCsv,
      end_month: "2025-12",
    });
  });
  it("accepts complete and partial previews, not invented zeroes for missing fuel", () => {
    expect(validApiPayload("/energy-inputs", monthlyPreview)).toBe(true);
    const partial = {
      ...monthlyPreview,
      status: "partial",
      gas_kwh: null,
      purchased_kwh: null,
      coverage: { electricity_months: 12, gas_months: 11 },
      months: monthlyPreview.months.map((row, i) =>
        i === 0 ? { ...row, gas_kwh: null } : row,
      ),
    };
    expect(validApiPayload("/energy-inputs", partial)).toBe(true);
    expect(validApiPayload("/energy-inputs", { ...partial, gas_kwh: 0 })).toBe(
      false,
    );
  });
  it.each([
    { months: [] },
    { coverage: null },
    { purchased_kwh: Infinity },
    { ignored_rows: -1 },
    { status: "invented" },
    { warnings: null },
    {
      period: {
        start_month: "2099-01",
        end_month: "2099-12",
        expected_months: 12,
      },
    },
  ])("rejects malformed previews: %j", (change) => {
    expect(
      validApiPayload("/energy-inputs", { ...monthlyPreview, ...change }),
    ).toBe(false);
  });
  it("accepts legacy health while validating optional provider fields", () => {
    expect(validApiPayload("/health", health)).toBe(true);
    expect(
      validApiPayload("/health", {
        ...health,
        llm_configured: true,
        llm_provider: "xkiro",
        llm_label: "Qwen via Xkiro",
        llm_model: "test",
        llm_data_notice: "Third-party gateway",
      }),
    ).toBe(true);
    expect(
      validApiPayload("/health", { ...health, llm_configured: "yes" }),
    ).toBe(false);
  });
});
