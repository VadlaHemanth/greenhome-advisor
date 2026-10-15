import type { EnergyInputs } from "../types";

export const monthlyPreview: EnergyInputs = {
  status: "complete",
  period: { start_month: "2025-01", end_month: "2025-12", expected_months: 12 },
  electricity_kwh: 2640,
  gas_kwh: 9600,
  purchased_kwh: 12240,
  coverage: { electricity_months: 12, gas_months: 12 },
  missing_months: [],
  ignored_rows: 0,
  months: Array.from({ length: 12 }, (_, i) => ({
    month: `2025-${String(i + 1).padStart(2, "0")}`,
    electricity_kwh: 220,
    gas_kwh: 800,
  })),
  warnings: [],
};
export const monthlyCsv =
  "month,electricity_kwh,gas_kwh\n" +
  monthlyPreview.months
    .map((row) => `${row.month},${row.electricity_kwh},${row.gas_kwh}`)
    .join("\n");
