import { useState } from "react";
import { ArrowLeft, ArrowRight, Search, ShieldCheck } from "lucide-react";
import { Button, Loading, Notice } from "./components";
import { DEMO_PROPERTY_TYPES, loadDemoCatalogue } from "./demoCatalogue";
import type { CatalogueFilters } from "./demoCatalogue";
import { HomeThumbnail } from "./HomeComparison";
import { HEATING, REGIONS, moneyRange, number } from "./format";
import type { Home } from "./types";
import { useResource } from "./useResource";
import "./demoCatalogue.css";

const initial: CatalogueFilters = {
  q: "",
  property_type: "",
  status: "",
  page: 1,
};
const statusLabels: Record<string, string> = {
  available: "Improvement opportunity",
  no_affordable_option: "Budget-limited",
  no_modelled_benefit: "No further modelled saving",
  insufficient_evidence: "Needs more information",
  unsupported: "Outside calculation scope",
};

export function DemoCatalogue({
  onOpen,
  hasSavedWorkspace = false,
}: {
  onOpen: (home: Home) => void;
  hasSavedWorkspace?: boolean;
}) {
  const [draft, setDraft] = useState(initial);
  const [filters, setFilters] = useState(initial);
  const [retry, setRetry] = useState(0);
  const resource = useResource(JSON.stringify([filters, retry]), (signal) =>
    loadDemoCatalogue(filters, signal),
  );
  const data = resource.data;
  const first = data ? (data.page - 1) * data.page_size + 1 : 0;
  return (
    <div className="demo-catalogue">
      <header className="catalogue-heading">
        <div>
          <h1>Find a home to explore</h1>
          <p>
            Different homes, different decisions. Open an example, rotate its
            before-and-after view, and compare improvements using your tariffs.
          </p>
        </div>
        <span className="catalogue-scope">
          <ShieldCheck size={18} aria-hidden="true" />
          England & Wales · fictional examples
        </span>
      </header>
      <Notice>
        These are independently generated demonstrations, not surveyed homes,
        customer records or additional model-training data. Building shapes are
        illustrative. Savings depend on the recorded facts and stated
        assumptions.
        {hasSavedWorkspace ? (
          <p>
            Your saved workspace stays separate. Exploring a catalogue home
            switches to temporary mode without changing saved records.
          </p>
        ) : null}
      </Notice>
      <form
        className="catalogue-filters"
        onSubmit={(event) => {
          event.preventDefault();
          setFilters({ ...draft, q: draft.q.trim(), page: 1 });
          setRetry((value) => value + 1);
        }}
      >
        <label className="form-field catalogue-search">
          <span>Find an example</span>
          <div>
            <Search size={18} aria-hidden="true" />
            <input
              type="search"
              maxLength={100}
              value={draft.q}
              placeholder="Reference, region or feature"
              onChange={(event) =>
                setDraft({ ...draft, q: event.target.value })
              }
            />
          </div>
        </label>
        <label className="form-field">
          <span>Building type</span>
          <select
            aria-label="Building type"
            value={draft.property_type}
            onChange={(event) =>
              setDraft({ ...draft, property_type: event.target.value })
            }
          >
            <option value="">All building types</option>
            {DEMO_PROPERTY_TYPES.map((type) => (
              <option key={type}>{type}</option>
            ))}
          </select>
        </label>
        <label className="form-field">
          <span>Assessment status</span>
          <select
            aria-label="Assessment status"
            value={draft.status}
            onChange={(event) =>
              setDraft({ ...draft, status: event.target.value })
            }
          >
            <option value="">All statuses</option>
            {Object.entries(statusLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button className="button primary" type="submit">
          Find examples
        </button>
        <button
          className="button secondary"
          type="button"
          onClick={() => {
            setDraft(initial);
            setFilters(initial);
            setRetry((value) => value + 1);
          }}
        >
          Clear filters
        </button>
      </form>
      <div className="sr-only" role="status" aria-live="polite">
        {resource.loading
          ? "Loading fictional examples."
          : data
            ? `${data.filtered_total} matching examples. Page ${data.page} of ${data.page_count}.`
            : resource.error
              ? "Catalogue unavailable."
              : ""}
      </div>
      {resource.loading ? <Loading label="Finding your examples…" /> : null}
      {resource.error ? (
        <Notice kind="error">
          <p>{resource.error}</p>
          <Button onClick={() => setRetry((value) => value + 1)}>
            Retry catalogue
          </Button>
        </Notice>
      ) : null}
      {data ? (
        <>
          <section
            className="catalogue-overview"
            aria-label="Example catalogue summary"
          >
            <div>
              <strong>{data.total} fictional homes</strong>
              <span>{data.filtered_total} match your filters</span>
            </div>
            <div>
              <strong>{data.summary.assessed}</strong>
              <span>assessed in this filter</span>
            </div>
            <div>
              <strong>{data.summary.evidence_needed}</strong>
              <span>need evidence or are outside scope</span>
            </div>
          </section>
          <p className="catalogue-ranking-note">
            Global ranks compare estimated purchased-energy reduction—not bill
            savings or property values. Filters do not change those ranks.
          </p>
          {!data.entries.length ? (
            <div className="catalogue-empty">
              <h2>No examples match these filters.</h2>
              <p>
                Try another building type, shorter search or clear the filters.
              </p>
            </div>
          ) : (
            <div className="catalogue-grid">
              {data.entries.map((entry) => {
                const row = entry.ranking;
                return (
                  <article
                    className="catalogue-home"
                    key={entry.home.property_id}
                  >
                    <div className="catalogue-thumbnail">
                      <HomeThumbnail home={entry.home} />
                    </div>
                    <div className="catalogue-home-body">
                      <p className="catalogue-reference">
                        {entry.home.property_id} · {entry.home.property_type}
                      </p>
                      <h2>{entry.label}</h2>
                      <p className="catalogue-location">
                        {REGIONS[entry.home.region || ""] || "Region unknown"} ·{" "}
                        {entry.home.floor_area_m2 === null
                          ? "Area unknown"
                          : `${number(entry.home.floor_area_m2)} m²`}{" "}
                        · {HEATING[entry.home.heating || "unknown"]}
                      </p>
                      <span
                        className={`catalogue-status ${row.rank === null ? "needs-evidence" : ""}`}
                      >
                        {statusLabels[row.status]}
                      </span>
                      <dl className="catalogue-outcomes">
                        <div>
                          <dt>Current score</dt>
                          <dd>
                            {row.score === null
                              ? "Unknown"
                              : `${number(row.score)}/100`}
                          </dd>
                        </div>
                        <div>
                          <dt>Potential energy reduction</dt>
                          <dd>
                            {row.improvement_percent === null
                              ? "Unavailable"
                              : `${number(row.improvement_percent, 1)}%`}
                          </dd>
                        </div>
                      </dl>
                      <p className="catalogue-rank">
                        {row.rank === null
                          ? "Not numerically ranked"
                          : `Global rank ${row.rank}`}
                      </p>
                      <details>
                        <summary>Assumptions for this example</summary>
                        <p>{row.reason}</p>
                        <p>
                          Indicative suggested-package cost:{" "}
                          {moneyRange(row.cost_gbp)}. Current active-plan
                          budget:{" "}
                          {entry.home.budget_gbp === null
                            ? " not specified"
                            : ` £${number(entry.home.budget_gbp)}`}
                          .
                        </p>
                        <ul>
                          {entry.notes.map((note, i) => (
                            <li key={i}>{note}</li>
                          ))}
                        </ul>
                      </details>
                      <button
                        className="button primary catalogue-open"
                        onClick={() => onOpen(entry.home)}
                        aria-label={`Explore ${entry.label}`}
                      >
                        Explore this home{" "}
                        <ArrowRight size={17} aria-hidden="true" />
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
          {data.filtered_total > 0 ? (
            <nav
              className="catalogue-pagination"
              aria-label="Example catalogue pages"
            >
              <Button
                disabled={data.page <= 1}
                onClick={() =>
                  setFilters({ ...filters, page: filters.page - 1 })
                }
              >
                <ArrowLeft size={16} aria-hidden="true" /> Previous page
              </Button>
              <p>
                Showing {first}–{first + data.entries.length - 1} of{" "}
                {data.filtered_total}
                <span>
                  Page {data.page} of {data.page_count}
                </span>
              </p>
              <Button
                disabled={data.page >= data.page_count}
                onClick={() =>
                  setFilters({ ...filters, page: filters.page + 1 })
                }
              >
                Next page <ArrowRight size={16} aria-hidden="true" />
              </Button>
            </nav>
          ) : null}
          <details className="catalogue-provenance">
            <summary>How these fictional examples were made</summary>
            <p>{data.provenance.label}</p>
            <p>{data.policy}</p>
            <p>
              Generator {data.provenance.generator_version}. Catalogue version{" "}
              {data.version}. Used only for demonstrations, never for model
              training or accuracy claims.
            </p>
            <p>
              Content fingerprint: <code>{data.provenance.sha256}</code>
            </p>
          </details>
        </>
      ) : null}
    </div>
  );
}
