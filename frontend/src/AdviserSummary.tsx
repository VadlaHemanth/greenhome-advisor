import type { RankedHome } from "./types";
import { number } from "./format";

export function AdviserSummary({
  rows,
  loading,
  available = true,
}: {
  rows: RankedHome[];
  loading: boolean;
  available?: boolean;
}) {
  const assessed = rows.filter(
    (row) =>
      row.status !== "insufficient_evidence" && row.status !== "unsupported",
  );
  const covered = assessed.filter(
    (row) =>
      typeof row.carbon_reduction_kgco2e === "number" &&
      Number.isFinite(row.carbon_reduction_kgco2e),
  );
  const carbon = covered.length
    ? covered.reduce((sum, row) => sum + row.carbon_reduction_kgco2e!, 0)
    : null;
  const unknownScore = rows.filter((row) => row.score === null).length;
  const ready = available && !loading;
  const missingLabel = loading ? "—" : "Unavailable";
  return (
    <section
      className="adviser-overview"
      aria-label="Adviser assessment summary"
    >
      <div className="adviser-stat">
        <span>Homes in this view</span>
        <strong>{ready ? rows.length : missingLabel}</strong>
        <small>Fictional examples, not a loan book</small>
      </div>
      <div className="adviser-stat">
        <span>Assessed opportunity</span>
        <strong>{ready ? assessed.length : missingLabel}</strong>
        <small>
          {ready
            ? `${rows.length - assessed.length} need evidence or are outside scope`
            : "Waiting for a successful assessment"}
        </small>
      </div>
      <div className="adviser-stat">
        <span>Poor or very poor</span>
        <strong>
          {ready ? rows.filter((row) => row.flagged).length : missingLabel}
        </strong>
        <small>
          {ready
            ? `${unknownScore} without a complete score`
            : "Classification not available"}
        </small>
      </div>
      <div className="adviser-stat">
        <span>Projected operational carbon reduction</span>
        <strong>
          {!ready
            ? missingLabel
            : carbon === null
              ? "Not assessed"
              : `${number(carbon)} kg`}
        </strong>
        <small>
          {ready
            ? `Per year, across ${covered.length} of ${rows.length} homes; not measured savings`
            : "No aggregate is shown without current results"}
        </small>
      </div>
    </section>
  );
}
