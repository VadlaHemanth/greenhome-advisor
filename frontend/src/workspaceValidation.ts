import { RETROFIT_IDS } from "./types";
import type { Home, HomeRanking, Preferences, Workspace } from "./types";

const obj = (v: unknown): v is Record<string, unknown> =>
  v !== null && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === "string";
const finite = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v);
const nullable = (v: unknown) => v === null || finite(v);
const nonnegative = (v: unknown) => v === null || (finite(v) && v >= 0);
const oneOf = (v: unknown, options: readonly unknown[]) => options.includes(v);
const ids = (v: unknown): boolean =>
  Array.isArray(v) &&
  v.length <= 5 &&
  new Set(v).size === v.length &&
  v.every((id) => oneOf(id, RETROFIT_IDS));
const date = (v: unknown) => text(v) && Number.isFinite(Date.parse(v));
const range = (v: unknown) =>
  Array.isArray(v) &&
  v.length === 2 &&
  v.every(nonnegative) &&
  (v[0] === null || v[1] === null || v[0] <= v[1]);

export function validHome(v: unknown): v is Home {
  if (!obj(v)) return false;
  return (
    (v.property_id === null || text(v.property_id)) &&
    oneOf(v.property_type, [
      null,
      "Detached",
      "Semi detached",
      "Mid terrace",
      "End terrace",
      "Bungalow",
      "Flat",
    ]) &&
    (v.age_band === null ||
      (finite(v.age_band) &&
        Number.isInteger(v.age_band) &&
        v.age_band >= 1 &&
        v.age_band <= 5)) &&
    (v.region === null || text(v.region)) &&
    oneOf(v.epc_rating, [null, "A", "A/B", "B", "C", "D", "E", "F", "G"]) &&
    oneOf(v.heating, [
      null,
      "gas_boiler",
      "heat_pump",
      "electric_resistance",
      "unknown",
    ]) &&
    oneOf(v.insulation, [null, "poor", "partial", "good", "unknown"]) &&
    oneOf(v.glazing, [null, "single", "double", "triple", "unknown"]) &&
    [
      "floor_area_m2",
      "electricity_kwh",
      "gas_kwh",
      "solar_kwp",
      "current_value_gbp",
      "budget_gbp",
    ].every((k) => nonnegative(v[k])) &&
    [
      "smart_controls",
      "roof_access",
      "listed_building",
      "consent_confirmed",
      "heat_pump_ready",
    ].every((k) => v[k] === null || typeof v[k] === "boolean") &&
    [
      "space_heat_fraction",
      "boiler_efficiency",
      "heat_pump_spf",
      "solar_yield_kwh_per_kwp",
      "solar_self_consumption_fraction",
    ].every((k) => v[k] === undefined || finite(v[k])) &&
    oneOf(v.data_kind, [null, "synthetic_demo", "user_entered"]) &&
    (v.excluded_retrofits === undefined || ids(v.excluded_retrofits))
  );
}

export function validPreferences(v: unknown): v is Preferences {
  return (
    obj(v) &&
    nonnegative(v.budget_gbp) &&
    ids(v.deferred_retrofits) &&
    oneOf(v.priority, ["energy", "carbon", "low_cost"]) &&
    oneOf(v.disruption, ["flexible", "minimal"])
  );
}

