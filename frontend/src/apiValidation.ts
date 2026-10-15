import { RETROFIT_IDS } from "./types";
import { validRanking, validWorkspace } from "./workspaceValidation";
import { validEnergyInputs } from "./energyValidation";

type ObjectValue = Record<string, unknown>;
const object = (value: unknown): value is ObjectValue =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const number = (value: unknown) =>
  value === null || (typeof value === "number" && Number.isFinite(value));
const strings = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === "string");
const ids = (value: unknown) =>
  strings(value) &&
  value.length <= 5 &&
  new Set(value).size === value.length &&
  value.every((id) =>
    RETROFIT_IDS.includes(id as (typeof RETROFIT_IDS)[number]),
  );
const range = (value: unknown) =>
  Array.isArray(value) && value.length === 2 && value.every(number);
const optionalStrings = (value: unknown) =>
  value === undefined || value === null || strings(value);

function scenario(value: unknown): boolean {
  return (
    object(value) &&
    [
      "electricity_kwh",
      "gas_kwh",
      "electricity_saving_kwh",
      "gas_saving_kwh",
      "net_saving_kwh",
      "improvement_percent",
      "carbon_reduction_kgco2e",
    ].every((key) => number(value[key])) &&
    range(value.cost_gbp) &&
    strings(value.warnings) &&
    strings(value.assumptions)
  );
}

function decisionPackage(value: unknown): boolean {
  return (
    object(value) &&
    ids(value.retrofits) &&
    range(value.cost_gbp) &&
    [
      "nominal_saving_kwh",
      "min_saving_kwh",
      "max_saving_kwh",
      "max_regret_kwh",
      "nominal_carbon_kgco2e",
    ].every((key) => number(value[key]))
  );
}

function assessment(value: unknown): boolean {
  if (
    !object(value) ||
    !object(value.home) ||
    !object(value.score) ||
    !object(value.baseline) ||
    !object(value.value_impact) ||
    !scenario(value.scenario) ||
    !ids(value.selected_retrofits)
  )
    return false;
  const score = value.score,
    baseline = value.baseline,
    impact = value.value_impact;
  if (
    !number(score.total) ||
    typeof score.classification !== "string" ||
    !strings(score.issues) ||
    !Array.isArray(score.components) ||
    !score.components.every(
      (item) =>
        object(item) &&
        typeof item.name === "string" &&
        typeof item.weight === "number" &&
        Number.isFinite(item.weight) &&
        number(item.score) &&
        number(item.contribution),
    )
  )
    return false;
  if (
    !["electricity_kwh", "gas_kwh", "purchased_kwh"].every((key) =>
      number(baseline[key]),
    )
  )
    return false;
  if (
    typeof impact.status !== "string" ||
    typeof impact.note !== "string" ||
    !["low_gbp", "high_gbp", "low_percent", "high_percent"].every((key) =>
      number(impact[key]),
    )
  )
    return false;
  if (
    !Array.isArray(value.recommendations) ||
    !value.recommendations.every(
      (item) =>
        object(item) &&
        ids([item.id]) &&
        typeof item.name === "string" &&
        typeof item.feasible === "boolean" &&
        typeof item.reason === "string" &&
        typeof item.suitability === "string" &&
        range(item.cost_gbp) &&
        (item.standalone === null || scenario(item.standalone)),
    )
  )
    return false;
  return (
    strings(value.warnings) &&
    Array.isArray(value.sources) &&
    value.sources.every(
      (item) =>
        object(item) &&
        typeof item.label === "string" &&
        typeof item.url === "string",
    ) &&
    (value.energy_benchmark === null ||
      (object(value.energy_benchmark) &&
        typeof value.energy_benchmark.status === "string" &&
        typeof value.energy_benchmark.note === "string" &&
        number(value.energy_benchmark.electricity_kwh) &&
        number(value.energy_benchmark.gas_kwh)))
  );
}

