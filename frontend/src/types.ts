export const RETROFIT_IDS = [
  "loft_insulation",
  "double_glazing",
  "smart_controls",
  "heat_pump",
  "solar_pv",
] as const;
export type RetrofitId = (typeof RETROFIT_IDS)[number];
export type NullableNumber = number | null;
export type Home = {
  property_id: string | null;
  property_type:
    | "Detached"
    | "Semi detached"
    | "Mid terrace"
    | "End terrace"
    | "Bungalow"
    | "Flat"
    | null;
  age_band: number | null;
  region: string | null;
  floor_area_m2: NullableNumber;
  epc_rating: string | null;
  electricity_kwh: NullableNumber;
  gas_kwh: NullableNumber;
  heating:
    | "gas_boiler"
    | "heat_pump"
    | "electric_resistance"
    | "unknown"
    | null;
  insulation: "poor" | "partial" | "good" | "unknown" | null;
  glazing: "single" | "double" | "triple" | "unknown" | null;
  solar_kwp: NullableNumber;
  smart_controls: boolean | null;
  roof_access: boolean | null;
  listed_building: boolean | null;
  consent_confirmed: boolean | null;
  heat_pump_ready: boolean | null;
  space_heat_fraction?: number;
  boiler_efficiency?: number;
  heat_pump_spf?: number;
  solar_yield_kwh_per_kwp?: number;
  solar_self_consumption_fraction?: number;
  current_value_gbp: NullableNumber;
  budget_gbp: NullableNumber;
  data_kind: "synthetic_demo" | "user_entered" | null;
  excluded_retrofits?: RetrofitId[];
};
export type CatalogueItem = {
  id: RetrofitId;
  name: string;
  cost_gbp: [number, number];
  order: number;
};
export type Scenario = {
  electricity_kwh: NullableNumber;
  gas_kwh: NullableNumber;
  electricity_saving_kwh: NullableNumber;
  gas_saving_kwh: NullableNumber;
  net_saving_kwh: NullableNumber;
  improvement_percent: NullableNumber;
  carbon_reduction_kgco2e: NullableNumber;
  cost_gbp: [NullableNumber, NullableNumber];
  warnings: string[];
  assumptions: string[];
};
export type Recommendation = {
  id: RetrofitId;
  name: string;
  feasible: boolean;
  suitability: string;
  reason: string;
  cost_gbp: [number, number];
  standalone: Scenario | null;
};
export type Assessment = {
  home: Home;
  score: {
    total: NullableNumber;
    classification: string;
    flagged?: boolean;
    intensity_kwh_m2?: NullableNumber;
    components: {
      name: string;
      weight: number;
      score: NullableNumber;
      contribution: NullableNumber;
    }[];
    issues: string[];
  };
  baseline: {
    electricity_kwh: NullableNumber;
    gas_kwh: NullableNumber;
    purchased_kwh: NullableNumber;
  };
  recommendations: Recommendation[];
  selected_retrofits: RetrofitId[];
  scenario: Scenario;
  value_impact: {
    status: string;
    low_gbp: NullableNumber;
    high_gbp: NullableNumber;
    low_percent: NullableNumber;
    high_percent: NullableNumber;
    note: string;
  };
  energy_benchmark: {
    status: string;
    note: string;
    electricity_kwh: NullableNumber;
    gas_kwh: NullableNumber;
  } | null;
  warnings: string[];
  sources: { label: string; url: string }[];
};
export type Health = {
  status: string;
  models: Record<string, boolean>;
  gemini_configured: boolean;
  llm_configured?: boolean;
  llm_provider?: "gemini" | "xkiro";
  llm_model?: string;
  llm_label?: string;
  llm_data_notice?: string;
};
export type EnergyInputs = {
  status: "complete" | "partial";
  period: { start_month: string; end_month: string; expected_months: 12 };
  electricity_kwh: NullableNumber;
  gas_kwh: NullableNumber;
  purchased_kwh: NullableNumber;
  coverage: { electricity_months: number; gas_months: number };
  missing_months: string[];
  ignored_rows: number;
  months: {
    month: string;
    electricity_kwh: NullableNumber;
    gas_kwh: NullableNumber;
  }[];
  warnings: string[];
};
export type Comparison = { package_a: Assessment; package_b: Assessment };
export type Reply = {
  provider?: string;
  model?: string;
  status: string;
  message: string;
  lines: string[];
  claim_ids: string[];
  selected_retrofits: RetrofitId[];
  assessment: Assessment | null;
  applied: boolean;
  needs_clarification: boolean;
  parser_mode: string;
  explanation_mode: string;
};
export type ErrorMetric = { mae?: number; rmse?: number; n?: number };
export type EnergyEvaluation = {
  model: ErrorMetric;
  dummy_median: ErrorMetric;
  mae_improvement_percent_vs_dummy?: number;
};
export type ValueEvaluation = {
  p50_percent?: ErrorMetric;
  dummy_median_percent?: ErrorMetric;
  p50_gbp?: ErrorMetric;
  coverage_p10_p90_all_scenarios?: number;
  coverage_p10_p90_active_scenarios?: number;
  [key: string]: unknown;
};
export type Metrics = {
  status: string;
  note?: string;
  metrics: {
    energy: Record<
      string,
      Partial<Record<"validation" | "test", EnergyEvaluation>>
    >;
    synthetic_value: {
      validation?: ValueEvaluation;
      test?: ValueEvaluation;
      nominal_interval_coverage?: number;
    };
  } | null;
};
export type Decision = {
  status: "available" | "unavailable";
  objective: string;
  recommended_package: RetrofitId[] | null;
  nominal_package: RetrofitId[] | null;
  greedy_package: RetrofitId[] | null;
  stable: boolean | null;
  scenario_count: NullableNumber;
  feasible_package_count: NullableNumber;
  regret_kwh: NullableNumber;
  next_check: { field: string | null; question: string; reason: string } | null;
  packages?:
    | {
        retrofits: RetrofitId[];
        cost_gbp: [NullableNumber, NullableNumber];
        nominal_saving_kwh: NullableNumber;
        min_saving_kwh: NullableNumber;
        max_saving_kwh: NullableNumber;
        max_regret_kwh: NullableNumber;
        nominal_carbon_kgco2e: NullableNumber;
      }[]
    | null;
  scenarios?:
    | {
        id: string;
        assumptions: Record<string, unknown>;
        best_package: RetrofitId[];
        best_saving_kwh: NullableNumber;
      }[]
    | null;
  assumptions?: string[] | null;
  warnings?: string[] | null;
};
export type Page =
  | "welcome"
  | "money"
  | "dashboard"
  | "home"
  | "improvements"
  | "what-if"
  | "reports"
  | "plan"
  | "homes"
  | "workspace";

