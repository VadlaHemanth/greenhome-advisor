import { useId } from "react";
import { number } from "./format";
import { MoneyRateForm } from "./MoneyRateForm";
import type { MoneyPlanResponse } from "./moneyTypes";
import type { Home, RetrofitId } from "./types";
import { useMoneyPlan } from "./useMoneyPlan";
import type { MoneyController } from "./useMoneyPlan";
import "./money.css";

const names: Record<RetrofitId, string> = {
  loft_insulation: "Loft insulation",
  double_glazing: "Double glazing",
  smart_controls: "Smart heating controls",
  heat_pump: "Air-source heat pump",
  solar_pv: "Solar panels",
};
const packageName = (ids: RetrofitId[]) =>
  ids.length
    ? ids.map((id) => names[id]).join(" + ")
    : "No improvements selected";
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
const costRange = (range: [number, number]) =>
  `${pounds(range[0])}–${pounds(range[1])}`;
const measure = (value: number | null, unit: string, decimals = 1) =>
  value === null ? "Unavailable" : `${number(value, decimals)}${unit}`;
const objectives = [
  {
    key: "energy",
    title: "Largest energy reduction",
    note: "Greatest known purchased-energy percentage reduction.",
  },
  {
    key: "bills",
    title: "Strongest bill saving",
    note: "Largest positive annual saving at your supplied rates.",
  },
  {
    key: "lowest_cost",
    title: "Lowest upfront cost",
    note: "Lowest upper installation estimate; excludes doing nothing.",
  },
] as const;

type MoneyPlanProps = {
  home: Home;
  selected: RetrofitId[];
  onChange: (ids: RetrofitId[]) => void;
  controller?: MoneyController;
};

export function MoneyPlan(props: MoneyPlanProps) {
  // Keep the fallback hook in its own component: supplied controllers never
  // create a second request owner, and switching modes does not change hooks.
  return props.controller ? (
    <MoneyPlanView controller={props.controller} onChange={props.onChange} />
  ) : (
    <StandaloneMoneyPlan {...props} />
  );
}

function StandaloneMoneyPlan({ home, selected, onChange }: MoneyPlanProps) {
  const controller = useMoneyPlan(home, selected, "standalone");
  return <MoneyPlanView controller={controller} onChange={onChange} />;
}

function MoneyPlanView({
  controller,
  onChange,
}: {
  controller: MoneyController;
  onChange: (ids: RetrofitId[]) => void;
}) {
  const id = useId();
  const { result, confirmed, selected } = controller;
  return (
    <section className="money-plan" aria-labelledby={`${id}-title`}>
      <header className="money-heading">
        <h1 id={`${id}-title`}>What changes on your bill?</h1>
        <p>
          Compare your selected improvements in pounds, energy and carbon.
          Screening estimates for England and Wales—not installer quotes or
          savings guarantees.
        </p>
      </header>
      <MoneyRateForm controller={controller} />
      <div className="money-output" aria-busy={result.loading}>
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
            Calculate to compare this home and plan. Edited rates are a draft;
            previous results are hidden until you calculate again.
          </p>
        ) : null}
        {result.data ? (
          <MoneyResults
            data={result.data}
            selected={selected}
            onChange={onChange}
            id={id}
          />
        ) : null}
      </div>
    </section>
  );
}

