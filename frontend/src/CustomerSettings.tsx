import { useState } from "react";
import { Button, Notice } from "./components";
import { number } from "./format";
import { RETROFIT_IDS, DEMO_TEMPLATE_IDS } from "./types";
import type {
  CustomerSettingsUpdate,
  DemoTemplateId,
  Home,
  WorkspaceCustomer,
} from "./types";
import { RETROFIT_LABELS } from "./workspaceModel";

export type SettingsDraft = Omit<CustomerSettingsUpdate, "version">;
const amount = (value: number | null) =>
  value === null ? "Unknown — cost evidence needed" : `£${number(value)}`;

/** Saved server totals, not a client-side allocation or an optimiser. */
export function PortfolioSummary({
  customer,
}: {
  customer: WorkspaceCustomer;
}) {
  const summary = customer.budget_summary;
  return (
    <>
      <dl className="summary-list portfolio-summary">
        <div>
          <dt>Shared portfolio cap</dt>
          <dd>
            {customer.portfolio_budget_gbp === null
              ? "No shared cap"
              : amount(customer.portfolio_budget_gbp)}
          </dd>
        </div>
        <div>
          <dt>Saved planned upper costs · all properties</dt>
          <dd>{amount(summary.planned_upper_gbp)}</dd>
        </div>
        <div>
          <dt>Completed planning reservations</dt>
          <dd>{amount(summary.completed_reserved_gbp)}</dd>
        </div>
        <div>
          <dt>Total reserved</dt>
          <dd>{amount(summary.total_reserved_gbp)}</dd>
        </div>
        <div>
          <dt>Remaining shared allocation</dt>
          <dd>
            {summary.remaining_gbp === null
              ? summary.status === "needs_cost_evidence"
                ? "Unknown — cost evidence needed"
                : "No shared cap"
              : amount(summary.remaining_gbp)}
          </dd>
        </div>
      </dl>
      <p>
        Saved plans reserve upper indicative costs across all properties.
        Completion moves a measure’s planning cost into a completed reservation;
        it does not free the allocation. These are not actual spending or
        cumulative realised savings. Unsaved drafts are not included.
      </p>
      {summary.status === "needs_cost_evidence" ? (
        <Notice kind="warning">
          Historical completion costs are unknown. No finite shared cap can be
          set until an aggregate legacy planning reserve is explicitly
          confirmed. Zero is allowed only if intentionally entered and
          confirmed; it is not inferred spending.
        </Notice>
      ) : null}
    </>
  );
}

