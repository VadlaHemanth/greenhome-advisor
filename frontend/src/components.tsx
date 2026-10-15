import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  ArrowRight,
  Check,
  CircleHelp,
  House,
  LoaderCircle,
  X,
} from "lucide-react";
import type {
  Assessment,
  CatalogueItem,
  Recommendation,
  RetrofitId,
  Scenario,
} from "./types";
import { isNumber, moneyRange, number } from "./format";
import { RetrofitIcon } from "./RetrofitIcon";

export function Button({
  children,
  onClick,
  disabled,
  variant = "secondary",
  type = "button",
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "secondary" | "text";
  type?: "button" | "submit";
  className?: string;
}) {
  return (
    <button
      type={type}
      className={`button ${variant} ${className}`}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}
export function Notice({
  children,
  kind = "info",
}: {
  children: ReactNode;
  kind?: "info" | "error" | "warning";
}) {
  return (
    <div
      className={`notice ${kind}`}
      role={kind === "error" ? "alert" : undefined}
    >
      {children}
    </div>
  );
}
export function Loading({
  label = "Recomputing from the saved home…",
}: {
  label?: string;
}) {
  return (
    <div className="loading" role="status">
      <LoaderCircle size={18} aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
export function PageHeading({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <h1>{title}</h1>
        <p>{children}</p>
      </div>
      {action}
    </div>
  );
}
export function Modal({
  title,
  children,
  close,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const closeRef = useRef(close);
  closeRef.current = close;
  useEffect(() => {
    const element = ref.current;
    const trigger =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    element?.showModal();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      element?.close();
      document.body.style.overflow = previous;
      trigger?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      tabIndex={-1}
      aria-labelledby="dialog-title"
      className="modal"
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const element = ref.current;
        if (!element) return;
        const controls = Array.from(
          element.querySelectorAll<HTMLElement>(
            'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex="0"]',
          ),
        ).filter((control) => control.getClientRects().length > 0);
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (!first || !last) {
          event.preventDefault();
          element.focus();
        } else if (
          event.shiftKey &&
          (document.activeElement === first ||
            !element.contains(document.activeElement))
        ) {
          event.preventDefault();
          last.focus();
        } else if (
          !event.shiftKey &&
          (document.activeElement === last ||
            !element.contains(document.activeElement))
        ) {
          event.preventDefault();
          first.focus();
        }
      }}
      onCancel={(event) => {
        event.preventDefault();
        closeRef.current();
      }}
    >
      <div className="modal-header">
        <h2 id="dialog-title">{title}</h2>
        <button
          aria-label="Close dialog"
          className="icon-button"
          onClick={close}
        >
          <X size={20} />
        </button>
      </div>
      <div className="modal-body">{children}</div>
    </dialog>
  );
}
export function Asset({
  src,
  alt,
  className = "",
  eager = false,
}: {
  src: string;
  alt: string;
  className?: string;
  eager?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  return (
    <div className={`asset ${className}`}>
      {failed ? (
        <div className="asset-unavailable">
          <House size={34} strokeWidth={1} aria-hidden="true" />
          <span>Concept image unavailable</span>
        </div>
      ) : (
        <img
          src={src}
          alt={alt}
          loading={eager ? "eager" : "lazy"}
          decoding="async"
          onError={() => setFailed(true)}
        />
      )}
    </div>
  );
}
export function ScoreGauge({ assessment }: { assessment: Assessment }) {
  const score = assessment.score;
  const total = score.total;
  const fraction = isNumber(total) ? Math.max(0, Math.min(1, total / 100)) : 0;
  return (
    <div
      className="score-gauge"
      aria-label={`Green Home Score: ${number(total)} out of 100. ${score.classification}`}
    >
      <svg viewBox="0 0 180 110" aria-hidden="true">
        <path
          d="M 16 91 A 74 74 0 0 1 164 91"
          pathLength="100"
          className="gauge-track"
        />
        <path
          d="M 16 91 A 74 74 0 0 1 164 91"
          pathLength="100"
          className="gauge-value"
          strokeDasharray={`${fraction * 100} 100`}
        />
      </svg>
      <div className={`gauge-label ${total === null ? "unavailable" : ""}`}>
        <strong>{isNumber(total) ? number(total) : "—"}</strong>
        <small>{isNumber(total) ? "/ 100" : "Missing inputs"}</small>
      </div>
      <span
        className={`tag ${["Poor", "Very poor"].includes(score.classification) ? "gold" : "sage"}`}
      >
        {score.classification}
      </span>
    </div>
  );
}
export function ScoreBreakdown({ assessment }: { assessment: Assessment }) {
  return (
    <div className="score-breakdown">
      <p>
        The current score is a fixed-weight screening measure, not an EPC
        assessment. Missing inputs remain unavailable.
      </p>
      {assessment.score.components.map((component) => (
        <div className="component-row" key={component.name}>
          <div>
            <span>{component.name}</span>
            <strong>
              {number(component.contribution, 1)}{" "}
              <small>/ {number(component.weight * 100)} points</small>
            </strong>
          </div>
          <div className="component-track">
            <span
              style={{
                width: `${isNumber(component.score) ? Math.max(0, Math.min(100, component.score)) : 0}%`,
              }}
            />
          </div>
          <small>
            {number(component.weight * 100)}% weight · sub-score{" "}
            {number(component.score, 1)} / 100
          </small>
        </div>
      ))}
      {assessment.score.issues.length ? (
        <Notice kind="warning">
          <strong>What needs attention</strong>
          <ul>
            {assessment.score.issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        </Notice>
      ) : null}
    </div>
  );
}
export function MetricCard({
  title,
  value,
  unit,
  detail,
  icon,
}: {
  title: string;
  value: string;
  unit?: string;
  detail: ReactNode;
  icon: ReactNode;
}) {
  return (
    <article className="metric-card card">
      <div className="metric-heading">
        <h2>{title}</h2>
        {icon}
      </div>
      <div className="metric-value">
        {value}
        {unit ? <span>{unit}</span> : null}
      </div>
      <div className="metric-detail">{detail}</div>
    </article>
  );
}
export function FuelTable({
  assessment,
  comparison,
}: {
  assessment: Assessment;
  comparison?: Assessment | null;
}) {
  const { baseline: b, scenario: a } = assessment;
  const after = comparison?.scenario;
  const rows = [
    [
      "Grid electricity",
      b.electricity_kwh,
      a.electricity_kwh,
      a.electricity_saving_kwh,
      after?.electricity_kwh,
      after?.electricity_saving_kwh,
    ],
    [
      "Gas · gross CV",
      b.gas_kwh,
      a.gas_kwh,
      a.gas_saving_kwh,
      after?.gas_kwh,
      after?.gas_saving_kwh,
    ],
  ] as const;
  return (
    <div className="fuel-comparison">
      <div
        className="table-region"
        role="region"
        aria-label="Annual fuel comparison"
        tabIndex={0}
      >
        <table>
          <caption>Annual purchased energy · kWh/year</caption>
          <thead>
            <tr>
              <th scope="col">Fuel</th>
              <th scope="col">Current</th>
              <th scope="col">{comparison ? "Package A" : "After"}</th>
              <th scope="col">Saving {comparison ? "A" : ""}</th>
              {comparison ? (
                <>
                  <th scope="col">Package B</th>
                  <th scope="col">Saving B</th>
                </>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row[0]}>
                <th scope="row">{row[0]}</th>
                <td>{number(row[1])}</td>
                <td>{number(row[2])}</td>
                <td
                  className={isNumber(row[3]) && row[3] < 0 ? "negative" : ""}
                >
                  {number(row[3], 0, true)}
                </td>
                {comparison ? (
                  <>
                    <td>{number(row[4])}</td>
                    <td
                      className={
                        isNumber(row[5]) && row[5] < 0 ? "negative" : ""
                      }
                    >
                      {number(row[5], 0, true)}
                    </td>
                  </>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="fine-print">
        Positive savings mean less purchased energy. Negative values mean an
        increase. Solar reduces grid imports, not the home’s underlying demand.
      </p>
    </div>
  );
}
export function PackageSummary({ scenario }: { scenario: Scenario }) {
  return (
    <dl className="summary-list">
      <div>
        <dt>Net energy saving</dt>
        <dd>
          {number(scenario.net_saving_kwh, 0, true)}
          <small>kWh/year</small>
        </dd>
      </div>
      <div>
        <dt>Carbon reduction</dt>
        <dd>
          {number(scenario.carbon_reduction_kgco2e, 1, true)}
          <small>kg CO₂e/year</small>
        </dd>
      </div>
      <div>
        <dt>Indicative cost</dt>
        <dd>{moneyRange(scenario.cost_gbp)}</dd>
      </div>
    </dl>
  );
}
export function RetrofitPicker({
  recommendations,
  selected,
  onChange,
  label,
}: {
  recommendations: Recommendation[];
  selected: RetrofitId[];
  onChange: (ids: RetrofitId[]) => void;
  label: string;
}) {
  return (
    <fieldset className="retrofit-picker">
      <legend>{label}</legend>
      {recommendations.map((item) => (
        <label
          key={item.id}
          className={`check-row ${!item.feasible ? "unfeasible" : ""}`}
        >
          <input
            type="checkbox"
            name={item.id}
            checked={selected.includes(item.id)}
            disabled={!item.feasible && !selected.includes(item.id)}
            onChange={(event) =>
              onChange(
                event.target.checked
                  ? [...selected, item.id]
                  : selected.filter((id) => id !== item.id),
              )
            }
          />
          <span>
            <strong>{item.name}</strong>
            <small>
              {item.feasible
                ? moneyRange(item.cost_gbp)
                : "Not currently feasible"}
            </small>
          </span>
        </label>
      ))}
    </fieldset>
  );
}
export function RecommendationCard({
  item,
  selected,
  onToggle,
  onDetails,
}: {
  item: Recommendation;
  selected: boolean;
  onToggle: () => void;
  onDetails: () => void;
}) {
  return (
    <article
      className={`improvement-card retrofit-card card ${selected ? "selected" : ""}`}
    >
      <div className="improvement-body">
        <div className="card-topline">
          <span className={`tag ${item.feasible ? "sage" : ""}`}>
            {item.feasible ? `${item.suitability} suitability` : "Not feasible"}
          </span>
          <span className="subtle">{moneyRange(item.cost_gbp)}</span>
        </div>
        <div className="retrofit-card__heading">
          <RetrofitIcon id={item.id} size="lg" />
          <h2>{item.name}</h2>
        </div>
        <p>{item.reason}</p>
        {item.standalone ? (
          <dl className="standalone-savings">
            <div>
              <dt>Electricity saving</dt>
              <dd>
                {number(item.standalone.electricity_saving_kwh, 0, true)}{" "}
                <small>kWh/year</small>
              </dd>
            </div>
            <div>
              <dt>Gas saving</dt>
              <dd>
                {number(item.standalone.gas_saving_kwh, 0, true)}{" "}
                <small>kWh/year</small>
              </dd>
            </div>
          </dl>
        ) : null}
        <div className="card-actions">
          <Button
            variant={selected ? "secondary" : "primary"}
            disabled={!item.feasible && !selected}
            onClick={onToggle}
          >
            {selected ? (
              <>
                <Check size={16} />
                Remove from plan
              </>
            ) : (
              "Add to plan"
            )}
          </Button>
          <button
            className="icon-button"
            aria-label={`View details for ${item.name}`}
            onClick={onDetails}
          >
            <ArrowRight size={18} />
          </button>
        </div>
      </div>
    </article>
  );
}
export function RecommendationDetails({ item }: { item: Recommendation }) {
  return (
    <>
      <span className={`tag ${item.feasible ? "sage" : "gold"}`}>
        {item.feasible
          ? `${item.suitability} suitability`
          : "Not currently feasible"}
      </span>
      <p className="detail-intro">{item.reason}</p>
      <h3>Indicative installation cost</h3>
      <p>{moneyRange(item.cost_gbp)} · a screening assumption, not a quote.</p>
      {item.standalone ? (
        <>
          <h3>Standalone screening estimate</h3>
          <PackageSummary scenario={item.standalone} />
          <p>
            Electricity saving:{" "}
            {number(item.standalone.electricity_saving_kwh, 0, true)} kWh/year.
            Gas saving: {number(item.standalone.gas_saving_kwh, 0, true)}{" "}
            kWh/year.
          </p>
          <p className="fine-print">
            Do not add these estimates together. The selected package is
            recomputed with interactions.
          </p>
          <details>
            <summary>Calculation assumptions</summary>
            <ul>
              {item.standalone.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </details>
        </>
      ) : (
        <Notice kind="warning">
          No savings estimate is available for this measure on the saved home.
        </Notice>
      )}
    </>
  );
}
export function Evidence({ assessment }: { assessment: Assessment }) {
  return (
    <div className="evidence-block">
      <h3>
        <CircleHelp size={17} aria-hidden="true" /> Assumptions & evidence
      </h3>
      <details className="source-quality">
        <summary>Where the numbers come from</summary>
        <ul>
          <li>
            <strong>Government data: consumption benchmark</strong>
            <p>
              Anonymised NEED data provides statistical context for energy use,
              not proof of savings for this home.
            </p>
          </li>
          <li>
            <strong>Scenario assumptions: retrofit savings/costs</strong>
            <p>
              Disclosed calculations and indicative cost ranges, not guaranteed
              outcomes or an installer quote.
            </p>
          </li>
          <li>
            <strong>Synthetic illustration: value only</strong>
            <p>
              Fictional scenarios only. Not market-calibrated, a valuation or a
              proven resale gain.
            </p>
          </li>
        </ul>
        <p>
          The sources below support different parts of the assessment. Not every
          input is government data; check the calculation assumptions as well.
        </p>
      </details>
      <details>
        <summary>Read calculation warnings and assumptions</summary>
        <ul>
          {[
            ...new Set([
              ...assessment.warnings,
              ...assessment.scenario.warnings,
              ...assessment.scenario.assumptions,
            ]),
          ].map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      </details>
      <div className="source-links">
        {assessment.sources
          .filter((s) => /^https?:\/\//.test(s.url))
          .map((s) => (
            <a key={s.url} href={s.url} target="_blank" rel="noreferrer">
              {s.label}
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
          ))}
      </div>
    </div>
  );
}
export function packageNames(
  ids: RetrofitId[] | null | undefined,
  catalogue: CatalogueItem[],
) {
  return ids?.length
    ? ids
        .map(
          (id) =>
            catalogue.find((item) => item.id === id)?.name ||
            id.replaceAll("_", " "),
        )
        .join(", ")
    : "No improvements selected";
}
