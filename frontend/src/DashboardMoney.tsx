import { useId } from "react";
import { MoneyRateForm } from "./MoneyRateForm";
import type { MoneyController } from "./useMoneyPlan";
import "./money.css";

const currency = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const signedCurrency = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  signDisplay: "exceptZero",
});
const pounds = (value: number | null, signed = false) =>
  value === null
    ? "Unavailable"
    : (signed ? signedCurrency : currency).format(value);

export function DashboardMoney({
  controller,
  onCompare,
}: {
  controller: MoneyController;
  onCompare: () => void;
}) {
  const id = useId();
  const { home, selected, result, confirmed } = controller;
  const money = result.data?.money;
  const saving = money?.total.saving_gbp;
  const negative = saving !== undefined && saving !== null && saving < 0;

  return (
    <section
      className="money-plan dashboard-money"
      aria-labelledby={`${id}-title`}
    >
      <header className="dashboard-money-heading">
        <div>
          <h2 id={`${id}-title`}>What changes on your bill?</h2>
          <p>
            England and Wales · GBP screening estimates, not guaranteed savings.
          </p>
        </div>
        <button
          type="button"
          className="money-compare"
          onClick={onCompare}
          disabled={!home}
        >
          Compare packages
        </button>
      </header>
      {!home ? (
        <p className="money-state" role="status">
          Select a home to compare its costs.
        </p>
      ) : (
        <>
          {!selected.length ? (
            <p className="money-state">
              No improvements selected. Current and proposed costs describe the
              same home; choose improvements to compare a plan.
            </p>
          ) : null}
          <div className="dashboard-money-output" aria-busy={result.loading}>
            {result.loading ? (
              <p role="status" className="money-state">
                Calculating this home and selected plan…
              </p>
            ) : null}
            {result.error ? (
              <p role="alert" className="money-error money-state">
                {result.error}
              </p>
            ) : null}
            {!confirmed ? (
              <p role="status" className="money-state">
                Calculate to compare this home and plan. Edited rates are a
                draft; previous results are hidden until you calculate again.
              </p>
            ) : null}
            {money ? (
              <div className="dashboard-money-summary">
                <span className="money-status">
                  {money.status === "available"
                    ? "Estimate available"
                    : money.status === "partial"
                      ? "Partial estimate"
                      : "Money estimate unavailable"}
                </span>
                <dl className="dashboard-money-primary">
                  <div>
                    <dt>Current annual variable cost</dt>
                    <dd>{pounds(money.total.before_gbp)}</dd>
                  </div>
                  <div>
                    <dt>Proposed annual variable cost</dt>
                    <dd>{pounds(money.total.after_gbp)}</dd>
                  </div>
                  <div className={negative ? "money-negative" : undefined}>
                    <dt>Annual bill saving</dt>
                    <dd>{pounds(money.total.saving_gbp, true)}</dd>
                  </div>
                </dl>
                <dl className="dashboard-money-secondary">
                  <div className={negative ? "money-negative" : undefined}>
                    <dt>Monthly average saving</dt>
                    <dd>{pounds(money.monthly_average_gbp, true)}</dd>
                  </div>
                  <div>
                    <dt>Indicative installation cost</dt>
                    <dd>
                      {pounds(money.cost_gbp[0])}–{pounds(money.cost_gbp[1])}
                    </dd>
                  </div>
                </dl>
                {money.status !== "available" ? (
                  <p className="money-state">
                    Both annual fuel readings and both unit rates are needed for
                    totals. Missing is not zero. Compare packages to inspect
                    known fuel costs and missing inputs.
                  </p>
                ) : negative ? (
                  <p className="money-negative dashboard-money-sign">
                    Negative savings mean higher estimated bills. No positive
                    payback at these rates.
                  </p>
                ) : saving === 0 ? (
                  <p className="dashboard-money-sign">
                    No change in estimated annual variable costs at these rates.
                  </p>
                ) : (
                  <p className="dashboard-money-sign">
                    Positive savings mean lower estimated bills at these rates.
                  </p>
                )}
                <p className="money-hint">
                  Monthly average means annual saving divided by 12, not a
                  predicted monthly bill. Installation costs are separate
                  prototype estimates, not quotes; no grants or subsidies are
                  assumed.
                </p>
                {result.data?.warnings.length ? (
                  <details className="dashboard-money-notes">
                    <summary>Calculation assumptions and limits</summary>
                    <ul>
                      {result.data.warnings.map((warning, index) => (
                        <li key={index}>{warning}</li>
                      ))}
                    </ul>
                  </details>
                ) : null}
              </div>
            ) : null}
          </div>
          <MoneyRateForm controller={controller} />
        </>
      )}
    </section>
  );
}
