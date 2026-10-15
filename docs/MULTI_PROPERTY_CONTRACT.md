# Customer → properties release contract

11 October 2026, Team 225. Real workspace data is fictional only. Current
single-property source `ad06fbc` is the migration input, not overwritten evidence.

## Parallel ownership

- Backend worker: workspace_store.py, workspace_api.py, new migration helper if
  needed, workspace tests + new multi-property tests, WORKSPACE_MEMORY.md.
- Frontend worker: frontend/ only and new docs/MULTI_PROPERTY_UI.md.
- Evaluation worker: new scripts/evaluate_ownership.py,
  tests/test_ownership_evaluation.py, data/ownership_cases*.json,
  reports/ownership_*.json and docs/OWNERSHIP_EVALUATION.md; no old reports changed.
- Lead: integration, report/architecture updates, browser and release checks.

## V2 canonical JSON, additive compatibility

Workspace adds `schema_version: 2`; existing id/mode/expiry/note retained.
Four seeded customer records remain for compatibility; each initially has one
property. UI explicitly supports adding up to eight properties per customer from
four fictional templates. Not eight properties masquerading as eight customers.

```
customer = {
 id, label, version, updated_at,
 customer_preferences: {deferred_retrofits:[], priority:"energy", disruption:"flexible"},
 portfolio_budget_gbp: null,
 legacy_completed_reserve_gbp: 0,
 budget_summary: {
   planned_upper_gbp: 0, completed_reserved_gbp: 0|null,
   total_reserved_gbp:0|null, remaining_gbp:null,
   status:"unlimited"|"within_budget"|"needs_cost_evidence"
 },
 properties:[{
   id, customer_id, label, version, updated_at,
   home: HomeInput, preferences: existing property Preferences schema,
   selected_retrofits:[], review_status:"new",
   baseline_status:"current"|"needs_update", events:[]
 }]
}
```

`id` on each property is a server-generated opaque resource ID, not client
supplied; `home.property_id` is unique within the workspace, immutable and safe
for ranking/LLM-free engine inputs. Customer id and property id must BOTH be used
to fetch/write. A wrong customer id with a valid property id returns 404 even
inside the same private workspace. Properties cannot be transferred by input.

Customer-wide exclusions are unioned with property exclusions when assessing.
Raw property preferences remain separate; defaults at customer scope are neutral.
Customer priority/disruption remain discussion preferences, not ranking weights.
The required ranking remains each home's potential, not portfolio optimisation.
Property fields/budget/history never live at the customer root canonically.

For **exactly one property only**, old root `home`, `preferences`,
`selected_retrofits`, `review_status`, `baseline_status`, `events` may remain as
deprecated read-only projections so existing tests/callers survive. Legacy
POST customer/events endpoints only operate if exactly one property, and use
customer `version`; with multiple properties they return 409
`property_required`. No silent "first home" mutation. New UI uses canonical fields.

## Routes (under /api/workspace)

- Existing bootstrap/create/export/delete and secure cookie controls retained.
- `GET /customers/{cid}/properties/{pid}` returns whole workspace after scoped lookup.
- `POST /customers/{cid}/properties` body:
  `{customer_version:1, template_id:"DEMO-01"}` creates new fictional property with
  fresh resource/home identifiers, independent empty selection/history. Copy
  template facts only, not another property's bills/history or preferences.
- `POST /customers/{cid}/settings` body:
  `{version:1, customer_preferences:{...}, portfolio_budget_gbp:null,
    legacy_completed_reserve_gbp:0, confirm_legacy_reserve:false}`
  defaults confirmation false. New cap cannot be below committed+planned upper
  allocation. New customer exclusions conflicting with saved plans ->409
  explicit conflict, no silently deleting multiple property plans.
- `POST /customers/{cid}/properties/{pid}`:
  `{customer_version:1, version:1, home:HomeInput, preferences:Preferences,
    selected_retrofits:[], review_status:"new",
    baseline_confirmed_after_completion:false}`
  Full required field validation. Mutation checks property AND customer versions
  inside one customer-locked transaction, increments BOTH versions. The sibling's
  version/state stays unchanged. Effective budget/exclusions checked server-side.
- `POST /customers/{cid}/properties/{pid}/events`:
  `{customer_version:1,version:1,kind:"completed",retrofit_id:"loft_insulation",
    completed_on:"2026-10-11",confirmed:true}`
  Existing completion safeguards retained, only target's fields/fuels change.
  New event adds `planning_cost_upper_gbp` captured from that saved measure's
  catalogue upper estimate at completion, explicitly NOT actual spending.
  Removing it from selection + adding equal reservation leaves portfolio
  allocation unchanged. No saved aggregate energy saving is counted.

No property deletion/transfer is necessary for this release: workspace deletion
removes every related record. If added, do not let deletion erase incurred
planning allocations or circumvent a shared cap.

## Shared cap and migration

Portfolio plan total = sum of active selected upper costs on ALL properties +
sum of new completed event planning reservations + legacy_completed_reserve_gbp.
This is planning accounting, not a bank account or cumulative realised benefit.
All allocation checks under the SAME database transaction and customer version
lock; concurrent sibling saves cannot both spend the last allocation.
Reject cap reductions below commitments; preserve draft on 409.
Unlimited/null cap still reports totals. Incomplete old cost records remain null.

Transactionally migrate v1 under lock before traffic, after schema validation.
Preserve customer/workspace IDs, token hashes, expiry, versions, labels, original
home facts, selections, permissions, property preferences and event IDs/dates.
Create one property per original customer deterministically/idempotently.
Do NOT promote old property budget/exclusions into customer-wide settings.
If any old completion has no cost reservation, set customer
legacy_completed_reserve_gbp=null; no finite shared cap until operator explicitly
confirms an aggregate planning reserve (zero allowed if intentionally confirmed).
Do not invent historical spending. Existing legacy properties remain usable.
Validate all rows; corrupt/unknown schema aborts and rolls back. No lossy reset.
Take an owner-only SQLite backup before live upgrade; old app workers must stop
before replacing schema. Preserve exact schema1 fixtures/tests of rollback,
concurrent warmers and repeated startup. Test backed-up v1 upgrade then v2 restart.

## UI

Separate labelled customer and property selectors; property selector contains
only the chosen customer's properties. Preserve dirty confirmation and reset
old responses/selection when either identity changes. Key all async contexts by
workspace+customer+property+versions, not a display label or template alias.
Property editor/save/completion controls clearly name both target customer/home.
Customer settings show shared cap/allocation and universal exclusions separately
from the current property's budget/deferrals. Add-property action uses template
picker with explicit fictional label; no personal-address lookup.
Homes adviser list flattens properties with owner labels; no duplicated IDs.
Print/export includes parent customer and property identity/scope. Customer-wide
cap is not silently treated as an individual home budget or aggregate optimum.

## Evidence constraints

New ownership dataset assigns customer IDs FIRST, then deterministic customer
train/validation/test split, then creates 1,2,4 properties with chronological
histories. All siblings inherit split. Only already-recorded events available at
query time, even if occurrence date is backdated. No links inferred from NEED.
No old property-only score/model metrics relabelled customer validation.
Test actual new HTTP routes/store: 1/2/4 properties, wrong-owner scope, exports,
deletion, duplicate completion, sibling versions, cap reservation/concurrency,
new preferences, past-date future-knowledge rejection, postcompletion baseline.
Report split sizes, event/query counts, denominator and ablations honestly;
no real-user/physical-savings claim.
