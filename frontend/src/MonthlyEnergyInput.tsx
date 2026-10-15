import { useEffect, useRef, useState } from "react";
import { api, ApiError, errorMessage } from "./api";
import { Button, Notice } from "./components";
import { number } from "./format";
import type { EnergyInputs } from "./types";
import { periodIncludesPreCompletion } from "./workspaceModel";

export function lastCompletedMonth() {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - 1, 1))
    .toISOString()
    .slice(0, 7);
}

export function MonthlyEnergyInput({
  disabled,
  onApply,
  onDirtyChange,
  baselineAfterDate,
}: {
  disabled: boolean;
  onApply: (preview: EnergyInputs) => void;
  onDirtyChange: (dirty: boolean) => void;
  baselineAfterDate?: string;
}) {
  const [csv, setCsv] = useState("");
  const [endMonth, setEndMonth] = useState("");
  const [preview, setPreview] = useState<EnergyInputs | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applied, setApplied] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  function invalidate() {
    controller.current?.abort();
    setBusy(false);
    setError(null);
    setPreview(null);
    setApplied(false);
  }
  async function check() {
    invalidate();
    if (!endMonth || endMonth > lastCompletedMonth()) {
      setError(
        "Choose a completed end month. The current UTC month is not complete.",
      );
      return;
    }
    if (new TextEncoder().encode(csv).length > 16 * 1024) {
      setError("Use at most 16 KiB of CSV text and 36 monthly rows.");
      return;
    }
    const request = new AbortController();
    controller.current = request;
    setBusy(true);
    try {
      const result = await api.energyInputs(csv, endMonth, request.signal);
      if (!request.signal.aborted) setPreview(result);
    } catch (cause) {
      if (!request.signal.aborted)
        setError(
          cause instanceof ApiError && cause.status === 422
            ? "The monthly data could not be accepted. Use exactly month,electricity_kwh,gas_kwh, up to 36 unique completed YYYY-MM months and non-negative kWh. Leave unknown fuel cells blank; no formulas, extra columns or personal details."
            : errorMessage(cause),
        );
    } finally {
      if (!request.signal.aborted) setBusy(false);
    }
  }
  return (
    <details className="monthly-input">
      <summary>Use monthly CSV instead (optional)</summary>
      <p id="monthly-privacy">
        Paste only months and kWh, not bills, names, addresses or account
        numbers. Nothing is sent until you choose Preview. The calculation
        service does not save these rows; this does not send them to an AI
        provider.
      </p>
      <div className="form-grid">
        <label className="form-field">
          <span id="label-energy-end-month">
            Last month in your 12-month period
          </span>
          <input
            type="month"
            name="energy_end_month"
            aria-labelledby="label-energy-end-month"
            max={lastCompletedMonth()}
            value={endMonth}
            disabled={disabled}
            onChange={(e) => {
              invalidate();
              setEndMonth(e.target.value);
              onDirtyChange(Boolean(csv || e.target.value));
            }}
            aria-describedby="monthly-period-help"
          />
          <small id="monthly-period-help">
            Choose a completed month, not the current month. No date is assumed.
          </small>
        </label>
        <label className="form-field">
          <span id="label-energy-csv">Monthly energy CSV</span>
          <textarea
            name="energy_csv"
            aria-labelledby="label-energy-csv"
            value={csv}
            disabled={disabled}
            rows={5}
            spellCheck={false}
            autoComplete="off"
            placeholder={"month,electricity_kwh,gas_kwh\nYYYY-MM,220,800"}
            aria-describedby="monthly-privacy monthly-format"
            onChange={(e) => {
              invalidate();
              setCsv(e.target.value);
              onDirtyChange(Boolean(e.target.value || endMonth));
            }}
          />
          <small id="monthly-format">
            Exact headers: month,electricity_kwh,gas_kwh. Up to 36 rows, 16 KiB.
            A blank cell is unknown; 0 is an explicit zero. No seasonal scaling.
          </small>
        </label>
      </div>
      <Button
        disabled={disabled || busy || !csv.trim() || !endMonth}
        onClick={check}
      >
        {busy ? "Checking monthly data…" : "Preview 12-month totals"}
      </Button>
      {error ? <Notice kind="error">{error}</Notice> : null}
      {preview ? (
        <section className="energy-preview" aria-label="Monthly energy preview">
          <h3>
            {preview.period.start_month} to {preview.period.end_month}
          </h3>
          {periodIncludesPreCompletion(
            preview.period.start_month,
            baselineAfterDate,
          ) ? (
            <Notice kind="warning">
              This CSV period includes time before this property’s latest
              completed work ({baselineAfterDate}). These totals cannot confirm
              a post-work annual baseline.
            </Notice>
          ) : null}
          <p role="status">
            Electricity: {preview.coverage.electricity_months}/12 known months.{" "}
            Gas: {preview.coverage.gas_months}/12 known months.{" "}
            {preview.ignored_rows} rows outside this period ignored.
          </p>
          <dl className="intake-totals">
            <div>
              <dt>Annual grid electricity</dt>
              <dd>
                {preview.electricity_kwh === null
                  ? "Unknown — incomplete coverage"
                  : `${number(preview.electricity_kwh)} kWh`}
              </dd>
            </div>
            <div>
              <dt>Annual gas</dt>
              <dd>
                {preview.gas_kwh === null
                  ? "Unknown — incomplete coverage"
                  : `${number(preview.gas_kwh)} kWh`}
              </dd>
            </div>
            <div>
              <dt>Total purchased energy</dt>
              <dd>
                {preview.purchased_kwh === null
                  ? "Unknown"
                  : `${number(preview.purchased_kwh)} kWh`}
              </dd>
            </div>
          </dl>
          <div
            className="monthly-table-scroll"
            role="region"
            aria-label="Monthly readings"
            tabIndex={0}
          >
            <table>
              <caption>Monthly readings · kWh, not pounds</caption>
              <thead>
                <tr>
                  <th scope="col">Month</th>
                  <th scope="col">Grid electricity</th>
                  <th scope="col">Gas</th>
                </tr>
              </thead>
              <tbody>
                {preview.months.map((row) => (
                  <tr key={row.month}>
                    <th scope="row">{row.month}</th>
                    <td>
                      {row.electricity_kwh === null
                        ? "Unknown"
                        : number(row.electricity_kwh)}
                    </td>
                    <td>
                      {row.gas_kwh === null ? "Unknown" : number(row.gas_kwh)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {preview.missing_months.length ? (
            <p>Missing months: {preview.missing_months.join(", ")}.</p>
          ) : null}
          {preview.warnings.length ? (
            <ul>
              {preview.warnings.map((warning, i) => (
                <li key={i}>{warning}</li>
              ))}
            </ul>
          ) : null}
          <p>
            Apply replaces both annual fields. Incomplete fuel coverage clears
            that field to Unknown; no missing usage is guessed.
          </p>
          <Button
            variant="primary"
            disabled={disabled}
            onClick={() => {
              onApply(preview);
              setApplied(true);
            }}
          >
            Apply these annual totals
          </Button>
          {applied ? (
            <p role="status">
              Totals applied to the annual fields. Review them before saving the
              home.
            </p>
          ) : null}
        </section>
      ) : null}
    </details>
  );
}
