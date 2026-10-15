import type {
  Home,
  Preferences,
  RetrofitId,
  WorkspaceCustomer,
  WorkspaceProperty,
  Workspace,
  WorkspaceView,
  LegacyWorkspaceCustomer,
  CustomerPreferences,
} from "./types";

export function ukCalendarDate(now = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/London",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const part = (name: string) =>
    parts.find((item) => item.type === name)?.value;
  return `${part("year")}-${part("month")}-${part("day")}`;
}

export const RETROFIT_LABELS: Record<RetrofitId, string> = {
  loft_insulation: "Loft insulation",
  double_glazing: "Double glazing",
  smart_controls: "Smart heating controls",
  heat_pump: "Air-source heat pump",
  solar_pv: "Solar panels",
};
export const REVIEW_LABELS = {
  new: "New",
  reviewing: "In review",
  ready: "Ready to discuss",
  deferred: "On hold",
};
export function withPreferences(
  home: Home,
  preferences: Preferences,
  customerPreferences?: CustomerPreferences,
): Home {
  return {
    ...home,
    budget_gbp: preferences.budget_gbp,
    excluded_retrofits: [
      ...new Set([
        ...preferences.deferred_retrofits,
        ...(customerPreferences?.deferred_retrofits ?? []),
      ]),
    ],
  };
}
export function propertyHome(
  customer: WorkspaceCustomer,
  property: WorkspaceProperty,
): Home {
  // Never allocate the portfolio cap to one property or use it as a ranking budget.
  return withPreferences(
    property.home,
    property.preferences,
    customer.customer_preferences,
  );
}
export function canonicalCustomer(
  customer: WorkspaceCustomer | LegacyWorkspaceCustomer,
): WorkspaceCustomer {
  if ("properties" in customer) return customer;
  // Only schema-1 input reaches this adapter. Never infer a property from a v2 root projection.
  const { id, label, version, updated_at, ...fields } = customer;
  return {
    id,
    label,
    version,
    updated_at,
    customer_preferences: {
      deferred_retrofits: [],
      priority: "energy",
      disruption: "flexible",
    },
    portfolio_budget_gbp: null,
    legacy_completed_reserve_gbp: fields.events.length ? null : 0,
    // Legacy JSON has no aggregate cost evidence. Do not invent it.
    budget_summary: {
      planned_upper_gbp: 0,
      completed_reserved_gbp: null,
      total_reserved_gbp: null,
      remaining_gbp: null,
      status: "needs_cost_evidence",
    },
    properties: [
      {
        ...fields,
        id: `legacy:${id}`,
        customer_id: id,
        label: fields.home.property_id || "Legacy property",
        version,
        updated_at,
      },
    ],
  };
}
export function workspaceView(workspace: Workspace): WorkspaceView {
  return {
    ...workspace,
    schema_version: workspace.schema_version ?? 1,
    customers: workspace.customers.map(canonicalCustomer),
  };
}
export function flattenProperties(
  customers: (WorkspaceCustomer | LegacyWorkspaceCustomer)[],
) {
  return customers.flatMap((raw) => {
    const customer = canonicalCustomer(raw);
    return customer.properties.map((property) => ({ customer, property }));
  });
}
export function propertyContext(
  workspace: WorkspaceView | null,
  customer: WorkspaceCustomer | null,
  property: WorkspaceProperty | null,
) {
  return JSON.stringify([
    workspace?.id,
    customer?.id,
    property?.id,
    customer?.version,
    property?.version,
  ]);
}
export function latestCompletedOn(
  property: WorkspaceProperty | null,
): string | undefined {
  return property?.events.reduce<string | undefined>(
    (latest, event) =>
      !latest || event.completed_on > latest ? event.completed_on : latest,
    undefined,
  );
}
export function periodIncludesPreCompletion(
  startMonth: string | null,
  completedOn?: string,
): boolean {
  return Boolean(
    startMonth && completedOn && startMonth <= completedOn.slice(0, 7),
  );
}
export function retrofitNames(ids: RetrofitId[]) {
  return ids.length
    ? ids.map((id) => RETROFIT_LABELS[id]).join(", ")
    : "No improvements selected";
}
export function displayDate(value: string) {
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeZone: "UTC",
  }).format(new Date(value));
}
