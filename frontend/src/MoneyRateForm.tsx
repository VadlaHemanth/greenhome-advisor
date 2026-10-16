import { useId, useRef } from "react";
import type { MoneyTariffField } from "./moneyTypes";
import { parseMoneyTariffs } from "./moneyValidation";
import type { MoneyController } from "./useMoneyPlan";

const dateFormat = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});

/** Both pages render this form; only the owning controller manages tariffs. */
export function MoneyRateForm({ controller }: { controller: MoneyController }) {
  const id = useId();
  const fields = useRef<
    Partial<Record<MoneyTariffField, HTMLInputElement | null>>
  >({});
  const { draft, errors, edit, calculate, useIllustration } = controller;
  const enteredDate = parseMoneyTariffs(draft).tariffs?.as_of;

  return (
    <form
      className="money-rate-form"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        const errors = calculate();
        const first = Object.keys(errors)[0] as MoneyTariffField | undefined;
        if (first) fields.current[first]?.focus();
      }}
    >
      <fieldset disabled={!controller.home}>
        <legend>Your energy unit rates</legend>
        <p id={`${id}-rate-hint`} className="money-hint">
          Use pence per kWh, not pounds. Blank means unknown; 0 is accepted.
          Supported range: 0–200 p/kWh, including fractional pence.
        </p>
        <div className="money-inputs">
          {(
            [
              ["electricity_pence", "Electricity unit rate (p/kWh)"],
              ["gas_pence", "Gas unit rate (p/kWh)"],
              ["as_of", "Rate date (optional)"],
            ] as const
          ).map(([field, label]) => (
            <div className="money-field" key={field}>
              <label htmlFor={`${id}-${field}`}>{label}</label>
              <input
                ref={(element) => {
                  fields.current[field] = element;
                }}
                id={`${id}-${field}`}
                name={field}
                type={field === "as_of" ? "date" : "text"}
                inputMode={field === "as_of" ? undefined : "decimal"}
                autoComplete="off"
                value={draft[field]}
                aria-invalid={errors[field] ? true : undefined}
                aria-describedby={[
                  `${id}-${field === "as_of" ? "date" : "rate"}-hint`,
                  errors[field] ? `${id}-${field}-error` : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                onChange={(event) => edit(field, event.target.value)}
              />
              {errors[field] && (
                <p
                  className="money-error"
                  id={`${id}-${field}-error`}
                  role="alert"
                >
                  {errors[field]}
                </p>
              )}
            </div>
          ))}
        </div>
        <p className="money-hint" id={`${id}-date-hint`}>
          The entered date records your source; it does not verify a tariff or
          its availability.
        </p>
      </fieldset>

      <div className="money-form-actions">
        <button
          type="submit"
          className="money-calculate"
          disabled={!controller.home}
        >
          Calculate
        </button>
        <button
          type="button"
          className="money-preset"
          disabled={!controller.home}
          onClick={useIllustration}
        >
          Use illustrative 25p / 7p preset
        </button>
      </div>
      <dl className="money-provenance">
        <div>
          <dt>Rate source</dt>
          <dd>
            {draft.source === "illustrative"
              ? "Illustrative rates — not current tariffs"
              : "User-entered rates"}
          </dd>
        </div>
        <div>
          <dt>Entered rate date</dt>
          <dd>
            {enteredDate ? (
              <time dateTime={enteredDate}>
                {dateFormat.format(new Date(`${enteredDate}T00:00:00Z`))}
              </time>
            ) : draft.as_of ? (
              "Date needs checking"
            ) : (
              "No date entered"
            )}
          </dd>
        </div>
      </dl>
      <p className="money-standing-note">
        Standing charges are excluded from before/after costs and assumed
        unchanged for savings—not zero. A heat pump does not imply removal of
        the gas supply or its standing charge.
      </p>
    </form>
  );
}
