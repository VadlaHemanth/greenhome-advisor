import type { HomeRanking, LegacyWorkspace } from "../types";
import { home } from "./fixtures";

// Deliberately fictional fixtures. Production does not import this module.
export const workspace: LegacyWorkspace = {
  id: "workspace-fixture",
  mode: "fictional_demo",
  expires_at: "2026-11-09T12:00:00Z",
  note: "Private fictional workspace; not a bank account or shared adviser access.",
  customers: Array.from({ length: 4 }, (_, i) => ({
    id: `customer-${i + 1}`,
    label: `Example household ${i + 1}`,
    version: 1,
    home: { ...home, property_id: `DEMO-0${i + 1}`, excluded_retrofits: [] },
    preferences: {
      budget_gbp: null,
      deferred_retrofits: [],
      priority: "energy",
      disruption: "flexible",
    },
    selected_retrofits: i === 0 ? ["loft_insulation"] : [],
    review_status: "new",
    baseline_status: "current",
    events: [],
    updated_at: "2026-10-10T12:00:00Z",
  })),
};
export const ranking: HomeRanking = {
  policy:
    "Maximum nominal purchased-energy reduction under each stated budget; upper indicative costs",
  rows: workspace.customers.map((c, i) => ({
    property_id: c.home.property_id!,
    rank: i < 2 ? 1 : i === 2 ? 3 : null,
    status:
      i === 3
        ? "insufficient_evidence"
        : i === 2
          ? "no_affordable_option"
          : "available",
    reason:
      i === 3
        ? "Annual fuel evidence is missing."
        : i === 2
          ? "No package fits this budget."
          : "Fictional ranking fixture.",
    score: i === 3 ? null : 37,
    classification: i === 3 ? "Unavailable" : "Poor",
    flagged: i === 3 ? null : true,
    improvement_percent: i < 2 ? 40.9523 : i === 2 ? 0 : null,
    baseline_kwh: i === 3 ? null : 16800,
    selected_retrofits: i < 2 ? ["heat_pump"] : [],
    electricity_saving_kwh: i === 3 ? null : -2720,
    gas_saving_kwh: i === 3 ? null : 9600,
    carbon_reduction_kgco2e: i === 3 ? null : 1394,
    cost_gbp: i === 3 ? null : [9000, 15000],
    budget_gbp: i === 2 ? 0 : null,
  })),
  warnings: ["Test fixtures, not measured household outcomes."],
};
