import { useState } from "react";
import { api } from "./api";
import { Button, Loading, Notice, PageHeading } from "./components";
import { moneyRange, number } from "./format";
import type {
  Home,
  RankedHome,
  WorkspaceCustomer,
  LegacyWorkspaceCustomer,
} from "./types";
import { useResource } from "./useResource";
import { AdviserSummary } from "./AdviserSummary";
import {
  flattenProperties,
  propertyHome,
  REVIEW_LABELS,
  retrofitNames,
} from "./workspaceModel";

export function Homes({
  homes,
  customers,
  openHome,
  workspaceId,
}: {
  homes: Home[];
  customers: (WorkspaceCustomer | LegacyWorkspaceCustomer)[] | null;
  workspaceId?: string;
  openHome: (propertyId: string) => void;
}) {
  const [retry, setRetry] = useState(0);
  const [filter, setFilter] = useState("");
  const properties = customers ? flattenProperties(customers) : null;
  const owners = new Map(
    properties?.map((entry) => [entry.property.home.property_id, entry]),
  );
  const inputs = properties
    ? properties.map(({ customer, property }) =>
        propertyHome(customer, property),
      )
    : homes;
  const versions = properties?.map(({ customer, property }) => [
    customer.id,
    property.id,
    customer.version,
    property.version,
  ]);
  const ranking = useResource(
    inputs.length
      ? JSON.stringify([workspaceId, versions, inputs, retry])
      : null,
    (signal) => api.rankHomes(inputs, signal),
  );
  const visible = (r: RankedHome) =>
    `${r.property_id} ${owners.get(r.property_id)?.customer.label || ""} ${owners.get(r.property_id)?.property.label || ""}`
      .toLowerCase()
      .includes(filter.toLowerCase());
  const ranked =
    ranking.data?.rows
      .filter(
        (r) =>
          r.status !== "insufficient_evidence" && r.status !== "unsupported",
      )
      .filter(visible) || [];
  const evidence =
    ranking.data?.rows
      .filter(
        (r) =>
          r.status === "insufficient_evidence" || r.status === "unsupported",
      )
      .filter(visible) || [];
  function label(r: RankedHome) {
    const owner = owners.get(r.property_id);
    return owner
      ? `${owner.customer.label} / ${owner.property.label}`
      : r.property_id;
  }
  return (
    <>
      <PageHeading title="Homes, considered together">
        Adviser view of{" "}
        {customers
          ? "your private fictional workspace"
          : "the temporary demonstration homes"}
        . Customer and adviser views belong to the same user—not a bank account,
        staff login or shared service.
      </PageHeading>
      <AdviserSummary
        rows={ranking.data?.rows.filter(visible) || []}
        loading={ranking.loading}
        available={ranking.data !== null || inputs.length === 0}
      />
      <Notice>
        Ordered by the greatest estimated percentage reduction in purchased
        energy within each home’s active-plan budget, using upper indicative
        costs. This is not a bill-saving, resale-value or portfolio-budget
        ranking. Priority preferences do not change this rule. Individual
        active-plan budgets are not cumulative spending limits. The customer
        shared cap separately reserves planned and completed work.
      </Notice>
      <div className="homes-toolbar">
        <label className="form-field">
          <span>Find a fictional home</span>
          <input
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Customer, property or reference"
          />
        </label>
        <Button
          onClick={() => setRetry((n) => n + 1)}
          disabled={ranking.loading}
        >
          Refresh ranking
        </Button>
      </div>
      {customers ? (
        <p>
          Ranking uses saved versions only. Save property changes before
          comparing homes.
        </p>
      ) : null}
      <div className="sr-only" role="status" aria-live="polite">
        {ranking.loading
          ? "Updating home ranking."
          : ranking.data
            ? `${ranked.length} assessed homes and ${evidence.length} evidence-needed homes shown.`
            : ""}
      </div>
      {ranking.loading ? (
        <Loading label="Comparing homes under their own budgets…" />
      ) : null}
      {ranking.error ? (
        <Notice kind="error">
          {ranking.error} Use Refresh ranking to try again. Previous ranks are
          not shown.
        </Notice>
      ) : null}
      {ranking.data ? (
        <>
          <section
            className="card homes-section"
            aria-labelledby="ranked-homes-title"
          >
            <h2 id="ranked-homes-title">
              Assessed opportunity{" "}
              <span className="tag sage">{ranked.length}</span>
            </h2>
            <p>
              Equal results share a rank. Displayed percentages are rounded;
              ranking treats differences below its documented numerical
              precision as ties. No affordable option is not a missing-data
              result.
            </p>
            <ol className="home-ranking">
              {ranked.map((r) => {
                const property = owners.get(r.property_id)?.property;
                return (
                  <li key={r.property_id}>
                    <div
                      className="rank-number"
                      aria-label={
                        r.rank === null ? "Not ranked" : `Rank ${r.rank}`
                      }
                    >
                      {r.rank === null ? "—" : r.rank}
                    </div>
                    <div className="rank-copy">
                      <h3>{label(r)}</h3>
                      <p>
                        {r.property_id}{" "}
                        {property
                          ? ` · ${REVIEW_LABELS[property.review_status]}`
                          : ""}
                      </p>
                      <p>{r.reason}</p>
                      <p>
                        <strong>Suggested package:</strong>{" "}
                        {retrofitNames(r.selected_retrofits)}
                      </p>
                      <details>
                        <summary>Why this home is here</summary>
                        <dl className="summary-list">
                          <div>
                            <dt>Green Home Score (not an EPC)</dt>
                            <dd>
                              {number(r.score)} · {r.classification}
                            </dd>
                          </div>
                          <div>
                            <dt>Current purchased energy</dt>
                            <dd>{number(r.baseline_kwh)} kWh/year</dd>
                          </div>
                          <div>
                            <dt>Electricity saving</dt>
                            <dd>
                              {number(r.electricity_saving_kwh, 0, true)}{" "}
                              kWh/year
                            </dd>
                          </div>
                          <div>
                            <dt>Gas saving</dt>
                            <dd>
                              {number(r.gas_saving_kwh, 0, true)} kWh/year
                            </dd>
                          </div>
                          <div>
                            <dt>Carbon reduction</dt>
                            <dd>
                              {number(r.carbon_reduction_kgco2e)} kgCO₂e/year
                            </dd>
                          </div>
                        </dl>
                        <p>
                          A negative saving means use increases. Estimates
                          depend on the home information and stated assumptions.
                        </p>
                      </details>
                    </div>
                    <div className="rank-outcome">
                      <strong>
                        {r.improvement_percent === null
                          ? "Unavailable"
                          : `${number(r.improvement_percent, 2)}%`}
                      </strong>
                      <span>purchased-energy reduction</span>
                      <span>{moneyRange(r.cost_gbp)} indicative cost</span>
                      <span>
                        Active-plan budget:{" "}
                        {r.budget_gbp === null
                          ? "not specified"
                          : `£${number(r.budget_gbp)}`}
                      </span>
                      <Button onClick={() => openHome(r.property_id)}>
                        Open {label(r)}
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ol>
            {!ranked.length ? <p>No assessed homes match this view.</p> : null}
          </section>
          <section
            className="card homes-section evidence-queue"
            aria-labelledby="evidence-homes-title"
          >
            <h2 id="evidence-homes-title">
              Evidence needed or outside scope{" "}
              <span className="tag gold">{evidence.length}</span>
            </h2>
            <p>
              These homes are not assigned zero potential or placed at the
              bottom of a numerical ranking.
            </p>
            {evidence.map((r) => (
              <article key={r.property_id}>
                <div>
                  <h3>{label(r)}</h3>
                  <span className="tag gold">
                    {r.status === "unsupported"
                      ? "Outside supported scope"
                      : "Needs more information"}
                  </span>
                  <p>{r.reason}</p>
                </div>
                <Button onClick={() => openHome(r.property_id)}>
                  Review {label(r)}
                </Button>
              </article>
            ))}
            {!evidence.length ? (
              <p>No evidence-needed homes match this view.</p>
            ) : null}
          </section>
          <details className="ranking-method">
            <summary>Ranking method and limitations</summary>
            <p>{ranking.data.policy}</p>
          </details>
          {ranking.data.warnings.length ? (
            <Notice kind="warning">
              <ul>
                {ranking.data.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </Notice>
          ) : null}
        </>
      ) : null}
    </>
  );
}