/** Validate the fields components rely on; never coerce missing values to numbers. */
export function validApiPayload(path: string, value: unknown): boolean {
  if (path === "/energy-inputs") return validEnergyInputs(value);
  if (path === "/workspace/session")
    return value === null || validWorkspace(value);
  if (path === "/rank-homes") return validRanking(value);
  if (
    /^\/workspace\/customers\/[^/]+\/(?:properties(?:\/[^/]+(?:\/events)?)?|settings)$/.test(
      path,
    )
  )
    return validWorkspace(value) && value.schema_version === 2;
  if (path === "/workspace/delete")
    return (
      object(value) && (value.deleted === true || value.status === "deleted")
    );
  if (
    path === "/workspace" ||
    path === "/workspace/export" ||
    path.startsWith("/workspace/customers/")
  )
    return validWorkspace(value);
  if (path === "/demo-homes")
    return (
      Array.isArray(value) &&
      value.every(
        (item) =>
          object(item) &&
          typeof item.property_id === "string" &&
          typeof item.property_type === "string" &&
          (item.data_kind === "synthetic_demo" ||
            item.data_kind === "user_entered"),
      )
    );
  if (path === "/catalogue")
    return (
      Array.isArray(value) &&
      value.every(
        (item) =>
          object(item) &&
          ids([item.id]) &&
          typeof item.name === "string" &&
          range(item.cost_gbp) &&
          typeof item.order === "number",
      )
    );
  if (!object(value)) return false;
  if (path === "/health")
    return (
      typeof value.status === "string" &&
      object(value.models) &&
      Object.values(value.models).every((flag) => typeof flag === "boolean") &&
      typeof value.gemini_configured === "boolean" &&
      (value.llm_configured === undefined ||
        typeof value.llm_configured === "boolean") &&
      (value.llm_provider === undefined ||
        ["gemini", "xkiro"].includes(String(value.llm_provider))) &&
      ["llm_model", "llm_label", "llm_data_notice"].every(
        (key) => value[key] === undefined || typeof value[key] === "string",
      )
    );
  if (path === "/assess") return assessment(value);
  if (path === "/compare")
    return assessment(value.package_a) && assessment(value.package_b);
  if (path === "/what-if")
    return (
      typeof value.status === "string" &&
      typeof value.message === "string" &&
      typeof value.parser_mode === "string" &&
      typeof value.explanation_mode === "string" &&
      (value.provider === undefined || typeof value.provider === "string") &&
      (value.model === undefined || typeof value.model === "string") &&
      typeof value.applied === "boolean" &&
      typeof value.needs_clarification === "boolean" &&
      strings(value.lines) &&
      strings(value.claim_ids) &&
      ids(value.selected_retrofits) &&
      (value.assessment === null || assessment(value.assessment))
    );
  if (path === "/decision-check") {
    if (value.status !== "available" && value.status !== "unavailable")
      return false;
    if (!optionalStrings(value.warnings) || !optionalStrings(value.assumptions))
      return false;
    if (value.status === "unavailable") return true;
    return (
      ["recommended_package", "nominal_package", "greedy_package"].every(
        (key) => value[key] === null || ids(value[key]),
      ) &&
      (value.stable === null || typeof value.stable === "boolean") &&
      ["scenario_count", "feasible_package_count", "regret_kwh"].every((key) =>
        number(value[key]),
      ) &&
      (value.packages === undefined ||
        value.packages === null ||
        (Array.isArray(value.packages) &&
          value.packages.every(decisionPackage))) &&
      (value.next_check === undefined ||
        value.next_check === null ||
        (object(value.next_check) &&
          typeof value.next_check.question === "string" &&
          typeof value.next_check.reason === "string"))
    );
  }
  if (path === "/metrics") {
    if (value.status === "unavailable") return value.metrics === null;
    if (
      value.status !== "available" ||
      !object(value.metrics) ||
      !object(value.metrics.energy) ||
      !object(value.metrics.synthetic_value)
    )
      return false;
    return (
      Object.values(value.metrics.energy).every(
        (target) =>
          object(target) &&
          ["validation", "test"].every(
            (split) =>
              target[split] === undefined ||
              (object(target[split]) &&
                object(target[split].model) &&
                object(target[split].dummy_median)),
          ),
      ) &&
      ["validation", "test"].every(
        (split) =>
          value.metrics &&
          object(value.metrics) &&
          object(value.metrics.synthetic_value) &&
          (value.metrics.synthetic_value[split] === undefined ||
            object(value.metrics.synthetic_value[split])),
      )
    );
  }
  return true;
}