export function CustomerSettings({
  customer,
  draft,
  busy,
  conflict,
  onChange,
  onSave,
}: {
  customer: WorkspaceCustomer;
  draft: SettingsDraft | null;
  busy: boolean;
  conflict: boolean;
  onChange: (next: SettingsDraft) => void;
  onSave: () => void;
}) {
  const value: SettingsDraft = draft ?? {
    customer_preferences: customer.customer_preferences,
    portfolio_budget_gbp: customer.portfolio_budget_gbp,
    legacy_completed_reserve_gbp: customer.legacy_completed_reserve_gbp,
    confirm_legacy_reserve: false,
  };
  const needsReserve = customer.legacy_completed_reserve_gbp === null;
  const cannotConfirmCap =
    needsReserve &&
    value.portfolio_budget_gbp !== null &&
    (!value.confirm_legacy_reserve ||
      value.legacy_completed_reserve_gbp === null);
  function numeric(
    key: "portfolio_budget_gbp" | "legacy_completed_reserve_gbp",
    input: string,
  ) {
    const next = input === "" ? null : Number(input);
    if (next === null || (Number.isFinite(next) && next >= 0 && next <= 1e9))
      onChange({ ...value, [key]: next });
  }
  return (
    <section
      className="card workspace-panel customer-settings"
      aria-labelledby="customer-settings-title"
    >
      <h2 id="customer-settings-title">Customer settings · {customer.label}</h2>
      <p>
        Applies to all {customer.properties.length} properties owned by this
        customer. Customer version {customer.version}. Property details,
        budgets, deferrals and histories remain independent.
      </p>
      <PortfolioSummary customer={customer} />
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!busy && !conflict && draft && !cannotConfirmCap) onSave();
        }}
      >
        <fieldset disabled={busy}>
          <legend>Shared settings, not this property’s budget</legend>
          <div className="form-grid">
            <label className="form-field">
              <span id="shared-budget-label">Shared portfolio budget (£)</span>
              <input
                name="portfolio_budget_gbp"
                type="number"
                min="0"
                max="1000000000"
                step="any"
                value={value.portfolio_budget_gbp ?? ""}
                onChange={(e) =>
                  numeric("portfolio_budget_gbp", e.target.value)
                }
                aria-labelledby="shared-budget-label"
                aria-describedby="portfolio-budget-help"
              />
              <small id="portfolio-budget-help">
                Blank means no shared cap. A cap below saved plans and
                completion reservations is rejected, never silently allocated to
                individual homes.
              </small>
            </label>
            <label className="form-field">
              <span>Customer discussion priority</span>
              <select
                value={value.customer_preferences.priority}
                onChange={(e) =>
                  onChange({
                    ...value,
                    customer_preferences: {
                      ...value.customer_preferences,
                      priority: e.target
                        .value as SettingsDraft["customer_preferences"]["priority"],
                    },
                  })
                }
              >
                <option value="energy">Using less purchased energy</option>
                <option value="carbon">Reducing carbon</option>
                <option value="low_cost">Lower installation cost</option>
              </select>
            </label>
            <label className="form-field">
              <span>Customer disruption preference</span>
              <select
                value={value.customer_preferences.disruption}
                onChange={(e) =>
                  onChange({
                    ...value,
                    customer_preferences: {
                      ...value.customer_preferences,
                      disruption: e.target
                        .value as SettingsDraft["customer_preferences"]["disruption"],
                    },
                  })
                }
              >
                <option value="flexible">Flexible</option>
                <option value="minimal">Keep disruption low</option>
              </select>
            </label>
          </div>
          {needsReserve ? (
            <div className="legacy-reserve">
              <label className="form-field">
                <span>Aggregate legacy planning reserve (£)</span>
                <input
                  type="number"
                  min="0"
                  max="1000000000"
                  step="any"
                  value={value.legacy_completed_reserve_gbp ?? ""}
                  onChange={(e) =>
                    numeric("legacy_completed_reserve_gbp", e.target.value)
                  }
                />
              </label>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={value.confirm_legacy_reserve}
                  onChange={(e) =>
                    onChange({
                      ...value,
                      confirm_legacy_reserve: e.target.checked,
                    })
                  }
                />
                <span>
                  I explicitly confirm this aggregate legacy planning reserve,
                  including zero if entered. This is not evidence of actual
                  spending.
                </span>
              </label>
            </div>
          ) : null}
          <fieldset className="deferred-options">
            <legend>Customer-wide exclusions</legend>
            <p>
              Unioned with each property’s deferrals. Conflicts with saved plans
              are rejected; this action never silently removes plans. Priority
              and disruption are discussion preferences, not ranking weights.
            </p>
            {RETROFIT_IDS.map((id) => (
              <label key={id} className="check-row">
                <input
                  type="checkbox"
                  checked={value.customer_preferences.deferred_retrofits.includes(
                    id,
                  )}
                  onChange={(e) =>
                    onChange({
                      ...value,
                      customer_preferences: {
                        ...value.customer_preferences,
                        deferred_retrofits: e.target.checked
                          ? [
                              ...value.customer_preferences.deferred_retrofits,
                              id,
                            ]
                          : value.customer_preferences.deferred_retrofits.filter(
                              (item) => item !== id,
                            ),
                      },
                    })
                  }
                />
                <span>Exclude {RETROFIT_LABELS[id]} for all properties</span>
              </label>
            ))}
          </fieldset>
          <Button
            type="submit"
            variant="primary"
            disabled={!draft || conflict || cannotConfirmCap}
          >
            Save customer settings
          </Button>
          {draft ? (
            <p role="status">
              Unsaved customer settings. Property plans and budgets have not
              been changed.
            </p>
          ) : null}
        </fieldset>
      </form>
    </section>
  );
}

export function AddProperty({
  customer,
  templates,
  busy,
  onAdd,
}: {
  customer: WorkspaceCustomer;
  templates: Home[];
  busy: boolean;
  onAdd: (template: DemoTemplateId) => void;
}) {
  const [template, setTemplate] = useState<DemoTemplateId | "">("");
  const [fictional, setFictional] = useState(false);
  const full = customer.properties.length >= 8;
  return (
    <section
      className="card workspace-panel"
      aria-labelledby="add-property-title"
    >
      <h2 id="add-property-title">Properties for {customer.label}</h2>
      <p>
        {customer.properties.length} of 8 properties. Add a separate fictional
        property, not another customer.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (template && fictional && !full && !busy) onAdd(template);
        }}
      >
        <fieldset disabled={busy || full}>
          <legend>Add a fictional template property</legend>
          <label className="form-field">
            <span id="property-template-label">
              Fictional property template
            </span>
            <select
              aria-labelledby="property-template-label"
              aria-describedby="property-template-help"
              required
              value={template}
              onChange={(e) => {
                setTemplate(e.target.value as DemoTemplateId | "");
                setFictional(false);
              }}
            >
              <option value="">Choose a fictional example</option>
              {DEMO_TEMPLATE_IDS.map((id) => (
                <option key={id} value={id}>
                  {id} ·{" "}
                  {templates.find((home) => home.property_id === id)
                    ?.property_type ?? "Example home"}{" "}
                  · fictional
                </option>
              ))}
            </select>
            <small id="property-template-help">
              Copies template facts only, with fresh home and property IDs. No
              other property’s bills, preferences, saved plan or history are
              copied. No address lookup or real customer data.
            </small>
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              required
              checked={fictional}
              onChange={(e) => setFictional(e.target.checked)}
            />
            <span>
              I understand this new property is a fictional template helper, not
              real home data.
            </span>
          </label>
          <Button type="submit" disabled={!template || !fictional}>
            Add fictional property
          </Button>
        </fieldset>
      </form>
      {full ? (
        <Notice>
          Eight-property limit reached for this customer. Select an existing
          property to work on it.
        </Notice>
      ) : null}
    </section>
  );
}
