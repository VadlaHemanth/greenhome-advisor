import type { Home } from "./types";
export function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}
export function number(value: unknown, decimals = 0, signed = false): string {
  if (!isNumber(value)) return "Unavailable";
  return new Intl.NumberFormat("en-GB", {
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
    signDisplay: signed ? "exceptZero" : "auto",
  }).format(value);
}
export function money(value: unknown) {
  return isNumber(value) ? `£${number(value)}` : "Unavailable";
}
export function moneyRange(range: (number | null)[] | undefined | null) {
  return range && range.length === 2 && range.every(isNumber)
    ? `${money(range[0])}–${money(range[1])}`
    : "Unavailable";
}
export function percentageRange(low: unknown, high: unknown) {
  return isNumber(low) && isNumber(high)
    ? `${number(low, 1)}–${number(high, 1)}%`
    : "Unavailable";
}
export const REGIONS: Record<string, string> = {
  E12000001: "North East",
  E12000002: "North West",
  E12000003: "Yorkshire and the Humber",
  E12000004: "East Midlands",
  E12000005: "West Midlands",
  E12000006: "East of England",
  E12000007: "London",
  E12000008: "South East",
  E12000009: "South West",
  W92000004: "Wales",
};
export const HEATING: Record<string, string> = {
  gas_boiler: "Gas boiler",
  heat_pump: "Heat pump",
  electric_resistance: "Electric resistance",
  unknown: "Unknown",
};
export function newHome(): Home {
  return {
    property_id: "MY-HOME",
    property_type: null,
    region: null,
    age_band: null,
    floor_area_m2: null,
    epc_rating: null,
    electricity_kwh: null,
    gas_kwh: null,
    heating: "unknown",
    insulation: "unknown",
    glazing: "unknown",
    solar_kwp: null,
    smart_controls: null,
    roof_access: null,
    listed_building: null,
    consent_confirmed: null,
    heat_pump_ready: null,
    current_value_gbp: null,
    budget_gbp: null,
    data_kind: "user_entered",
  };
}
