import type {
  Assessment,
  CatalogueItem,
  Decision,
  Health,
  Home,
  Reply,
} from "../types";

// Explicit offline test fixtures. Never imported by production components.
export const home: Home = {
  property_id: "UNIT-TEST",
  property_type: "Semi detached",
  age_band: 2,
  region: "E12000007",
  floor_area_m2: 100,
  epc_rating: "E",
  electricity_kwh: 4800,
  gas_kwh: 12000,
  heating: "gas_boiler",
  insulation: "poor",
  glazing: "single",
  solar_kwp: 0,
  smart_controls: false,
  roof_access: true,
  listed_building: false,
  consent_confirmed: false,
  heat_pump_ready: true,
  current_value_gbp: 350000,
  budget_gbp: null,
  data_kind: "synthetic_demo",
  space_heat_fraction: 0.8,
  boiler_efficiency: 0.85,
  heat_pump_spf: 3,
  solar_yield_kwh_per_kwp: 900,
  solar_self_consumption_fraction: 0.45,
};
export const catalogue: CatalogueItem[] = [
  {
    id: "loft_insulation",
    name: "Loft insulation",
    cost_gbp: [800, 1600],
    order: 0,
  },
  {
    id: "heat_pump",
    name: "Air-source heat pump",
    cost_gbp: [9000, 15000],
    order: 3,
  },
];
export const assessment: Assessment = {
  home,
  score: {
    total: 37,
    classification: "Poor",
    intensity_kwh_m2: 168,
    flagged: true,
    components: [
      { name: "Energy efficiency", weight: 0.25, score: 40, contribution: 10 },
    ],
    issues: ["Energy efficiency is a weak component."],
  },
  baseline: { electricity_kwh: 4800, gas_kwh: 12000, purchased_kwh: 16800 },
  selected_retrofits: ["heat_pump"],
  scenario: {
    electricity_kwh: 7520,
    gas_kwh: 2400,
    electricity_saving_kwh: -2720,
    gas_saving_kwh: 9600,
    net_saving_kwh: 6880,
    improvement_percent: 40.95238095,
    carbon_reduction_kgco2e: 1394.7648,
    cost_gbp: [9000, 15000],
    warnings: ["Electricity use increases."],
    assumptions: ["Unit-test scenario, not a live result."],
  },
  recommendations: catalogue.map((item) => ({
    ...item,
    feasible: true,
    suitability: "Medium",
    reason: "Unit-test feasibility reason.",
    standalone: null,
  })),
  value_impact: {
    status: "abstained",
    low_gbp: null,
    high_gbp: null,
    low_percent: null,
    high_percent: null,
    note: "No value result in this test.",
  },
  energy_benchmark: null,
  warnings: ["Fictional unit-test home."],
  sources: [],
};
export const health: Health = {
  status: "ok",
  models: { energy: true, value: true },
  gemini_configured: false,
};
export const reply: Reply = {
  status: "fallback_disabled",
  message: "Local calculation explanation; Gemini was not used.",
  lines: ["Only engine-supplied evidence is rendered."],
  claim_ids: ["estimate.caveat"],
  selected_retrofits: ["heat_pump"],
  assessment,
  applied: false,
  needs_clarification: false,
  parser_mode: "local_rules",
  explanation_mode: "local_template",
};
export const decision: Decision = {
  status: "available",
  objective: "purchased_energy",
  recommended_package: ["loft_insulation"],
  nominal_package: ["loft_insulation"],
  greedy_package: ["loft_insulation"],
  stable: true,
  scenario_count: 27,
  feasible_package_count: 4,
  regret_kwh: 0,
  next_check: null,
  packages: [],
  scenarios: [],
  assumptions: ["Analyst-selected stress cases, not probabilities."],
  warnings: [],
};
export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}
