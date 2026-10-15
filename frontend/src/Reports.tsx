import { useState } from "react";
import { Download, FileCheck2 } from "lucide-react";
import type { Assessment, Home } from "./types";
import { api, downloadJson } from "./api";
import { useResource } from "./useResource";
import { number } from "./format";
import { Button, Evidence, Loading, Notice, PageHeading } from "./components";

export function Reports({
  home,
  assessment,
}: {
  home: Home;
  assessment: Assessment | null;
}) {
  const [retry, setRetry] = useState(0);
  const metrics = useResource(`metrics-${retry}`, api.metrics);
  return (
    <>
      <PageHeading title="The evidence behind your plan">
        Inspect what was calculated, how the models performed, and where the
        limits remain.
      </PageHeading>
      <section className="report-download card">
        <FileCheck2 size={32} strokeWidth={1.3} aria-hidden="true" />
        <div>
          <h2>Your current assessment</h2>
          <p>
            Download the actual engine response, including inputs, package,
            assumptions, sources and model status.
          </p>
          <span className="tag sage">
            {home.data_kind === "synthetic_demo"
              ? "Fictional demonstration home"
              : "User-entered home"}
          </span>
        </div>
        <Button
          variant="primary"
          disabled={!assessment}
          onClick={() =>
            assessment &&
            downloadJson("greenhome-assessment.json", {
              exported_at: new Date().toISOString(),
              scope:
                "England and Wales screening pilot; estimates, not guarantees",
              assessment,
            })
          }
        >
          <Download size={16} aria-hidden="true" />
          Download JSON
        </Button>
      </section>
      <section className="card training-report">
        <div className="section-heading">
          <div>
            <h2>Actual held-out model results</h2>
            <p>
              Recorded evaluation results from the calculation service. These
              are model checks, not a customer installation plan.
            </p>
          </div>
          <Button onClick={() => setRetry((n) => n + 1)}>
            Refresh results
          </Button>
        </div>
        {metrics.loading ? (
          <Loading label="Loading recorded training results…" />
        ) : null}
        {metrics.error ? <Notice kind="error">{metrics.error}</Notice> : null}
        {metrics.data?.metrics ? (
          <>
            <h3>Annual energy benchmark</h3>
            <p className="fine-print">
              Errors are in kWh/year. Lower MAE and RMSE are better. Benchmark
              errors are not evidence of causal retrofit savings.
            </p>
            <div
              className="table-region"
              role="region"
              aria-label="Energy benchmark metrics"
              tabIndex={0}
            >
              <table>
                <thead>
                  <tr>
                    <th>Target</th>
                    <th>Split</th>
                    <th>Model MAE</th>
                    <th>Median baseline MAE</th>
                    <th>Model RMSE</th>
                    <th>Samples</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(metrics.data.metrics.energy || {}).flatMap(
                    ([fuel, splits]) =>
                      (["validation", "test"] as const).map((split) => {
                        const result = splits[split];
                        return result ? (
                          <tr key={`${fuel}-${split}`}>
                            <th scope="row" className="capitalize">
                              {fuel}
                            </th>
                            <td className="capitalize">{split}</td>
                            <td>{number(result.model?.mae, 1)}</td>
                            <td>{number(result.dummy_median?.mae, 1)}</td>
                            <td>{number(result.model?.rmse, 1)}</td>
                            <td>{number(result.model?.n)}</td>
                          </tr>
                        ) : null;
                      }),
                  )}
                </tbody>
              </table>
            </div>
            <h3>Synthetic value references</h3>
            <Notice kind="warning">
              This model is not calibrated to market prices or causal retrofit
              effects. Agreement with synthetic targets is not real-world value
              accuracy.
            </Notice>
            <div
              className="table-region"
              role="region"
              aria-label="Synthetic value model metrics"
              tabIndex={0}
            >
              <table>
                <thead>
                  <tr>
                    <th>Split</th>
                    <th>Model MAE · pp</th>
                    <th>Baseline MAE · pp</th>
                    <th>Model MAE · £</th>
                    <th>Active interval coverage</th>
                    <th>Samples</th>
                  </tr>
                </thead>
                <tbody>
                  {(["validation", "test"] as const).map((split) => {
                    const result =
                      metrics.data?.metrics?.synthetic_value?.[split];
                    return result ? (
                      <tr key={split}>
                        <th scope="row" className="capitalize">
                          {split}
                        </th>
                        <td>{number(result.p50_percent?.mae, 3)}</td>
                        <td>{number(result.dummy_median_percent?.mae, 3)}</td>
                        <td>{number(result.p50_gbp?.mae, 0)}</td>
                        <td>
                          {number(result.coverage_p10_p90_active_scenarios, 3)}
                        </td>
                        <td>{number(result.p50_percent?.n)}</td>
                      </tr>
                    ) : null;
                  })}
                </tbody>
              </table>
            </div>
            <p className="fine-print">
              pp = percentage points. Coverage is a fraction of held-out
              synthetic references, not a guarantee about any property.
            </p>
            <Button
              onClick={() =>
                downloadJson("greenhome-training-metrics.json", metrics.data)
              }
            >
              <Download size={16} aria-hidden="true" />
              Download actual metrics JSON
            </Button>
          </>
        ) : metrics.data ? (
          <Notice>
            Training results are unavailable or incomplete. No sample counts,
            errors or accuracy values have been filled in.
          </Notice>
        ) : null}
      </section>
      {assessment ? (
        <section className="card model-context">
          <h2>Model context for this home</h2>
          <h3>Energy benchmark</h3>
          {assessment.energy_benchmark ? (
            <>
              <p>{assessment.energy_benchmark.note}</p>
              <dl className="summary-list">
                <div>
                  <dt>Predicted electricity</dt>
                  <dd>
                    {number(assessment.energy_benchmark.electricity_kwh)}
                    <small>kWh/year</small>
                  </dd>
                </div>
                <div>
                  <dt>Predicted gas</dt>
                  <dd>
                    {number(assessment.energy_benchmark.gas_kwh)}
                    <small>kWh/year</small>
                  </dd>
                </div>
              </dl>
              <p className="fine-print">
                Status: {assessment.energy_benchmark.status}. Statistical
                context only; the saved consumption remains the retrofit
                baseline.
              </p>
            </>
          ) : (
            <Notice>
              Energy benchmark unavailable. No model prediction replaces missing
              measured consumption.
            </Notice>
          )}
          <h3>Value model</h3>
          <p>{assessment.value_impact.note}</p>
          <p className="fine-print">Status: {assessment.value_impact.status}</p>
          <Evidence assessment={assessment} />
        </section>
      ) : null}
    </>
  );
}
