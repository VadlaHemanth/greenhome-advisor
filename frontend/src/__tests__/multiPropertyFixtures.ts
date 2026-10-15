import type { CanonicalWorkspace, WorkspaceProperty } from "../types";
import { home } from "./fixtures";

// Offline UI fixtures only; no real participant/customer data.
export function propertyFixture(
  owner: string,
  index: number,
): WorkspaceProperty {
  return {
    id: `${owner}-property-${index}`,
    customer_id: owner,
    label: `Fictional home ${index}`,
    version: 1,
    updated_at: "2026-10-11T00:00:00Z",
    home: {
      ...home,
      property_id: `HOME-${owner}-${index}`,
      budget_gbp: index * 5000,
      excluded_retrofits: [],
    },
    preferences: {
      budget_gbp: index * 5000,
      deferred_retrofits: [],
      priority: "energy",
      disruption: "flexible",
    },
    selected_retrofits: index === 1 ? ["loft_insulation"] : [],
    review_status: "new",
    baseline_status: "current",
    events: [],
  };
}
export function multiWorkspace(counts = [1, 1, 1, 1]): CanonicalWorkspace {
  return {
    id: "workspace-v2-fictional",
    schema_version: 2,
    mode: "fictional_demo",
    note: "Fictional UI test fixtures, not real household evidence.",
    expires_at: "2026-11-10T00:00:00Z",
    customers: counts.map((count, index) => {
      const id = `customer-${index + 1}`;
      return {
        id,
        label: `Example customer ${index + 1}`,
        version: 1,
        updated_at: "2026-10-11T00:00:00Z",
        customer_preferences: {
          deferred_retrofits: [],
          priority: "energy",
          disruption: "flexible",
        },
        portfolio_budget_gbp: null,
        legacy_completed_reserve_gbp: 0,
        budget_summary: {
          planned_upper_gbp: 1600,
          completed_reserved_gbp: 0,
          total_reserved_gbp: 1600,
          remaining_gbp: null,
          status: "unlimited",
        },
        properties: Array.from({ length: count }, (_, i) =>
          propertyFixture(id, i + 1),
        ),
      };
    }),
  };
}
