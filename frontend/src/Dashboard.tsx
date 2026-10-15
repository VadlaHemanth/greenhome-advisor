import {
  ArrowRight,
  Flame,
  Leaf,
  Pencil,
  Ruler,
  ShieldCheck,
  Sun,
  Zap,
} from "lucide-react";
import type {
  Assessment,
  Home,
  Page,
  Recommendation,
  RetrofitId,
} from "./types";
import {
  HEATING,
  isNumber,
  moneyRange,
  number,
  percentageRange,
} from "./format";
import {
  Button,
  Evidence,
  FuelTable,
  MetricCard,
  Notice,
  ScoreGauge,
} from "./components";
import { HomeSchematic } from "./HomeSchematic";
import { RetrofitIcon } from "./RetrofitIcon";
import "./planOverview.css";

export function Dashboard({
  home,
  baseline,
  plan,
  planLoading,
  edit,
  navigate,
  showScore,
  showDetails,
  selected = plan?.selected_retrofits ?? [],
  onChange,
}: {
  home: Home;
  baseline: Assessment;
  plan: Assessment | null;
  planLoading: boolean;
  edit: () => void;
  navigate: (page: Page) => void;
  showScore: () => void;
  showDetails: (r: Recommendation) => void;
  selected?: RetrofitId[];
  onChange?: (ids: RetrofitId[]) => void;
}) {
  const hasSelection = selected.length > 0;
  // Preview an already-computed standalone option without selecting or saving
  // it. Never turn a joint-only zero into a standalone recommendation.
  const preview = !hasSelection
    ? baseline.recommendations.find(
        (item) =>
          item.feasible &&
          item.standalone &&
          (item.standalone.net_saving_kwh === null ||
            item.standalone.net_saving_kwh > 0),
      )
    : undefined;
  const top =
    preview ??
    baseline.recommendations.find(
      (item) => item.feasible && !selected.includes(item.id),
    );
  const scenario = hasSelection ? plan?.scenario : preview?.standalone;
  const value = plan?.value_impact;
  const synthetic = home.data_kind === "synthetic_demo";
  const valueAvailable =
    synthetic &&
    value?.status === "synthetic_illustration" &&
    isNumber(value.low_gbp) &&
    isNumber(value.high_gbp);
  return (
    <>
      <section className="hero intake-hero">
        <div className="hero-copy">
          <h1>
            A considered plan.
            <br />A greener home.
          </h1>
          <p>
            {baseline.score.total === null
              ? "Start with the details you know. Missing readings stay unknown, so we’ll show what you need to check."
              : "See your energy use, choose suitable improvements and compare what could change. Estimates, not promises."}
          </p>
          <Button variant="text" onClick={() => navigate("improvements")}>
            Explore improvements <ArrowRight size={17} aria-hidden="true" />
          </Button>
        </div>
        <HomeSchematic home={home} selected={selected} />
      </section>
      <div className="data-context">
        <ShieldCheck size={15} aria-hidden="true" />
        <span>
          {synthetic
            ? "Fictional demonstration home"
            : "User-entered home · not independently verified"}
        </span>
        <span className="context-separator">·</span>
        <span>England & Wales pilot</span>
      </div>
      <div className="release-compare-link">
        <p>
          <strong>What could this mean for your bills?</strong>Enter your
          tariffs and compare suitable packages. Energy and money savings are
          different.
        </p>
        <Button variant="primary" onClick={() => navigate("money")}>
          Compare costs & packages
        </Button>
      </div>
      <section
        className="metric-grid"
        aria-label="Current home and selected package"
      >
        <article className="metric-card score-card card">
          <div className="metric-heading">
            <h2>Green Home Score</h2>
            <button
              className="icon-button small-icon"
              onClick={showScore}
              aria-label="View score breakdown"
            >
              <Ruler size={16} />
            </button>
          </div>
          <ScoreGauge assessment={baseline} />
          <button className="text-link" onClick={showScore}>
            View breakdown <ArrowRight size={14} aria-hidden="true" />
          </button>
        </article>
        <MetricCard
          title="Annual energy use"
          value={number(baseline.baseline.purchased_kwh)}
          unit="kWh / year"
          icon={<Zap size={18} aria-hidden="true" />}
          detail={
            <div className="fuel-mini">
              <div>
                <span>
                  <Zap size={13} />
                  Grid electricity
                </span>
                <strong>{number(baseline.baseline.electricity_kwh)}</strong>
              </div>
              <div>
                <span>
                  <Flame size={13} />
                  Gas · gross CV
                </span>
                <strong>{number(baseline.baseline.gas_kwh)}</strong>
              </div>
              <small>Current purchased energy, not predicted bills.</small>
            </div>
          }
        />
        <MetricCard
          title={
            hasSelection ? "Selected energy saving" : "Suggested energy saving"
          }
          value={
            planLoading
              ? "Calculating…"
              : number(scenario?.net_saving_kwh, 0, true)
          }
          unit={scenario ? "kWh / year" : undefined}
          icon={<Leaf size={18} aria-hidden="true" />}
          detail={
            <>
              {hasSelection ? (
                <>
                  <span className="tag sage">
                    {planLoading
                      ? "Updating plan"
                      : scenario && isNumber(scenario.improvement_percent)
                        ? `${number(scenario.improvement_percent, 1)}% purchased-energy change`
                        : "No complete estimate"}
                  </span>
                  <p>Recalculated for the whole selected package.</p>
                </>
              ) : (
                <>
                  {preview ? (
                    <>
                      <span className="tag sage">Preview · {preview.name}</span>
                      <p>
                        {isNumber(scenario?.net_saving_kwh)
                          ? "One suitable starting point, not yet selected or saved."
                          : "More energy readings are needed for a complete saving estimate."}
                      </p>
                      {onChange ? (
                        <button
                          className="text-link metric-action"
                          onClick={() => onChange([preview.id])}
                        >
                          Use suggested plan{" "}
                          <ArrowRight size={14} aria-hidden="true" />
                        </button>
                      ) : null}
                    </>
                  ) : (
                    <p>
                      No standalone estimate is available under the current
                      details, permissions and budget.
                    </p>
                  )}
                  <button
                    className="text-link metric-action"
                    onClick={() => navigate("improvements")}
                  >
                    Choose improvements{" "}
                    <ArrowRight size={14} aria-hidden="true" />
                  </button>
                </>
              )}
            </>
          }
        />
        <MetricCard
          title="Operational carbon"
          value={
            planLoading
              ? "Calculating…"
              : number(scenario?.carbon_reduction_kgco2e, 0, true)
          }
          unit={scenario ? "kg CO₂e / year reduction" : undefined}
          icon={<Sun size={18} aria-hidden="true" />}
          detail={
            <>
              <p>
                {hasSelection
                  ? "Calculated from the signed electricity and gas changes."
                  : preview
                    ? `Preview for ${preview.name.toLowerCase()}. Both fuel readings are needed to calculate carbon.`
                    : "No complete carbon estimate is available. Review suitable improvements and missing readings."}
              </p>
              <small>Operational emissions estimate, not a guarantee.</small>
            </>
          }
        />
      </section>
      <section className="home-glance card">
        <div className="section-heading">
          <h2>Your home at a glance</h2>
          <Button onClick={edit}>
            <Pencil size={14} aria-hidden="true" /> Edit details
          </Button>
        </div>
        <dl className="home-facts">
          <div>
            <dt>Property type</dt>
            <dd>{home.property_type || "Unknown"}</dd>
          </div>
          <div>
            <dt>Floor area</dt>
            <dd>
              {number(home.floor_area_m2)}
              {isNumber(home.floor_area_m2) ? " m²" : ""}
            </dd>
          </div>
          <div>
            <dt>Recorded EPC</dt>
            <dd>{home.epc_rating || "Unknown"}</dd>
          </div>
          <div>
            <dt>Heating</dt>
            <dd>{HEATING[home.heating || "unknown"]}</dd>
          </div>
          <div>
            <dt>Insulation</dt>
            <dd className="capitalize">{home.insulation || "Unknown"}</dd>
          </div>
        </dl>
      </section>
      <div className="dashboard-lower">
        <section className="recommendation-feature card">
          <div className="recommendation-copy">
            <span className="tag gold">
              {hasSelection
                ? "Another suitable improvement"
                : "A suitable starting point"}
            </span>
            <h2 className="display">
              {top?.name ||
                (hasSelection
                  ? "Your selection is ready to compare"
                  : "Check your home details")}
            </h2>
            <p>
              {top?.reason ||
                (hasSelection
                  ? "Review the combined fuel changes and cost range before deciding on your next step."
                  : "No suitable option is confirmed yet. Check missing details, existing features and permissions.")}
            </p>
            <div className="starting-point-actions">
              {top && onChange ? (
                <Button
                  variant="primary"
                  disabled={planLoading}
                  onClick={() => onChange([...selected, top.id])}
                >
                  Add {top.name.toLowerCase()}{" "}
                  <ArrowRight size={16} aria-hidden="true" />
                </Button>
              ) : null}
              <Button
                variant={top && onChange ? "secondary" : "primary"}
                onClick={() =>
                  top
                    ? showDetails(top)
                    : navigate(hasSelection ? "plan" : "home")
                }
              >
                {top
                  ? "View improvement"
                  : hasSelection
                    ? "Review my plan"
                    : "Review my home"}
              </Button>
            </div>
          </div>
          {top ? (
            <div className="feature-retrofit-icon">
              <RetrofitIcon id={top.id} />
            </div>
          ) : (
            <div className="feature-leaf">
              <Leaf size={58} strokeWidth={1} aria-hidden="true" />
            </div>
          )}
        </section>
        <section className="value-card card">
          <div className="section-heading">
            <h2>What about property value?</h2>
            <span className="tag gold">Synthetic model</span>
          </div>
          <strong className="value-range">
            {valueAvailable
              ? moneyRange([value.low_gbp, value.high_gbp])
              : !hasSelection && synthetic
                ? "Choose a plan first"
                : "No market estimate"}
          </strong>
          {valueAvailable ? (
            <p className="value-percent">
              {percentageRange(value.low_percent, value.high_percent)}{" "}
              illustrative impact
            </p>
          ) : null}
          <p>
            {!hasSelection && synthetic
              ? "No improvements are selected. A synthetic before-and-after range can appear for a supported plan."
              : value?.note ||
                "A value result appears only when the model returns one for this scenario."}
          </p>
          <small>
            Not market-calibrated. Not a proven causal premium or valuation.
          </small>
        </section>
      </div>
      <section className="comparison-card card">
        <div className="section-heading">
          <div>
            <h2>
              {hasSelection
                ? "Current home → your selected plan"
                : "Compare a plan with your current home"}
            </h2>
            <p>
              {hasSelection
                ? "Annual changes, one consistent baseline."
                : "Select improvements first. We keep the current readings as the baseline."}
            </p>
          </div>
          <Button onClick={() => navigate("improvements")}>
            Compare packages <ArrowRight size={15} aria-hidden="true" />
          </Button>
        </div>
        {!hasSelection ? (
          <p className="comparison-empty">
            No improvements selected. The suggested estimate above is a preview;
            use it or choose other measures to compare your selected plan.
          </p>
        ) : plan ? (
          <FuelTable assessment={plan} />
        ) : (
          <Notice>
            {planLoading
              ? "Your package is being recalculated."
              : "No valid package result is available. Adjust the selected measures or retry."}
          </Notice>
        )}
      </section>
      <Evidence assessment={plan || baseline} />
    </>
  );
}
