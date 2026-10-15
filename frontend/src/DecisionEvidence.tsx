import type { CatalogueItem, Decision, RetrofitId } from "./types";
import { moneyRange, number } from "./format";
import { packageNames } from "./components";

function samePackage(
  a: RetrofitId[] | null | undefined,
  b: RetrofitId[] | null | undefined,
) {
  return (
    Array.isArray(a) &&
    Array.isArray(b) &&
    a.length === b.length &&
    a.every((id) => b.includes(id))
  );
}

export function DecisionEvidence({
  decision,
  catalogue,
}: {
  decision: Decision;
  catalogue: CatalogueItem[];
}) {
  const methods = [
    {
      label: "Saved assumptions · nominal",
      ids: decision.nominal_package,
      explanation:
        "Best purchased-energy saving using the saved home assumptions.",
    },
    {
      label: "Catalogue order · greedy",
      ids: decision.greedy_package,
      explanation:
        "The engine’s feasible, budget-aware package in catalogue order.",
    },
    {
      label: "Tested scenarios · robust",
      ids: decision.recommended_package,
      explanation:
        "Compare each package’s largest shortfall, then choose the smallest of those shortfalls.",
    },
  ];
  const allSame =
    samePackage(decision.nominal_package, decision.recommended_package) &&
    samePackage(decision.greedy_package, decision.recommended_package);
  return (
    <>
      <h3>How the approaches compare</h3>
      <dl className="summary-list method-comparison">
        {methods.map((method) => (
          <div key={method.label}>
            <dt>
              {method.label}
              <small>{method.explanation}</small>
            </dt>
            <dd>
              {Array.isArray(method.ids)
                ? packageNames(method.ids, catalogue)
                : "Unavailable"}
            </dd>
          </div>
        ))}
      </dl>
      <p className="fine-print">
        {allSame
          ? "All three approaches return the same package for this home. This check does not establish an advantage over the simpler approaches."
          : "Different packages may tie. A different selection is not, by itself, evidence of better real-world performance."}
      </p>
      <details>
        <summary>Compare tested package estimates</summary>
        <p>
          All energy figures below come from the decision-check response, in
          kWh/year. The minimum and maximum describe only the analyst-selected
          scenarios tested—not a forecast interval.
        </p>
        {decision.packages?.length ? (
          <div
            className="table-region"
            role="region"
            aria-label="Tested package evidence"
            tabIndex={0}
          >
            <table>
              <caption>Package estimates across tested scenarios</caption>
              <thead>
                <tr>
                  <th scope="col">Package</th>
                  <th scope="col">Indicative cost</th>
                  <th scope="col">Saved-assumption saving</th>
                  <th scope="col">Lowest tested saving</th>
                  <th scope="col">Highest tested saving</th>
                  <th scope="col">Largest tested gap</th>
                </tr>
              </thead>
              <tbody>
                {decision.packages.map((item, index) => (
                  <tr key={`${item.retrofits.join("-")}-${index}`}>
                    <th scope="row">
                      {packageNames(item.retrofits, catalogue)}
                    </th>
                    <td>{moneyRange(item.cost_gbp)}</td>
                    <td>{number(item.nominal_saving_kwh, 1, true)}</td>
                    <td>{number(item.min_saving_kwh, 1, true)}</td>
                    <td>{number(item.max_saving_kwh, 1, true)}</td>
                    <td>{number(item.max_regret_kwh, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p>
            Package-level evidence is unavailable in this response. No
            comparison values have been filled in.
          </p>
        )}
        <p className="fine-print">
          The gap compares a package with the best feasible package in each
          tested scenario. A smaller largest gap means less sensitivity in this
          test—not guaranteed savings.
        </p>
      </details>
    </>
  );
}
