import { useState } from "react";
import { Button, Loading, Notice, PageHeading } from "./components";
import type {
  CompletionDraft,
  WorkspaceProperty,
  Home,
  DemoTemplateId,
  Preferences,
  RetrofitId,
  ReviewStatus,
  WorkspaceView,
  WorkspaceCustomer,
} from "./types";
import { AddProperty, CustomerSettings } from "./CustomerSettings";
import type { SettingsDraft } from "./CustomerSettings";
import { number } from "./format";
import { RETROFIT_IDS } from "./types";
import {
  displayDate,
  RETROFIT_LABELS,
  REVIEW_LABELS,
  ukCalendarDate,
} from "./workspaceModel";

type WorkspaceState = {
  data: WorkspaceView | null;
  busy: string | null;
  error: string | null;
  conflict: boolean;
  message: string;
};
type HouseholdDraft = {
  customer: WorkspaceCustomer;
  property: WorkspaceProperty;
  preferences: Preferences;
  reviewStatus: ReviewStatus;
  dirty: boolean;
};
export function WorkspacePage({
  state,
  draft,
  actions,
  settingsDraft,
  templates,
}: {
  state: WorkspaceState;
  settingsDraft: SettingsDraft | null;
  templates: Home[];
  draft: HouseholdDraft | null;
  actions: {
    create: () => void;
    restore: () => void;
    remove: () => void;
    export: () => void;
    save: () => void;
    preferences: (p: Preferences) => void;
    review: (s: ReviewStatus) => void;
    complete: (e: CompletionDraft) => void;
    settings: (next: SettingsDraft) => void;
    saveSettings: () => void;
    addProperty: (template: DemoTemplateId) => void;
    openFirst: () => void;
    editHome: () => void;
  };
}) {
  const [consent, setConsent] = useState(false);
  const [deleteConfirmed, setDeleteConfirmed] = useState(false);
  const [completion, setCompletion] = useState<RetrofitId | "">("");
  const [completedOn, setCompletedOn] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const today = ukCalendarDate();
  const saving = Boolean(state.busy);
  return (
    <>
      <PageHeading
        title={
          state.data
            ? "A place to return to"
            : "Keep a fictional plan for later"
        }
      >
        Save preferences, a selected plan and completed work for example
        households. Own-home screening stays temporary and is never saved here.
      </PageHeading>
      <Notice>
        This is your private demonstration workspace. Customer and adviser are
        two views of the same workspace, not separate users, bank
        authentication, adviser sharing or a bank integration. Do not enter
        personal information.
      </Notice>
      {state.busy ? <Loading label={state.busy} /> : null}
      <p role="status" aria-live="polite" className="save-status">
        {state.message}
      </p>
      {state.error ? (
        <Notice kind="error">
          <p>{state.error}</p>
          <Button onClick={actions.restore} disabled={saving}>
            {state.conflict
              ? "Reload saved workspace"
              : "Retry workspace restore"}
          </Button>
          {state.conflict ? (
            <p>
              Reload asks before discarding any unsaved changes. No automatic
              retry will overwrite another version.
            </p>
          ) : null}
        </Notice>
      ) : null}
      {!state.data ? (
        <section className="card workspace-panel">
          <h2>Save a demo workspace</h2>
          <p>
            Four fictional customers are created with one property each. You can
            add up to eight properties per customer. Your current temporary
            inputs and questions are not copied. A private browser cookie
            restores this workspace on this site. It expires after 30 days;
            clearing cookies can lose access. Export or delete it here whenever
            you choose.
          </p>
          <label className="check-row">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              disabled={saving}
            />
            <span>
              I agree to save fictional household data and use a private
              workspace cookie on this browser.
            </span>
          </label>
          <Button
            variant="primary"
            onClick={actions.create}
            disabled={!consent || saving}
          >
            Create my fictional workspace
          </Button>
          <p className="fine-print">
            No account is created. Nothing is saved until you opt in. Provider
            explanation consent is separate and remains off by default.
          </p>
        </section>
      ) : (
        <>
          <section className="card workspace-panel workspace-summary">
            <div>
              <h2>Saved on this browser</h2>
              <p>
                {state.data.customers.length} fictional customers ·{" "}
                {state.data.customers.reduce(
                  (total, c) => total + c.properties.length,
                  0,
                )}{" "}
                properties. Expires {displayDate(state.data.expires_at)}.
              </p>
              <p>{state.data.note}</p>
            </div>
            <Button onClick={actions.export} disabled={saving}>
              Export saved workspace JSON
            </Button>
          </section>
          {draft && state.data.schema_version === 2 ? (
            <>
              <CustomerSettings
                customer={draft.customer}
                draft={settingsDraft}
                busy={saving}
                conflict={state.conflict}
                onChange={actions.settings}
                onSave={actions.saveSettings}
              />
              <AddProperty
                customer={draft.customer}
                templates={templates}
                busy={saving || state.conflict}
                onAdd={actions.addProperty}
              />
            </>
          ) : state.data.schema_version === 1 ? (
            <Notice>
              Legacy single-property compatibility view. Shared budget totals
              are unavailable; no portfolio costs are inferred. Adding
              properties and customer-wide settings require the v2 API.
            </Notice>
          ) : null}
          {draft ? (
            <section
              className="card workspace-panel"
              aria-labelledby="property-settings-title"
            >
              <div className="section-heading">
                <div>
                  <h2 id="property-settings-title">
                    Property settings · {draft.customer.label} /{" "}
                    {draft.property.label}
                  </h2>
                  <p>
                    Customer version {draft.customer.version} · property version{" "}
                    {draft.property.version} · {draft.property.home.property_id}{" "}
                    · {displayDate(draft.property.updated_at)}
                  </p>
                </div>
                <span className={`tag ${draft.dirty ? "gold" : "sage"}`}>
                  {draft.dirty ? "Unsaved changes" : "Saved"}
                </span>
              </div>
              <fieldset disabled={saving} className="preferences-fields">
                <legend>Property preferences</legend>
                <div className="form-grid">
                  <label className="form-field">
                    <span id="workspace-budget-label">
                      Property active-plan budget (£)
                    </span>
                    <input
                      type="number"
                      inputMode="decimal"
                      min="0"
                      max="1000000000"
                      step="any"
                      aria-labelledby="workspace-budget-label"
                      aria-describedby="workspace-budget-help"
                      value={draft.preferences.budget_gbp ?? ""}
                      onChange={(e) => {
                        const value =
                          e.target.value === "" ? null : Number(e.target.value);
                        if (
                          value === null ||
                          (Number.isFinite(value) && value >= 0 && value <= 1e9)
                        )
                          actions.preferences({
                            ...draft.preferences,
                            budget_gbp: value,
                          });
                      }}
                    />
                    <small id="workspace-budget-help">
                      For this property’s active selected plan only, not
                      cumulative historical spending. Completed work does not
                      consume this individual active-plan limit; it remains
                      reserved under the customer shared cap. Blank means no
                      stated active-plan limit. Suggestions use the upper end of
                      indicative costs.
                    </small>
                  </label>
                  <label className="form-field">
                    <span>What matters for this property?</span>
                    <select
                      value={draft.preferences.priority}
                      onChange={(e) =>
                        actions.preferences({
                          ...draft.preferences,
                          priority: e.target.value as Preferences["priority"],
                        })
                      }
                    >
                      <option value="energy">
                        Using less purchased energy
                      </option>
                      <option value="carbon">Reducing carbon</option>
                      <option value="low_cost">Lower installation cost</option>
                    </select>
                  </label>
                  <label className="form-field">
                    <span>Disruption preference</span>
                    <select
                      value={draft.preferences.disruption}
                      onChange={(e) =>
                        actions.preferences({
                          ...draft.preferences,
                          disruption: e.target
                            .value as Preferences["disruption"],
                        })
                      }
                    >
                      <option value="flexible">Flexible</option>
                      <option value="minimal">Keep disruption low</option>
                    </select>
                  </label>
                  <label className="form-field">
                    <span>Review status</span>
                    <select
                      value={draft.reviewStatus}
                      onChange={(e) =>
                        actions.review(e.target.value as ReviewStatus)
                      }
                    >
                      {Object.entries(REVIEW_LABELS).map(([id, name]) => (
                        <option value={id} key={id}>
                          {name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <p>
                  Priority and disruption are reminders for the conversation,
                  not calculated constraints. Homes are always ranked by
                  purchased-energy reduction. “Ready to discuss” is not
                  installation approval.
                </p>
                <fieldset className="deferred-options">
                  <legend>Leave these improvements out for now</legend>
                  <p>
                    Deferred improvements are removed from your plan and
                    excluded from suggestions and ranking. You can bring them
                    back later.
                  </p>
                  {RETROFIT_IDS.map((id) => (
                    <label className="check-row" key={id}>
                      <input
                        type="checkbox"
                        checked={draft.preferences.deferred_retrofits.includes(
                          id,
                        )}
                        onChange={(e) =>
                          actions.preferences({
                            ...draft.preferences,
                            deferred_retrofits: e.target.checked
                              ? [...draft.preferences.deferred_retrofits, id]
                              : draft.preferences.deferred_retrofits.filter(
                                  (v) => v !== id,
                                ),
                          })
                        }
                      />
                      <span>Defer {RETROFIT_LABELS[id]}</span>
                    </label>
                  ))}
                </fieldset>
              </fieldset>
              <p>
                Inherited customer exclusions:{" "}
                {draft.customer.customer_preferences.deferred_retrofits.length
                  ? draft.customer.customer_preferences.deferred_retrofits
                      .map((id) => RETROFIT_LABELS[id])
                      .join(", ")
                  : "None"}
                . Change these in Customer settings; property checkboxes do not
                override them.
              </p>
              {draft.property.baseline_status === "needs_update" ? (
                <Notice kind="warning">
                  Completed work changed this home. Its old electricity and gas
                  readings are no longer a valid baseline. Enter new annual
                  readings and explicitly confirm they describe the home after
                  the completed work.
                  <Button onClick={actions.editHome} disabled={saving}>
                    Update post-completion readings
                  </Button>
                </Notice>
              ) : null}
              <div className="form-actions">
                <Button
                  variant="primary"
                  onClick={actions.save}
                  disabled={saving || !draft.dirty || state.conflict}
                >
                  Save property changes
                </Button>
                <Button onClick={actions.restore} disabled={saving}>
                  Reload saved workspace
                </Button>
              </div>
              <p className="fine-print">
                Saves only this property’s home details, preferences, selected
                improvements and review status together. Comparison packages and
                questions are not saved.
              </p>
            </section>
          ) : (
            <Notice>
              You are screening a temporary home. It cannot be saved in this
              workspace.
              <Button onClick={actions.openFirst} disabled={saving}>
                Open a saved fictional household
              </Button>
            </Notice>
          )}
          {draft ? (
            <section className="card workspace-panel">
              <h2>
                Completed work & history · {draft.customer.label} /{" "}
                {draft.property.label}
              </h2>
              <p>
                Record only work actually completed in this fictional scenario.
                This changes existing features, removes the measure from the
                saved plan and clears both fuel readings. It does not create a
                new EPC or claim measured savings.
              </p>
              {draft.dirty || settingsDraft ? (
                <Notice>
                  Save or discard property changes and customer settings before
                  recording completion.
                </Notice>
              ) : null}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (
                    completion &&
                    confirmed &&
                    completedOn &&
                    completedOn <= today &&
                    !draft.dirty &&
                    !settingsDraft
                  )
                    actions.complete({
                      kind: "completed",
                      retrofit_id: completion,
                      completed_on: completedOn,
                      confirmed: true,
                    });
                }}
              >
                <fieldset
                  disabled={
                    saving ||
                    draft.dirty ||
                    Boolean(settingsDraft) ||
                    state.conflict ||
                    !draft.property.selected_retrofits.length
                  }
                >
                  <legend>Record a completed improvement</legend>
                  <div className="form-grid">
                    <label className="form-field">
                      <span>Completed improvement</span>
                      <select
                        required
                        value={completion}
                        onChange={(e) => {
                          setCompletion(e.target.value as RetrofitId | "");
                          setConfirmed(false);
                        }}
                      >
                        <option value="">Choose from the saved plan</option>
                        {draft.property.selected_retrofits.map((id) => (
                          <option key={id} value={id}>
                            {RETROFIT_LABELS[id]}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="form-field">
                      <span>Completion date</span>
                      <input
                        type="date"
                        required
                        value={completedOn}
                        max={today}
                        onChange={(e) => setCompletedOn(e.target.value)}
                      />
                    </label>
                  </div>
                  <label className="check-row">
                    <input
                      type="checkbox"
                      required
                      checked={confirmed}
                      onChange={(e) => setConfirmed(e.target.checked)}
                    />
                    <span>
                      I confirm this work is completed and understand that both
                      old fuel readings will be cleared. New post-completion
                      readings are needed.
                    </span>
                  </label>
                  <Button
                    type="submit"
                    variant="primary"
                    disabled={
                      !completion ||
                      !confirmed ||
                      !completedOn ||
                      completedOn > today ||
                      !draft.property.selected_retrofits.includes(completion)
                    }
                  >
                    Confirm completed work
                  </Button>
                </fieldset>
              </form>
              {!draft.property.selected_retrofits.length ? (
                <p>
                  Add and save a suitable improvement before recording its
                  completion.
                </p>
              ) : null}
              <h3>Saved history</h3>
              {draft.property.events.length ? (
                <ol className="completion-history">
                  {draft.property.events.map((e) => (
                    <li key={e.id}>
                      <strong>{RETROFIT_LABELS[e.retrofit_id]}</strong>{" "}
                      completed {displayDate(e.completed_on)}.
                      <span> Recorded {displayDate(e.created_at)}.</span>
                      <span>
                        {" "}
                        Planning cost reservation:{" "}
                        {e.planning_cost_upper_gbp == null
                          ? "unknown legacy cost — not assumed zero"
                          : `£${number(e.planning_cost_upper_gbp)}`}{" "}
                        (not actual spending).
                      </span>
                    </li>
                  ))}
                </ol>
              ) : (
                <p>No completed work recorded.</p>
              )}
            </section>
          ) : null}
          <section className="card workspace-panel deletion-panel">
            <h2>Delete this workspace</h2>
            <p>
              Deletes all saved fictional customers, their properties,
              preferences and histories, and clears the workspace cookie. Export
              first if you want a copy. This cannot be undone.
            </p>
            <label className="check-row">
              <input
                type="checkbox"
                checked={deleteConfirmed}
                onChange={(e) => setDeleteConfirmed(e.target.checked)}
                disabled={saving}
              />
              <span>
                I understand that all saved workspace records will be deleted.
              </span>
            </label>
            <Button
              onClick={actions.remove}
              disabled={saving || !deleteConfirmed}
            >
              Delete all saved workspace data
            </Button>
          </section>
        </>
      )}
    </>
  );
}
