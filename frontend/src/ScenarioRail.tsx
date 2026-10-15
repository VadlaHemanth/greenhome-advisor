import { ArrowRight, Check, Plus, RotateCcw, Sparkles } from "lucide-react";
import type {
  Assessment,
  CatalogueItem,
  Recommendation,
  RetrofitId,
} from "./types";
import {
  Button,
  Loading,
  Notice,
  PackageSummary,
  RetrofitPicker,
} from "./components";
import { number } from "./format";
import { RetrofitIcon } from "./RetrofitIcon";
import "./planOverview.css";

export function ScenarioRail({
  baseline,
  assessment,
  selected,
  onChange,
  loading,
  error,
  retry,
  openImprovements,
  openQuestions,
  openDetails,
  undo,
}: {
  baseline: Assessment | null;
  assessment: Assessment | null;
  selected: RetrofitId[];
  onChange: (ids: RetrofitId[]) => void;
  loading: boolean;
  error: string | null;
  retry: () => void;
  catalogue: CatalogueItem[];
  openImprovements: () => void;
  openQuestions: () => void;
  openDetails: (r: Recommendation) => void;
  undo?: () => void;
}) {
  const recommendations = baseline?.recommendations || [];
  const feasible = recommendations.filter((item) => item.feasible);
  return (
    <aside className="scenario-rail" aria-label="Your improvement scenario">
      <section className="scenario-card card">
        <div className="section-heading">
          <h2>Your scenario</h2>
          <span className="tag sage">Package A</span>
        </div>
        <p className="fine-print">
          Choose improvements. Estimates update for the whole package.
        </p>
        {baseline ? (
          <details className="picker-details">
            <summary>
              {selected.length
                ? `${selected.length} improvement${selected.length === 1 ? "" : "s"} selected`
                : "Add improvements"}
              <span aria-hidden="true">+</span>
            </summary>
            <RetrofitPicker
              label="Measures in your plan"
              recommendations={recommendations}
              selected={selected}
              onChange={onChange}
            />
          </details>
        ) : (
          <Loading label="Loading home suitability…" />
        )}
        {loading ? <Loading /> : null}
        {error ? (
          <Notice kind="error">
            <p>{error}</p>
            <Button onClick={retry}>Retry package</Button>
          </Notice>
        ) : null}
        {assessment && selected.length > 0 && !loading ? (
          <>
            <h3 className="rail-subheading">Projected annual changes</h3>
            <PackageSummary scenario={assessment.scenario} />
            <div className="rail-fuels">
              <div>
                <span>Electricity saving</span>
                <strong>
                  {number(assessment.scenario.electricity_saving_kwh, 0, true)}{" "}
                  <small>kWh</small>
                </strong>
              </div>
              <div>
                <span>Gas saving</span>
                <strong>
                  {number(assessment.scenario.gas_saving_kwh, 0, true)}{" "}
                  <small>kWh</small>
                </strong>
              </div>
            </div>
          </>
        ) : null}
        {!selected.length && !loading ? (
          <div className="empty-plan-guidance">
            <h3>Start with one improvement</h3>
            <p>
              No improvements selected. Add a suitable measure below to see
              energy, carbon and cost estimates.
            </p>
            <small>
              Nothing is added automatically. Zero is the unchanged baseline,
              not your home's potential.
            </small>
          </div>
        ) : null}
        <Button
          variant="primary"
          onClick={openImprovements}
          className="full-width"
        >
          Build & compare your plan <ArrowRight size={16} aria-hidden="true" />
        </Button>
        {selected.length ? (
          <button className="text-link clear-plan" onClick={() => onChange([])}>
            <RotateCcw size={13} aria-hidden="true" />
            Clear selected improvements
          </button>
        ) : null}
        {undo ? (
          <div role="status">
            <p>Selected improvements cleared.</p>
            <Button onClick={undo}>Undo clear</Button>
          </div>
        ) : null}
      </section>
      <section className="rail-recommendations card">
        <div className="section-heading">
          <h2>Suitable improvements</h2>
          <button className="text-link" onClick={openImprovements}>
            See all <ArrowRight size={13} aria-hidden="true" />
          </button>
        </div>
        {feasible.length ? (
          feasible.slice(0, 3).map((item) => (
            <div className="rail-recommendation" key={item.id}>
              <button
                className="rail-rec-details"
                onClick={() => openDetails(item)}
              >
                <RetrofitIcon id={item.id} className="rail-retrofit-icon" />
                <span className="rail-rec-copy">
                  <strong>{item.name}</strong>
                  <span className="tag gold">
                    {item.suitability} suitability
                  </span>
                  <small>View details</small>
                </span>
              </button>
              <button
                className={`rail-quick-add ${selected.includes(item.id) ? "is-selected" : ""}`}
                type="button"
                aria-label={`${selected.includes(item.id) ? "Remove" : "Add"} ${item.name} ${selected.includes(item.id) ? "from" : "to"} plan`}
                aria-pressed={selected.includes(item.id)}
                disabled={loading}
                onClick={() =>
                  onChange(
                    selected.includes(item.id)
                      ? selected.filter((id) => id !== item.id)
                      : [...selected, item.id],
                  )
                }
              >
                {selected.includes(item.id) ? (
                  <Check size={17} aria-hidden="true" />
                ) : (
                  <Plus size={17} aria-hidden="true" />
                )}
                <span>{selected.includes(item.id) ? "Remove" : "Add"}</span>
              </button>
            </div>
          ))
        ) : (
          <p className="fine-print">
            No feasible options are confirmed yet. Review property details and
            permissions.
          </p>
        )}
      </section>
      <div className="rail-guidance">
        <Sparkles size={19} strokeWidth={1.5} aria-hidden="true" />
        <h3>A question before you commit?</h3>
        <p>
          Explore a what-if, or stress-test your plan against different
          assumptions.
        </p>
        <button className="text-link" onClick={openQuestions}>
          Ask & explore <ArrowRight size={14} aria-hidden="true" />
        </button>
      </div>
      <p className="rail-disclaimer">
        Screening estimates only. Confirm suitability, consent and costs with a
        qualified installer.
      </p>
    </aside>
  );
}