export function validWorkspace(v: unknown): v is Workspace {
  if (
    !obj(v) ||
    !text(v.id) ||
    !v.id ||
    v.mode !== "fictional_demo" ||
    !date(v.expires_at) ||
    !text(v.note) ||
    !oneOf(v.schema_version, [undefined, 1, 2]) ||
    !Array.isArray(v.customers) ||
    v.customers.length > 100
  )
    return false;
  const customerIds = new Set<unknown>(),
    propertyIds = new Set<unknown>(),
    homeIds = new Set<unknown>();
  const validVersion = (value: unknown) =>
    finite(value) && Number.isSafeInteger(value) && value >= 1;
  function validProperty(
    p: unknown,
    ownerId: string,
    legacy: boolean,
  ): boolean {
    if (
      !obj(p) ||
      !text(p.id) ||
      !p.id ||
      (!legacy && (p.customer_id !== ownerId || propertyIds.has(p.id))) ||
      !text(p.label) ||
      !p.label ||
      !validVersion(p.version) ||
      !validHome(p.home) ||
      p.home.data_kind !== "synthetic_demo" ||
      !p.home.property_id ||
      homeIds.has(p.home.property_id) ||
      !validPreferences(p.preferences) ||
      !ids(p.selected_retrofits) ||
      !oneOf(p.review_status, ["new", "reviewing", "ready", "deferred"]) ||
      !oneOf(p.baseline_status, ["current", "needs_update"]) ||
      !date(p.updated_at) ||
      !Array.isArray(p.events) ||
      p.events.length > 1000
    )
      return false;
    propertyIds.add(p.id);
    homeIds.add(p.home.property_id);
    const eventIds = new Set<unknown>();
    return p.events.every((e) => {
      if (
        !obj(e) ||
        !text(e.id) ||
        !e.id ||
        eventIds.has(e.id) ||
        e.kind !== "completed" ||
        !oneOf(e.retrofit_id, RETROFIT_IDS) ||
        !text(e.completed_on) ||
        !/^\d{4}-\d{2}-\d{2}$/.test(e.completed_on) ||
        !date(e.completed_on) ||
        !date(e.created_at) ||
        (e.planning_cost_upper_gbp !== undefined &&
          !nonnegative(e.planning_cost_upper_gbp))
      )
        return false;
      eventIds.add(e.id);
      return true;
    });
  }
  return v.customers.every((c) => {
    if (
      !obj(c) ||
      !text(c.id) ||
      !c.id ||
      customerIds.has(c.id) ||
      !text(c.label) ||
      !c.label ||
      !validVersion(c.version) ||
      !date(c.updated_at)
    )
      return false;
    customerIds.add(c.id);
    if (v.schema_version !== 2) return validProperty(c, c.id, true);
    const preferences = c.customer_preferences;
    const summary = c.budget_summary;
    if (
      !obj(preferences) ||
      !ids(preferences.deferred_retrofits) ||
      !oneOf(preferences.priority, ["energy", "carbon", "low_cost"]) ||
      !oneOf(preferences.disruption, ["flexible", "minimal"]) ||
      !nonnegative(c.portfolio_budget_gbp) ||
      !nonnegative(c.legacy_completed_reserve_gbp) ||
      !obj(summary) ||
      !finite(summary.planned_upper_gbp) ||
      summary.planned_upper_gbp < 0 ||
      !nonnegative(summary.completed_reserved_gbp) ||
      !nonnegative(summary.total_reserved_gbp) ||
      !nonnegative(summary.remaining_gbp) ||
      !oneOf(summary.status, [
        "unlimited",
        "within_budget",
        "needs_cost_evidence",
      ]) ||
      !Array.isArray(c.properties) ||
      c.properties.length < 1 ||
      c.properties.length > 8
    )
      return false;
    return c.properties.every((p) => validProperty(p, c.id as string, false));
  });
}

export function validRanking(v: unknown): v is HomeRanking {
  if (
    !obj(v) ||
    !text(v.policy) ||
    !Array.isArray(v.rows) ||
    v.rows.length > 100 ||
    !Array.isArray(v.warnings) ||
    !v.warnings.every(text)
  )
    return false;
  const homes = new Set<unknown>();
  return v.rows.every((r) => {
    if (
      !obj(r) ||
      !text(r.property_id) ||
      homes.has(r.property_id) ||
      !oneOf(r.status, [
        "available",
        "no_affordable_option",
        "no_modelled_benefit",
        "insufficient_evidence",
        "unsupported",
      ]) ||
      !text(r.reason) ||
      !text(r.classification) ||
      !nonnegative(r.score) ||
      (r.flagged !== null && typeof r.flagged !== "boolean") ||
      !(
        r.rank === null ||
        (finite(r.rank) && Number.isInteger(r.rank) && r.rank >= 1)
      ) ||
      ![
        "improvement_percent",
        "electricity_saving_kwh",
        "gas_saving_kwh",
        "carbon_reduction_kgco2e",
      ].every((k) => nullable(r[k])) ||
      !nonnegative(r.baseline_kwh) ||
      !nonnegative(r.budget_gbp) ||
      !(r.cost_gbp === null || range(r.cost_gbp)) ||
      !ids(r.selected_retrofits)
    )
      return false;
    homes.add(r.property_id);
    if (r.status === "insufficient_evidence" || r.status === "unsupported")
      return r.rank === null && r.improvement_percent === null;
    if (r.status === "available")
      return (
        finite(r.improvement_percent) &&
        finite(r.rank) &&
        finite(r.baseline_kwh) &&
        r.baseline_kwh > 0
      );
    return true;
  });
}
