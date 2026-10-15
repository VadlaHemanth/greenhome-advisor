import { Button, Notice, PageHeading } from "./components";
import { moneyRange, number } from "./format";
import type {
  Assessment,
  Home,
  RetrofitId,
  WorkspaceCustomer,
  WorkspaceProperty,
  LegacyWorkspaceCustomer,
} from "./types";
import { PortfolioSummary } from "./CustomerSettings";
import {
  canonicalCustomer,
  displayDate,
  retrofitNames,
  REVIEW_LABELS,
} from "./workspaceModel";

export function CustomerPlan({
  home,
  assessment,
  selected,
  customer: customerInput,
  property: propertyInput,
  schemaVersion,
  unsaved,
}: {
  home: Home;
  assessment: Assessment | null;
  selected: RetrofitId[];
  customer: WorkspaceCustomer | LegacyWorkspaceCustomer | null;
  property?: WorkspaceProperty | null;
  schemaVersion?: 1 | 2;
  unsaved: boolean;
}) {
  const customer = customerInput ? canonicalCustomer(customerInput) : null;
  const property =
    propertyInput ??
    customer?.properties.find((p) => p.home.property_id === home.property_id) ??
    (customerInput && !("properties" in customerInput)
      ? customer?.properties[0]
      : null);
  const warnings = assessment
    ? [...new Set([...assessment.warnings, ...assessment.scenario.warnings])]
    : [];
  return (
    <article className="customer-plan">
      <PageHeading
        title="Your next-step home plan"
        action={
          <Button onClick={() => window.print()} disabled={!assessment}>
            Print or save plan as PDF
          </Button>
        }
      >
        A readable summary to discuss with a qualified installer. Use your
        browser’s print options to save a PDF.
      </PageHeading>
      <header className="plan-identity">
        <h2>GreenHome · Team 225</h2>
        <p>
          {customer
            ? `${customer.label} / ${property?.label ?? "Property"}`
            : home.property_id || "Temporary home"}{" "}
          ·{" "}
          {home.data_kind === "synthetic_demo"
            ? "Fictional example"
            : "Temporary own-home screening"}
        </p>
        <p>
          Prepared {displayDate(new Date().toISOString())}.{" "}
          {customer
            ? `Customer version ${customer.version}; property version ${property?.version ?? "unknown"}${unsaved ? " with unsaved draft changes" : ""}. Review: ${REVIEW_LABELS[property?.review_status ?? "new"]}.`
            : "Not stored in a workspace."}
        </p>
        {customer && property ? (
          <p>
            Customer ID: {customer.id}. Property ID: {property.id}. Home
            reference: {property.home.property_id}.
          </p>
        ) : null}
      </header>
      <Notice kind="warning">
        England and Wales screening only. Costs are indicative, not quotes.
        Purchased-energy reduction is not a promised bill saving. Green Home
        Score is not an EPC. No market valuation or guaranteed resale gain is
        provided.
      </Notice>
      <section className="card plan-section">
        <h2>1. Your starting point</h2>
        <dl className="summary-list">
          <div>
            <dt>Home</dt>
            <dd>
              {home.property_type || "Unknown"} · {number(home.floor_area_m2)}{" "}
              m²
            </dd>
          </div>
          <div>
            <dt>Recorded EPC (not updated by this plan)</dt>
            <dd>{home.epc_rating || "Unknown"}</dd>
          </div>
          <div>
            <dt>Annual grid electricity</dt>
            <dd>{number(home.electricity_kwh)} kWh/year</dd>
          </div>
          <div>
            <dt>Annual gas</dt>
            <dd>{number(home.gas_kwh)} kWh/year</dd>
          </div>
          <div>
            <dt>Property active-plan budget</dt>
            <dd>
              {home.budget_gbp === null
                ? "Not specified"
                : `£${number(home.budget_gbp)}`}
            </dd>
          </div>
          <div>
            <dt>Effective deferred improvements · property + customer</dt>
            <dd>
              {home.excluded_retrofits?.length
                ? retrofitNames(home.excluded_retrofits)
                : "None"}
            </dd>
          </div>
        </dl>
        {property?.baseline_status === "needs_update" ? (
          <Notice kind="warning">
            Post-completion baseline needs updating. Old bills must not be
            reused as evidence of the improved home.
          </Notice>
        ) : null}
      </section>
      {customer &&
      customerInput &&
      "properties" in customerInput &&
      schemaVersion !== 1 ? (
        <section className="card plan-section">
          <h2>Customer portfolio · saved allocation</h2>
          <PortfolioSummary customer={customer} />
          <p>
            The property active-plan budget limits currently selected work only,
            not cumulative historical spending. The customer shared cap includes
            planned work and completed reservations; completion never makes that
            money available again. This plan is not a portfolio ranking or an
            aggregate optimum.
          </p>
        </section>
      ) : null}
      <section className="card plan-section">
        <h2>2. The selected plan</h2>
        <p>
          <strong>{retrofitNames(selected)}</strong>
        </p>
        {!assessment ? (
          <Notice>
            No current validated result is available. Wait for the calculation
            or correct the home and package before printing. Previous figures
            are not shown.
          </Notice>
        ) : (
          <>
            <dl className="summary-list">
              <div>
                <dt>Joint indicative installation cost</dt>
                <dd>{moneyRange(assessment.scenario.cost_gbp)}</dd>
              </div>
              <div>
                <dt>Electricity saving</dt>
                <dd>
                  {number(assessment.scenario.electricity_saving_kwh, 0, true)}{" "}
                  kWh/year
                </dd>
              </div>
              <div>
                <dt>Gas saving</dt>
                <dd>
                  {number(assessment.scenario.gas_saving_kwh, 0, true)} kWh/year
                </dd>
              </div>
              <div>
                <dt>Total purchased-energy saving</dt>
                <dd>
                  {number(assessment.scenario.net_saving_kwh, 0, true)} kWh/year
                </dd>
              </div>
              <div>
                <dt>Purchased-energy reduction</dt>
                <dd>
                  {assessment.scenario.improvement_percent === null
                    ? "Unavailable"
                    : `${number(assessment.scenario.improvement_percent, 1)}%`}
                </dd>
              </div>
              <div>
                <dt>Carbon reduction</dt>
                <dd>
                  {number(assessment.scenario.carbon_reduction_kgco2e, 0, true)}{" "}
                  kgCO₂e/year
                </dd>
              </div>
            </dl>
            <p>
              A negative saving means consumption increases. Fuel prices and
              tariffs are not modelled; kWh is not pounds. Unknown values remain
              unavailable, never zero.
            </p>
            {!selected.length ? (
              <p>
                No improvements are selected. An unchanged home is not evidence
                of no opportunity.
              </p>
            ) : null}
          </>
        )}
      </section>
      <section className="card plan-section">
        <h2>3. Before spending or starting work</h2>
        <ul>
          {home.electricity_kwh === null || home.gas_kwh === null ? (
            <li>
              Find annual grid electricity and gas use in kWh. Enter zero only
              when confirmed, not as a substitute for missing readings.
            </li>
          ) : null}
          {home.floor_area_m2 === null ? (
            <li>Confirm floor area so energy intensity can be assessed.</li>
          ) : null}
          {home.epc_rating === null ? (
            <li>
              Check the recorded EPC rating. Do not estimate a new rating from
              this plan.
            </li>
          ) : null}
          <li>
            Ask a qualified installer to check condition, suitability and
            required permissions. Unknown consent is not approval.
          </li>
          <li>
            Obtain a property-specific quote, including related work, and
            compare it with your available budget.
          </li>
          <li>
            Confirm heating and solar assumptions with a professional before
            relying on these estimates.
          </li>
          <li>
            After completed work, record new annual energy evidence before
            comparing the improved home.
          </li>
        </ul>
      </section>
      {assessment ? (
        <section className="card plan-section plan-evidence">
          <h2>Assumptions & important limitations</h2>
          <ul>
            {[...warnings, ...assessment.scenario.assumptions].map(
              (text, i) => (
                <li key={i}>{text}</li>
              ),
            )}
          </ul>
          <p>{assessment.value_impact.note}</p>
          <h3>Calculation sources</h3>
          {assessment.sources.length ? (
            <ul>
              {assessment.sources.map((source, i) => (
                <li key={i}>
                  {source.label}
                  {/^https?:\/\//i.test(source.url) ? (
                    <>
                      {" "}
                      —{" "}
                      <a href={source.url} target="_blank" rel="noreferrer">
                        {source.url}
                      </a>
                    </>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p>
              No source links returned for this calculation. Ask for the
              calculation evidence before relying on it.
            </p>
          )}
        </section>
      ) : null}
    </article>
  );
}