export type RankingStatus =
  | "available"
  | "no_affordable_option"
  | "no_modelled_benefit"
  | "insufficient_evidence"
  | "unsupported";
export type RankedHome = {
  property_id: string;
  rank: NullableNumber;
  status: RankingStatus;
  reason: string;
  score: NullableNumber;
  classification: string;
  flagged: boolean | null;
  improvement_percent: NullableNumber;
  baseline_kwh: NullableNumber;
  selected_retrofits: RetrofitId[];
  electricity_saving_kwh: NullableNumber;
  gas_saving_kwh: NullableNumber;
  carbon_reduction_kgco2e: NullableNumber;
  cost_gbp: [NullableNumber, NullableNumber] | null;
  budget_gbp: NullableNumber;
};
export type HomeRanking = {
  policy: string;
  rows: RankedHome[];
  warnings: string[];
};
export type Preferences = {
  budget_gbp: NullableNumber;
  deferred_retrofits: RetrofitId[];
  priority: "energy" | "carbon" | "low_cost";
  disruption: "flexible" | "minimal";
};
export type ReviewStatus = "new" | "reviewing" | "ready" | "deferred";
export type CompletionEvent = {
  id: string;
  kind: "completed";
  retrofit_id: RetrofitId;
  completed_on: string;
  created_at: string;
  /** Planning reservation, never actual spending. Missing on legacy events. */
  planning_cost_upper_gbp?: NullableNumber;
};
export type WorkspaceProperty = {
  id: string;
  customer_id: string;
  label: string;
  version: number;
  home: Home;
  preferences: Preferences;
  selected_retrofits: RetrofitId[];
  review_status: ReviewStatus;
  baseline_status: "current" | "needs_update";
  events: CompletionEvent[];
  updated_at: string;
};
export type CustomerPreferences = Omit<Preferences, "budget_gbp">;
export type BudgetSummary = {
  planned_upper_gbp: number;
  completed_reserved_gbp: NullableNumber;
  total_reserved_gbp: NullableNumber;
  remaining_gbp: NullableNumber;
  status: "unlimited" | "within_budget" | "needs_cost_evidence";
};
export type WorkspaceCustomer = {
  id: string;
  label: string;
  version: number;
  updated_at: string;
  customer_preferences: CustomerPreferences;
  portfolio_budget_gbp: NullableNumber;
  legacy_completed_reserve_gbp: NullableNumber;
  budget_summary: BudgetSummary;
  properties: WorkspaceProperty[];
};
/** Read-only compatibility input. New UI never accesses root property projections. */
export type LegacyWorkspaceCustomer = Omit<WorkspaceProperty, "customer_id">;
type WorkspaceBase = {
  id: string;
  mode: "fictional_demo";
  expires_at: string;
  note: string;
};
export type LegacyWorkspace = WorkspaceBase & {
  schema_version?: 1;
  customers: LegacyWorkspaceCustomer[];
};
export type CanonicalWorkspace = WorkspaceBase & {
  schema_version: 2;
  customers: WorkspaceCustomer[];
};
export type Workspace = CanonicalWorkspace | LegacyWorkspace;
export type WorkspaceView = WorkspaceBase & {
  schema_version: 1 | 2;
  customers: WorkspaceCustomer[];
};
export type CustomerUpdate = Pick<
  WorkspaceProperty,
  "version" | "home" | "preferences" | "selected_retrofits" | "review_status"
> & {
  baseline_confirmed_after_completion?: boolean;
};
export type PropertyUpdate = CustomerUpdate & { customer_version: number };
export type CustomerSettingsUpdate = {
  version: number;
  customer_preferences: CustomerPreferences;
  portfolio_budget_gbp: NullableNumber;
  legacy_completed_reserve_gbp: NullableNumber;
  confirm_legacy_reserve: boolean;
};
export type CompletionInput = {
  version: number;
  kind: "completed";
  retrofit_id: RetrofitId;
  completed_on: string;
  confirmed: true;
};
export type PropertyCompletionInput = CompletionInput & {
  customer_version: number;
};
export type CompletionDraft = Omit<CompletionInput, "version">;
export const DEMO_TEMPLATE_IDS = [
  "DEMO-01",
  "DEMO-02",
  "DEMO-03",
  "DEMO-04",
] as const;
export type DemoTemplateId = (typeof DEMO_TEMPLATE_IDS)[number];
