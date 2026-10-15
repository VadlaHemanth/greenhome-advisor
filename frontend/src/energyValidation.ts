import type { EnergyInputs } from "./types";

/** Fail closed on an incomplete or inconsistent preview; never annualise here. */
export function validEnergyInputs(value: unknown): value is EnergyInputs {
  if (!value || typeof value !== "object") return false;
  const v = value as EnergyInputs;
  const month = (s: unknown): s is string =>
    typeof s === "string" && /^\d{4}-(0[1-9]|1[0-2])$/.test(s);
  const fuel = (n: unknown) =>
    n === null || (typeof n === "number" && Number.isFinite(n) && n >= 0);
  const strings = (s: unknown): s is string[] =>
    Array.isArray(s) && s.every((item) => typeof item === "string");
  if (
    !["complete", "partial"].includes(v.status) ||
    !v.period ||
    !v.coverage ||
    v.period.expected_months !== 12 ||
    !month(v.period.start_month) ||
    !month(v.period.end_month) ||
    !Array.isArray(v.months) ||
    v.months.length !== 12 ||
    !strings(v.warnings) ||
    !strings(v.missing_months) ||
    !v.missing_months.every(month) ||
    !Number.isInteger(v.ignored_rows) ||
    v.ignored_rows < 0 ||
    !fuel(v.electricity_kwh) ||
    !fuel(v.gas_kwh) ||
    !fuel(v.purchased_kwh)
  )
    return false;
  const end = new Date(`${v.period.end_month}-01T00:00:00Z`);
  const now = new Date();
  if (end >= new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1)))
    return false;
  const expected = Array.from({ length: 12 }, (_, i) => {
    const date = new Date(end);
    date.setUTCMonth(date.getUTCMonth() - 11 + i);
    return date.toISOString().slice(0, 7);
  });
  if (
    v.period.start_month !== expected[0] ||
    !v.months.every(
      (row, i) =>
        row &&
        row.month === expected[i] &&
        fuel(row.electricity_kwh) &&
        fuel(row.gas_kwh),
    ) ||
    !v.missing_months.every((m) => expected.includes(m))
  )
    return false;
  for (const [key, coverage] of [
    ["electricity_kwh", "electricity_months"],
    ["gas_kwh", "gas_months"],
  ] as const) {
    const count = v.months.filter((row) => row[key] !== null).length;
    if (v.coverage[coverage] !== count || (count === 12) !== (v[key] !== null))
      return false;
  }
  const complete = v.electricity_kwh !== null && v.gas_kwh !== null;
  return (
    v.status === (complete ? "complete" : "partial") &&
    (v.purchased_kwh !== null) === complete
  );
}
