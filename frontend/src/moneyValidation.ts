import { RETROFIT_IDS } from "./types";
import type {
  MoneyAmounts,
  MoneyPlanResponse,
  MoneyTariffDraft,
  MoneyTariffErrors,
  MoneyTariffs,
} from "./moneyTypes";

const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const finite = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);
const nullable = (value: unknown): value is number | null =>
  value === null || finite(value);
const nonnegative = (value: unknown): value is number =>
  finite(value) && value >= 0;
const rate = (value: unknown, maximum: number) =>
  value === null || (nonnegative(value) && value <= maximum);
const range = (value: unknown): value is [number, number] =>
  Array.isArray(value) &&
  value.length === 2 &&
  value.every(nonnegative) &&
  value[0] <= value[1];

function calendarDate(value: unknown): value is string {
  if (
    typeof value !== "string" ||
    !/^\d{4}-\d{2}-\d{2}$/.test(value) ||
    value.startsWith("0000-")
  )
    return false;
  const date = new Date(`${value}T00:00:00Z`);
  return (
    Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value
  );
}

/** Empty is unknown, zero is an explicit rate. Nothing is defaulted to 25/7. */
export function parseMoneyTariffs(draft: MoneyTariffDraft): {
  tariffs: MoneyTariffs | null;
  errors: MoneyTariffErrors;
} {
  const errors: MoneyTariffErrors = {};
  function parse(field: "electricity_pence" | "gas_pence") {
    const text = draft[field].trim();
    if (!text) return null;
    const value = Number(text);
    if (
      !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(text) ||
      !finite(value) ||
      value < 0 ||
      value > 200
    ) {
      errors[field] =
        "Enter a finite rate from 0 to 200 p/kWh, or leave blank.";
      return null;
    }
    return value;
  }
  const electricity_pence = parse("electricity_pence");
  const gas_pence = parse("gas_pence");
  const as_of = draft.as_of.trim() || null;
  if (as_of !== null && !calendarDate(as_of))
    errors.as_of = "Enter a real calendar date (YYYY-MM-DD), or leave blank.";
  return {
    errors,
    tariffs: Object.keys(errors).length
      ? null
      : {
          electricity_pence,
          gas_pence,
          source: draft.source,
          as_of,
          electricity_standing_before_pence_per_day: null,
          electricity_standing_after_pence_per_day: null,
          gas_standing_before_pence_per_day: null,
          gas_standing_after_pence_per_day: null,
        },
  };
}

function amounts(value: unknown): value is MoneyAmounts {
  if (!record(value)) return false;
  return (
    (value.before_gbp === null || nonnegative(value.before_gbp)) &&
    (value.after_gbp === null || nonnegative(value.after_gbp)) &&
    nullable(value.saving_gbp) &&
    (value.saving_gbp !== null) ===
      (value.before_gbp !== null && value.after_gbp !== null)
  );
}

/** Fail closed on malformed money, missing-data claims or dangling picks.
 * The server remains the calculator and package selector; this never ranks,
 * fills unknowns, or replaces the server's numerical outputs.
 */
export function validMoneyPlan(value: unknown): value is MoneyPlanResponse {
  if (!record(value)) return false;
  const v = value as MoneyPlanResponse;
  if (
    !record(v.money) ||
    !record(v.tariffs) ||
    !record(v.picks) ||
    !Array.isArray(v.packages) ||
    !Array.isArray(v.warnings) ||
    !v.warnings.every((warning) => typeof warning === "string")
  )
    return false;

  const m = v.money;
  if (
    !amounts(m.electricity) ||
    !amounts(m.gas) ||
    !amounts(m.total) ||
    !nullable(m.monthly_average_gbp) ||
    !range(m.cost_gbp) ||
    typeof m.standing_charge_note !== "string" ||
    !["user_entered", "illustrative"].includes(v.tariffs.source) ||
    !(v.tariffs.as_of === null || calendarDate(v.tariffs.as_of)) ||
    !rate(v.tariffs.electricity_pence, 200) ||
    !rate(v.tariffs.gas_pence, 200) ||
    !rate(v.tariffs.electricity_standing_before_pence_per_day, 1000) ||
    !rate(v.tariffs.electricity_standing_after_pence_per_day, 1000) ||
    !rate(v.tariffs.gas_standing_before_pence_per_day, 1000) ||
    !rate(v.tariffs.gas_standing_after_pence_per_day, 1000)
  )
    return false;

  const complete =
    m.electricity.saving_gbp !== null && m.gas.saving_gbp !== null;
  const anyKnown = [m.electricity, m.gas].some((fuel) =>
    Object.values(fuel).some((amount) => amount !== null),
  );
  if (
    m.status !==
      (complete ? "available" : anyKnown ? "partial" : "unavailable") ||
    (m.total.saving_gbp !== null) !== complete ||
    (m.monthly_average_gbp !== null) !== complete ||
    (!complete && Object.values(m.total).some((amount) => amount !== null))
  )
    return false;
  for (const fuel of ["electricity", "gas"] as const) {
    if (
      v.tariffs[`${fuel}_pence`] === null &&
      Object.values(m[fuel]).some((amount) => amount !== null)
    )
      return false;
  }
  if (
    m.payback_years !== null &&
    (!record(m.payback_years) ||
      !range([m.payback_years.low, m.payback_years.high]) ||
      m.total.saving_gbp === null ||
      m.total.saving_gbp <= 0)
  )
    return false;

  const packageIds = new Set<string>();
  for (const item of v.packages) {
    if (
      !record(item) ||
      typeof item.id !== "string" ||
      !Array.isArray(item.retrofits) ||
      item.retrofits.length === 0 ||
      item.retrofits.length > RETROFIT_IDS.length ||
      !item.retrofits.every((id) => RETROFIT_IDS.includes(id)) ||
      new Set(item.retrofits).size !== item.retrofits.length ||
      item.id !==
        RETROFIT_IDS.filter((id) => item.retrofits.includes(id)).join("+") ||
      packageIds.has(item.id) ||
      !range(item.cost_gbp) ||
      !nullable(item.net_saving_kwh) ||
      !nullable(item.improvement_percent) ||
      !nullable(item.carbon_reduction_kgco2e) ||
      !nullable(item.money_saving_gbp) ||
      (!complete && item.money_saving_gbp !== null) ||
      typeof item.recommendation_reason !== "string"
    )
      return false;
    packageIds.add(item.id);
  }
  for (const objective of ["energy", "bills", "lowest_cost"] as const) {
    const pick = v.picks[objective];
    if (pick === null) continue;
    if (typeof pick !== "string" || !packageIds.has(pick)) return false;
    const item = v.packages.find((item) => item.id === pick)!;
    if (
      (objective === "bills" &&
        (item.money_saving_gbp === null || item.money_saving_gbp <= 0)) ||
      (objective === "energy" &&
        (item.improvement_percent === null || item.improvement_percent <= 0))
    )
      return false;
  }
  return complete || v.picks.bills === null;
}