function MoneyResults({
  data,
  selected,
  onChange,
  id,
}: {
  data: MoneyPlanResponse;
  selected: RetrofitId[];
  onChange: (ids: RetrofitId[]) => void;
  id: string;
}) {
  const { money } = data;
  return (
    <>
      <section className="money-comparison" aria-labelledby={`${id}-selected`}>
        <div className="money-section-heading">
          <div>
            <h2 id={`${id}-selected`}>Your selected plan</h2>
            <p>{packageName(selected)}</p>
          </div>
          <span className="money-status">
            {money.status === "available"
              ? "Estimate available"
              : money.status === "partial"
                ? "Partial estimate"
                : "Money estimate unavailable"}
          </span>
        </div>
        {money.status !== "available" ? (
          <p className="money-state">
            Both annual fuel readings and both unit rates are needed for totals
            and bill-saving comparisons. Known fuel costs stay visible; missing
            is not zero.
          </p>
        ) : null}
        <div
          className="money-table-region"
          role="region"
          aria-label="Selected plan annual costs"
          tabIndex={0}
        >
          <table className="money-table" aria-describedby={`${id}-sign-hint`}>
            <caption>Annual energy costs for your selected plan (GBP)</caption>
            <thead>
              <tr>
                <th scope="col">Fuel</th>
                <th scope="col">Before</th>
                <th scope="col">After</th>
                <th scope="col">Annual saving</th>
              </tr>
            </thead>
            <tbody>
              {(
                [
                  ["electricity", "Electricity"],
                  ["gas", "Gas"],
                  ["total", "Total"],
                ] as const
              ).map(([key, label]) => (
                <tr
                  key={key}
                  className={key === "total" ? "money-total" : undefined}
                >
                  <th scope="row">{label}</th>
                  <td>{pounds(money[key].before_gbp)}</td>
                  <td>{pounds(money[key].after_gbp)}</td>
                  <td
                    className={
                      money[key].saving_gbp !== null &&
                      money[key].saving_gbp < 0
                        ? "money-negative"
                        : undefined
                    }
                  >
                    {pounds(money[key].saving_gbp, true)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p id={`${id}-sign-hint`} className="money-hint">
          Positive savings mean lower estimated bills. Negative savings mean
          higher estimated bills.
        </p>
        <dl className="money-totals">
          <div>
            <dt>Annual bill saving</dt>
            <dd>{pounds(money.total.saving_gbp, true)}</dd>
          </div>
          <div>
            <dt>Monthly average saving</dt>
            <dd>{pounds(money.monthly_average_gbp, true)}</dd>
          </div>
          <div>
            <dt>Indicative installation cost</dt>
            <dd className="money-cost-range">{costRange(money.cost_gbp)}</dd>
          </div>
        </dl>
        <p className="money-hint">
          Monthly average means annual saving divided by 12, not a predicted
          monthly bill. Installation costs are separate prototype estimates; no
          grants or subsidies are assumed.
        </p>
        <div className="money-payback">
          <h3>Simple payback</h3>
          <p>
            {money.payback_years ? (
              <strong>
                {number(money.payback_years.low, 2)}–
                {number(money.payback_years.high, 2)} years
              </strong>
            ) : (
              "Payback is unavailable without positive annual bill savings."
            )}
          </p>
          <p className="money-hint">
            Simple payback excludes financing, maintenance, replacement,
            discounting, tariff changes and export revenue. A long arithmetic
            range is not a lifespan or investment-return forecast.
          </p>
        </div>
        <p className="money-standing-note">{money.standing_charge_note}</p>
      </section>

      <section className="money-packages" aria-labelledby={`${id}-packages`}>
        <h2 id={`${id}-packages`}>Different priorities, different packages</h2>
        <p>
          These are the service’s named choices among compared feasible
          packages, using your home, permissions, exclusions and any upper-cost
          budget. No combined “best” score. Using a package changes your
          selection, not a saved plan.
        </p>
        {!data.packages.length ? (
          <p className="money-state">
            No feasible nonempty packages are available in this comparison.
          </p>
        ) : null}
        <div className="money-package-grid">
          {objectives.map((objective) => {
            const item = data.packages.find(
              (item) => item.id === data.picks[objective.key],
            );
            return (
              <article
                className="money-package"
                key={objective.key}
                aria-labelledby={`${id}-${objective.key}`}
              >
                <h3 id={`${id}-${objective.key}`}>{objective.title}</h3>
                <p className="money-objective">{objective.note}</p>
                {item ? (
                  <>
                    <p className="money-package-name">
                      {packageName(item.retrofits)}
                    </p>
                    <dl className="money-package-facts">
                      <div>
                        <dt>Installation estimate</dt>
                        <dd>{costRange(item.cost_gbp)}</dd>
                      </div>
                      <div>
                        <dt>Bill saving</dt>
                        <dd
                          className={
                            item.money_saving_gbp !== null &&
                            item.money_saving_gbp < 0
                              ? "money-negative"
                              : undefined
                          }
                        >
                          {item.money_saving_gbp === null
                            ? "Unavailable"
                            : `${pounds(item.money_saving_gbp, true)} / year`}
                        </dd>
                      </div>
                      <div>
                        <dt>Purchased-energy reduction</dt>
                        <dd>{measure(item.improvement_percent, "%")}</dd>
                      </div>
                      <div>
                        <dt>Purchased energy saved</dt>
                        <dd>{measure(item.net_saving_kwh, " kWh / year")}</dd>
                      </div>
                      <div>
                        <dt>Carbon reduction</dt>
                        <dd>
                          {measure(
                            item.carbon_reduction_kgco2e,
                            " kgCO₂e / year",
                          )}
                        </dd>
                      </div>
                    </dl>
                    <p className="money-reason">{item.recommendation_reason}</p>
                    <button
                      type="button"
                      onClick={() => onChange([...item.retrofits])}
                    >
                      Use this package
                    </button>
                  </>
                ) : (
                  <p className="money-no-pick">
                    {objective.key === "bills"
                      ? "Unavailable: no known positive bill-saving pick at these rates. Check missing inputs or compare energy and upfront cost."
                      : "Unavailable: no qualifying package for this objective with the supplied home facts."}
                  </p>
                )}
              </article>
            );
          })}
        </div>
        {data.packages.length ? (
          <details className="money-alternatives">
            <summary>All compared packages</summary>
            <p>
              Signed savings and the service’s reasons are retained, including
              alternatives with higher bills.
            </p>
            <div
              className="money-table-region"
              role="region"
              aria-label="All package estimates"
              tabIndex={0}
            >
              <table className="money-table money-alternatives-table">
                <caption>
                  All server-returned packages; screening estimates, not quotes
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Package</th>
                    <th scope="col">Installation estimate</th>
                    <th scope="col">Annual bill saving</th>
                    <th scope="col">Energy reduction</th>
                    <th scope="col">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {data.packages.map((item) => (
                    <tr key={item.id}>
                      <th scope="row">{packageName(item.retrofits)}</th>
                      <td>{costRange(item.cost_gbp)}</td>
                      <td>{pounds(item.money_saving_gbp, true)}</td>
                      <td>{measure(item.improvement_percent, "%")}</td>
                      <td>{item.recommendation_reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        ) : null}
      </section>
      {data.warnings.length ? (
        <aside className="money-notes" aria-labelledby={`${id}-notes`}>
          <h2 id={`${id}-notes`}>Assumptions and limits</h2>
          <ul>
            {data.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </aside>
      ) : null}
    </>
  );
}
