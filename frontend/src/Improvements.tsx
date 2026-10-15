import { useState } from "react";
import type { Assessment, Home, Recommendation, RetrofitId } from "./types";
import { api } from "./api";
import { useResource } from "./useResource";
import {
  Button,
  FuelTable,
  Loading,
  Notice,
  PageHeading,
  PackageSummary,
  RecommendationCard,
  RetrofitPicker,
} from "./components";

export function Improvements({
  home,
  baseline,
  selected,
  onChange,
  showDetails,
  compareSelected,
  setCompareSelected,
}: {
  home: Home;
  baseline: Assessment;
  selected: RetrofitId[];
  onChange: (ids: RetrofitId[]) => void;
  showDetails: (r: Recommendation) => void;
  compareSelected: RetrofitId[];
  setCompareSelected: (ids: RetrofitId[]) => void;
}) {
  const [compare, setCompare] = useState(false);
  const [retry, setRetry] = useState(0);
  const result = useResource(
    compare ? JSON.stringify([home, selected, compareSelected, retry]) : null,
    (signal) => api.compare(home, selected, compareSelected, signal),
  );
  const available = baseline.recommendations.filter((r) => r.feasible);
  const unavailable = baseline.recommendations.filter((r) => !r.feasible);
  return (
    <>
      <PageHeading title="A plan that fits your home">
        Explore suitable measures in the catalogue’s order—not a best-investment
        ranking. Every estimate is recomputed for your whole package.
      </PageHeading>
      <Notice>
        Indicative costs are prototype assumptions, not quotes. A measure can
        fit the budget alone while the combined package exceeds it.
      </Notice>
      <section className="improvement-grid" aria-label="Suitable improvements">
        {available.length ? (
          available.map((item) => (
            <RecommendationCard
              key={item.id}
              item={item}
              selected={selected.includes(item.id)}
              onToggle={() =>
                onChange(
                  selected.includes(item.id)
                    ? selected.filter((id) => id !== item.id)
                    : [...selected, item.id],
                )
              }
              onDetails={() => showDetails(item)}
            />
          ))
        ) : (
          <Notice>
            No catalogue improvements are currently feasible. Check the details
            and permissions below before planning work.
          </Notice>
        )}
      </section>
      <section className="card package-compare">
        <div className="section-heading">
          <div>
            <h2>Try a second approach</h2>
            <p>
              Keep your current plan as Package A and choose an independent
              Package B.
            </p>
          </div>
          <Button onClick={() => setCompare((value) => !value)}>
            {compare ? "Close comparison" : "Compare packages"}
          </Button>
        </div>
        {compare ? (
          <>
            <RetrofitPicker
              label="Package B · comparison"
              recommendations={baseline.recommendations}
              selected={compareSelected}
              onChange={setCompareSelected}
            />
            {result.loading ? (
              <Loading label="Comparing both packages from the same home…" />
            ) : null}
            {result.error ? (
              <Notice kind="error">
                <p>{result.error}</p>
                <Button onClick={() => setRetry((n) => n + 1)}>
                  Retry comparison
                </Button>
              </Notice>
            ) : null}
            {result.data ? (
              <>
                <FuelTable
                  assessment={result.data.package_a}
                  comparison={result.data.package_b}
                />
                <div className="package-summaries">
                  <section>
                    <h3>Package A · your plan</h3>
                    <PackageSummary scenario={result.data.package_a.scenario} />
                  </section>
                  <section>
                    <h3>Package B · comparison</h3>
                    <PackageSummary scenario={result.data.package_b.scenario} />
                    <Button onClick={() => onChange(compareSelected)}>
                      Use Package B as my plan
                    </Button>
                  </section>
                </div>
              </>
            ) : null}
          </>
        ) : null}
      </section>
      <section className="card unavailable-section">
        <h2>Not currently feasible</h2>
        <p>
          These are not recommendations for this home. Review the reason before
          changing any input.
        </p>
        {unavailable.length ? (
          unavailable.map((item) => (
            <div key={item.id} className="unavailable-item">
              <div>
                <h3>{item.name}</h3>
                <p>{item.reason}</p>
              </div>
              <Button onClick={() => showDetails(item)}>Details</Button>
            </div>
          ))
        ) : (
          <p>
            All catalogue measures currently pass the screening checks. A site
            survey is still required.
          </p>
        )}
      </section>
    </>
  );
}
