import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Check, ShieldCheck } from "lucide-react";
import { api, ApiError, errorMessage } from "./api";
import { HEATING, REGIONS } from "./format";
import type { Home } from "./types";
import { Button, Notice } from "./components";
import { MonthlyEnergyInput } from "./MonthlyEnergyInput";
import { periodIncludesPreCompletion } from "./workspaceModel";
import "./intake.css";

type Field = {
  key: keyof Home;
  label: string;
  unit?: string;
  min?: number;
  max?: number;
  step?: string;
  help?: string;
};
const propertyNumbers: Field[] = [
  {
    key: "floor_area_m2",
    label: "Floor area",
    unit: "m²",
    min: 0.01,
    max: 100000,
    help: "Use total floor area from the EPC or a measured floor plan, not the plot or garden. Leave blank if unsure.",
  },
  {
    key: "electricity_kwh",
    label: "Annual grid electricity use",
    unit: "kWh/year",
    min: 0,
    max: 10000000,
    help: "Your supplier’s annual statement or account shows imported electricity in kWh. Use a full 12-month period, not pounds or solar generation.",
  },
  {
    key: "gas_kwh",
    label: "Annual gas consumption",
    unit: "kWh/year",
    min: 0,
    max: 10000000,
    help: "Use annual gas kWh from your bill, not pounds or cubic metres.",
  },
  {
    key: "solar_kwp",
    label: "Existing solar capacity",
    unit: "kWp",
    min: 0,
    max: 10000,
    help: "Enter 0 only if confirmed absent.",
  },
  {
    key: "current_value_gbp",
    label: "Current estimated home value",
    unit: "£",
    min: 0.01,
    max: 1000000000000,
  },
  {
    key: "budget_gbp",
    label: "Installation budget · active plan",
    unit: "£",
    min: 0,
    max: 1000000000,
    help: "For the active selected plan, not cumulative historical spending. Blank means no active-plan limit. In a saved workspace, the separate customer shared cap still reserves completed work; completing it does not free that allocation.",
  },
];
const assumptions: Field[] = [
  {
    key: "space_heat_fraction",
    label: "Space-heating share of fuel",
    min: 0,
    max: 1,
    help: "Fraction between 0 and 1. Engine default: 0.80.",
  },
  {
    key: "boiler_efficiency",
    label: "Boiler efficiency · gross CV",
    min: 0.01,
    max: 1,
    help: "Fraction above 0 through 1. Engine default: 0.85.",
  },
  {
    key: "heat_pump_spf",
    label: "Heat-pump seasonal performance",
    min: 1,
    max: 6,
    help: "Seasonal performance factor. Engine default: 3.0.",
  },
  {
    key: "solar_yield_kwh_per_kwp",
    label: "Annual solar yield",
    unit: "kWh/kWp",
    min: 0.01,
    max: 2000,
    help: "Engine default: 900 kWh/kWp/year.",
  },
  {
    key: "solar_self_consumption_fraction",
    label: "Solar self-consumption share",
    min: 0,
    max: 1,
    help: "Fraction between 0 and 1. Engine default: 0.45.",
  },
];
const booleanFields: Field[] = [
  { key: "smart_controls", label: "Smart heating controls installed" },
  { key: "roof_access", label: "Roof access and permission confirmed" },
  { key: "listed_building", label: "Listed building" },
  {
    key: "consent_confirmed",
    label: "Required installation consent confirmed",
  },
  { key: "heat_pump_ready", label: "Heat-pump installer checks completed" },
];

export function HomeForm({
  home,
  onSave,
  onCancel,
  onDirtyChange,
  workspaceBaseline,
  baselineAfterDate,
  initialMode = "full",
}: {
  home: Home;
  onSave: (home: Home, baselineConfirmed?: boolean) => void;
  onCancel?: () => void;
  onDirtyChange?: (dirty: boolean) => void;
  workspaceBaseline?: "current" | "needs_update";
  baselineAfterDate?: string;
  initialMode?: "guided" | "full";
}) {
  const [mode, setMode] = useState(initialMode);
  const [step, setStep] = useState(0);
  const [csvDirty, setCsvDirty] = useState(false);
  const [energyPeriod, setEnergyPeriod] = useState<string | null>(null);
  const [csvFuelStarts, setCsvFuelStarts] = useState<{
    electricity_kwh: string | null;
    gas_kwh: string | null;
  }>({ electricity_kwh: null, gas_kwh: null });
  const [noGasConfirmed, setNoGasConfirmed] = useState(home.gas_kwh === 0);
  const formRef = useRef<HTMLFormElement>(null);
  const stepHeading = useRef<HTMLHeadingElement>(null);
  const guided = mode === "guided";
  const steps = ["Home basics", "Energy", "Features & permissions", "Review"];
  function goStep(next: number) {
    setStep(next);
    requestAnimationFrame(() => stepHeading.current?.focus());
  }
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      Object.entries(home).map(([k, v]) => [
        k,
        v === null || v === undefined ? "" : String(v),
      ]),
    ),
  );
  const [fictional, setFictional] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [invalidFields, setInvalidFields] = useState<string[]>([]);
  const [confirmedAfterCompletion, setConfirmedAfterCompletion] =
    useState(false);
  const [saving, setSaving] = useState(false);
  const requestRef = useRef<AbortController | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const homeKey = JSON.stringify([home, workspaceBaseline, baselineAfterDate]);
  const requiresPostCompletionConfirmation =
    workspaceBaseline === "needs_update" || Boolean(baselineAfterDate);
  const preCompletionPeriod = Object.values(csvFuelStarts).some((start) =>
    periodIncludesPreCompletion(start, baselineAfterDate),
  );
  const blockedAnnualBaseline =
    preCompletionPeriod &&
    Boolean(draft.electricity_kwh?.trim() && draft.gas_kwh?.trim());
  const initialDraft = Object.fromEntries(
    Object.entries(home).map(([k, v]) => [
      k,
      v === null || v === undefined ? "" : String(v),
    ]),
  );
  const dirty =
    JSON.stringify(draft) !== JSON.stringify(initialDraft) ||
    fictional ||
    confirmedAfterCompletion ||
    csvDirty;
  const notifyDirty = useRef(onDirtyChange);
  notifyDirty.current = onDirtyChange;
  useEffect(() => {
    notifyDirty.current?.(dirty);
  }, [dirty]);
  useEffect(() => () => notifyDirty.current?.(false), []);
  const latestKey = useRef(homeKey);
  latestKey.current = homeKey;
  const loadedKey = useRef(homeKey);
  const latestHome = useRef(home);
  latestHome.current = home;
  useEffect(() => {
    if (loadedKey.current !== homeKey) {
      requestRef.current?.abort();
      setDraft(
        Object.fromEntries(
          Object.entries(latestHome.current).map(([key, value]) => [
            key,
            value === null || value === undefined ? "" : String(value),
          ]),
        ),
      );
      setFictional(false);
      setMode(initialMode);
      setStep(0);
      setCsvDirty(false);
      setEnergyPeriod(null);
      setCsvFuelStarts({ electricity_kwh: null, gas_kwh: null });
      setNoGasConfirmed(latestHome.current.gas_kwh === 0);
      setConfirmedAfterCompletion(false);
      setInvalidFields([]);
      setError(null);
      setSaving(false);
      loadedKey.current = homeKey;
    }
    return () => {
      requestRef.current?.abort();
    };
  }, [homeKey, initialMode]);
  const update = (key: keyof Home, value: string) => {
    if (key === "electricity_kwh" || key === "gas_kwh") {
      setConfirmedAfterCompletion(false);
      setEnergyPeriod(null);
      // A manual edit clears only this fuel's CSV provenance, not its sibling fuel.
      setCsvFuelStarts((previous) => ({ ...previous, [key]: null }));
    }
    if (key === "gas_kwh") setNoGasConfirmed(false);
    setDraft((previous) => ({ ...previous, [key]: value }));
  };

  const numberField = (field: Field) => (
    <label className="form-field" key={field.key}>
      <span id={`label-${field.key}`}>
        {field.label}
        {field.unit ? <small>{field.unit}</small> : null}
      </span>
      <input
        type="number"
        inputMode="decimal"
        name={field.key}
        aria-labelledby={`label-${field.key}`}
        aria-invalid={invalidFields.includes(field.key) || undefined}
        min={field.min}
        max={field.max}
        step={field.step || "any"}
        value={draft[field.key] || ""}
        onChange={(event) => update(field.key, event.target.value)}
        placeholder="Unknown / not entered"
        aria-describedby={
          [
            field.help ? `help-${field.key}` : "",
            invalidFields.includes(field.key) ? `error-${field.key}` : "",
          ]
            .filter(Boolean)
            .join(" ") || undefined
        }
      />
      {field.help ? <small id={`help-${field.key}`}>{field.help}</small> : null}
      {invalidFields.includes(field.key) ? (
        <small id={`error-${field.key}`}>
          Check this value or leave it blank if unknown.
        </small>
      ) : null}
    </label>
  );
  const selectField = (
    key: keyof Home,
    label: string,
    choices: Record<string, string>,
    help?: string,
  ) => (
    <label className="form-field">
      <span id={`label-${key}`}>{label}</span>
      <select
        name={key}
        aria-labelledby={`label-${key}`}
        aria-invalid={invalidFields.includes(key) || undefined}
        aria-describedby={
          [
            help ? `help-${key}` : "",
            invalidFields.includes(key) ? `error-${key}` : "",
          ]
            .filter(Boolean)
            .join(" ") || undefined
        }
        value={draft[key] || ""}
        onChange={(event) => update(key, event.target.value)}
      >
        <option value="">Unknown</option>
        {Object.entries(choices).map(([value, text]) => (
          <option value={value} key={value}>
            {text}
          </option>
        ))}
      </select>
      {help ? <small id={`help-${key}`}>{help}</small> : null}
      {invalidFields.includes(key) ? (
        <small id={`error-${key}`}>Choose a supported value or Unknown.</small>
      ) : null}
    </label>
  );
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    setError(null);
    setInvalidFields([]);
    const form = event.currentTarget;
    if (!form.reportValidity()) return;
    if (guided && step < 3) {
      if (step === 1 && !checkNoGas()) return;
      goStep(step + 1);
      return;
    }
    if (blockedAnnualBaseline) return;
    if (!checkNoGas()) return;
    if (
      requiresPostCompletionConfirmation &&
      draft.electricity_kwh?.trim() &&
      draft.gas_kwh?.trim() &&
      !confirmedAfterCompletion
    ) {
      setError(
        "Confirm that both annual fuel readings describe the home after its completed work.",
      );
      requestAnimationFrame(() => errorRef.current?.focus());
      return;
    }
    const candidate: Home = {
      ...home,
      data_kind:
        workspaceBaseline || fictional ? "synthetic_demo" : "user_entered",
    };
    const numericKeys = [...propertyNumbers, ...assumptions];
    for (const field of numericKeys) {
      const raw = draft[field.key]?.trim() || "";
      if (!raw && assumptions.includes(field)) {
        delete candidate[field.key];
        continue;
      }
      const value = raw ? Number(raw) : null;
      if (
        value !== null &&
        (!Number.isFinite(value) ||
          (field.min !== undefined && value < field.min) ||
          (field.max !== undefined && value > field.max))
      ) {
        setMode("full");
        setInvalidFields([field.key]);
        setError(
          `Check ${field.label.toLowerCase()} or leave it blank if unknown.`,
        );
        requestAnimationFrame(() => errorRef.current?.focus());
        return;
      }
      Object.assign(candidate, { [field.key]: value });
    }
    for (const key of [
      "property_type",
      "region",
      "epc_rating",
      "heating",
      "insulation",
      "glazing",
    ] as const) {
      Object.assign(candidate, { [key]: draft[key] || null });
    }
    candidate.age_band = draft.age_band ? Number(draft.age_band) : null;
    for (const field of booleanFields)
      Object.assign(candidate, {
        [field.key]:
          draft[field.key] === "" || draft[field.key] === undefined
            ? null
            : draft[field.key] === "true",
      });
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    const requestedKey = homeKey;
    setSaving(true);
    try {
      await api.assess(candidate, [], controller.signal);
      if (!controller.signal.aborted && latestKey.current === requestedKey)
        onSave(candidate, confirmedAfterCompletion);
    } catch (cause) {
      if (!controller.signal.aborted) {
        setError(errorMessage(cause));
        const fields = cause instanceof ApiError ? cause.fields : [];
        if (fields.length) setMode("full");
        setInvalidFields(fields);
        requestAnimationFrame(() => {
          const field = fields.length
            ? form.elements.namedItem(fields[0])
            : null;
          if (field instanceof HTMLElement) field.focus();
          else errorRef.current?.focus();
        });
      }
    } finally {
      if (!controller.signal.aborted) setSaving(false);
    }
  }
  function checkNoGas() {
    if (
      draft.gas_kwh?.trim() &&
      Number(draft.gas_kwh) === 0 &&
      !noGasConfirmed
    ) {
      setError(
        "Confirm no gas was used in this 12-month period, or leave gas blank if unknown.",
      );
      if (guided) goStep(1);
      requestAnimationFrame(() => errorRef.current?.focus());
      return false;
    }
    return true;
  }
  const show = (section: number) => !guided || step === section;
  const display = (key: keyof Home) =>
    draft[key] === "true"
      ? "Yes"
      : draft[key] === "false"
        ? "No"
        : draft[key] || "Unknown";
  return (
    <form
      className="home-form"
      ref={formRef}
      onSubmit={submit}
      noValidate
      aria-label="Home intake"
    >
      <Notice>
        <ShieldCheck size={16} aria-hidden="true" />
        <span>
          Start with what you know. Blank means unknown, never zero. Use no
          names, addresses or other personal information.
        </span>
      </Notice>
      <div className="intake-mode">
        <p>
          {guided
            ? "Three short sections, then review. Unknown answers are welcome."
            : "All home details in one editor."}
        </p>
        <Button
          disabled={saving}
          onClick={() => {
            setMode(guided ? "full" : "guided");
            requestAnimationFrame(() => stepHeading.current?.focus());
          }}
        >
          {guided ? "Use full editor" : "Use guided intake"}
        </Button>
      </div>
      {guided ? (
        <>
          <ol className="intake-steps" aria-label="Intake progress">
            {steps.map((label, i) => (
              <li key={label} aria-current={step === i ? "step" : undefined}>
                <span aria-hidden="true">{i + 1}</span>
                {label}
              </li>
            ))}
          </ol>
          <h2 ref={stepHeading} tabIndex={-1} className="intake-heading">
            {step + 1}. {steps[step]}
          </h2>
        </>
      ) : null}
      {error ? (
        <div ref={errorRef} tabIndex={-1}>
          <Notice kind="error">
            {error} Your previous home remains unchanged.
          </Notice>
        </div>
      ) : null}
      <fieldset disabled={saving || !show(0)} hidden={!show(0)}>
        <legend>The property</legend>
        <div className="form-grid">
          {selectField(
            "property_type",
            "Property type",
            Object.fromEntries(
              [
                "Detached",
                "Semi detached",
                "Mid terrace",
                "End terrace",
                "Bungalow",
                "Flat",
              ].map((v) => [v, v]),
            ),
          )}
          {selectField("region", "Region · England & Wales", REGIONS)}
          {selectField(
            "epc_rating",
            "Recorded EPC rating",
            Object.fromEntries(
              ["A", "A/B", "B", "C", "D", "E", "F", "G"].map((v) => [v, v]),
            ),
            "Find the letter on your Energy Performance Certificate (EPC). If you do not have it, choose Unknown; do not estimate it.",
          )}
          {selectField("age_band", "When was it built?", {
            "1": "Before 1930",
            "2": "1930–1972",
            "3": "1973–1999",
            "4": "2000 or later",
          })}
          {propertyNumbers
            .filter(
              (field) =>
                ["floor_area_m2", "budget_gbp"].includes(field.key) ||
                (!guided && field.key === "current_value_gbp"),
            )
            .map(numberField)}
        </div>
        <p className="fine-print">
          Construction periods follow the verified NEED age-band definitions.
          The app does not infer a new EPC rating after improvements.
        </p>
      </fieldset>
      <fieldset disabled={saving || !show(1)} hidden={!show(1)}>
        <legend>Your energy use</legend>
        <p>
          Use the same 12 months for both fuels. No bills to hand? Leave the
          readings blank and continue.
        </p>
        <div className="form-grid">
          {propertyNumbers
            .filter((field) =>
              ["electricity_kwh", "gas_kwh"].includes(field.key),
            )
            .map(numberField)}
        </div>
        <label className="check-row no-gas-check">
          <input
            type="checkbox"
            name="no_gas_confirmed"
            checked={noGasConfirmed}
            onChange={(e) => {
              setNoGasConfirmed(e.target.checked);
              setConfirmedAfterCompletion(false);
              setEnergyPeriod(null);
              setCsvFuelStarts((previous) => ({ ...previous, gas_kwh: null }));
              setDraft((previous) => ({
                ...previous,
                gas_kwh: e.target.checked ? "0" : "",
              }));
            }}
          />
          <span>
            I confirm no gas was used in this 12-month period{" "}
            <small>
              Sets annual gas to 0. Electric heating alone does not confirm zero
              gas use.
            </small>
          </span>
        </label>
        <MonthlyEnergyInput
          key={homeKey}
          disabled={saving || !show(1)}
          baselineAfterDate={baselineAfterDate}
          onDirtyChange={setCsvDirty}
          onApply={(preview) => {
            setDraft((previous) => ({
              ...previous,
              electricity_kwh:
                preview.electricity_kwh === null
                  ? ""
                  : String(preview.electricity_kwh),
              gas_kwh: preview.gas_kwh === null ? "" : String(preview.gas_kwh),
            }));
            setNoGasConfirmed(false);
            setConfirmedAfterCompletion(false);
            setEnergyPeriod(
              `${preview.period.start_month} to ${preview.period.end_month}`,
            );
            setCsvFuelStarts({
              electricity_kwh:
                preview.electricity_kwh === null
                  ? null
                  : preview.period.start_month,
              gas_kwh:
                preview.gas_kwh === null ? null : preview.period.start_month,
            });
          }}
        />
        {energyPeriod ? (
          <p className="fine-print">
            Applied monthly period: {energyPeriod}. This is not confirmation of
            a fresh post-work baseline.
          </p>
        ) : null}
      </fieldset>
      <fieldset disabled={saving || !show(2)} hidden={!show(2)}>
        <legend>Existing features</legend>
        <div className="form-grid">
          {selectField("heating", "Main heating system", HEATING)}
          {selectField("insulation", "Insulation condition", {
            poor: "Poor",
            partial: "Partial",
            good: "Good",
          })}
          {selectField("glazing", "Window glazing", {
            single: "Single",
            double: "Double",
            triple: "Triple",
          })}
          {propertyNumbers
            .filter((field) => field.key === "solar_kwp")
            .map(numberField)}
          {booleanFields.map((field) => (
            <div key={field.key}>
              {selectField(
                field.key,
                field.label,
                {
                  true: "Yes",
                  false: "No",
                },
                field.key === "roof_access" || field.key === "consent_confirmed"
                  ? "Choose Yes only if the relevant access or permission is confirmed. Unknown does not count as permission."
                  : field.key === "heat_pump_ready"
                    ? "An installer must have checked suitability; this is not inferred from your heating type."
                    : undefined,
              )}
            </div>
          ))}
        </div>
      </fieldset>
      {guided && step === 3 ? (
        <section className="intake-review" aria-label="Review home details">
          <p>
            Check what you entered. Unknowns stay unknown and may limit
            estimates; nothing here is a survey or valuation.
          </p>
          <dl className="intake-totals">
            <div>
              <dt>Property type</dt>
              <dd>{display("property_type")}</dd>
            </div>
            <div>
              <dt>Region</dt>
              <dd>{REGIONS[draft.region] || "Unknown"}</dd>
            </div>
            <div>
              <dt>Floor area · m²</dt>
              <dd>{display("floor_area_m2")}</dd>
            </div>
            <div>
              <dt>Recorded EPC</dt>
              <dd>{display("epc_rating")}</dd>
            </div>
            <div>
              <dt>Construction period</dt>
              <dd>
                {(
                  {
                    "1": "Before 1930",
                    "2": "1930–1972",
                    "3": "1973–1999",
                    "4": "2000 or later",
                  } as Record<string, string>
                )[draft.age_band] || "Unknown"}
              </dd>
            </div>
            <div>
              <dt>Active-plan installation budget · £</dt>
              <dd>{display("budget_gbp")}</dd>
            </div>
            <div>
              <dt>Annual grid electricity · kWh</dt>
              <dd>{display("electricity_kwh")}</dd>
            </div>
            <div>
              <dt>Annual gas · kWh</dt>
              <dd>
                {display("gas_kwh")}
                {noGasConfirmed ? " — no gas confirmed" : ""}
              </dd>
            </div>
            <div>
              <dt>Heating</dt>
              <dd>{HEATING[draft.heating] || "Unknown"}</dd>
            </div>
            <div>
              <dt>Insulation</dt>
              <dd>{display("insulation")}</dd>
            </div>
            <div>
              <dt>Window glazing</dt>
              <dd>{display("glazing")}</dd>
            </div>
            <div>
              <dt>Existing solar · kWp</dt>
              <dd>{display("solar_kwp")}</dd>
            </div>
            {booleanFields.map((field) => (
              <div key={field.key}>
                <dt>{field.label}</dt>
                <dd>{display(field.key)}</dd>
              </div>
            ))}
          </dl>
          {energyPeriod ? <p>Monthly data period: {energyPeriod}.</p> : null}
          <div className="form-actions">
            {steps.slice(0, 3).map((label, i) => (
              <Button key={label} onClick={() => goStep(i)}>
                Edit {label.toLowerCase()}
              </Button>
            ))}
          </div>
        </section>
      ) : null}
      <details className="assumption-form" hidden={guided && step !== 3}>
        <summary>Review calculation assumptions</summary>
        <p>
          Leave blank to use the engine’s disclosed defaults. Change a default
          only when you have better information.
        </p>
        <fieldset disabled={saving || (guided && step !== 3)}>
          <div className="form-grid">{assumptions.map(numberField)}</div>
          <p>
            Home value is optional and not needed for energy screening. Any
            value illustration is synthetic, not a market valuation.
          </p>
          {guided
            ? propertyNumbers
                .filter((field) => field.key === "current_value_gbp")
                .map(numberField)
            : null}
        </fieldset>
      </details>
      {requiresPostCompletionConfirmation && (!guided || step === 3) ? (
        <Notice kind="warning">
          <p>
            Completed work changed this home. Do not copy its old bills into the
            new baseline.
          </p>
          {preCompletionPeriod ? (
            <p role="alert">
              This period includes time before completed work; cannot confirm a
              post-work annual baseline. Use a full annual period starting after{" "}
              {baselineAfterDate?.slice(0, 7)}, or replace the affected
              CSV-derived annual readings manually.
            </p>
          ) : null}
          <p>
            Manual readings and your post-work confirmation are not
            independently verified. Confirm a full year after this property’s
            latest completed work
            {baselineAfterDate ? ` (${baselineAfterDate})` : ""}; do not reuse
            pre-work bills.
          </p>
          <label className="check-row">
            <input
              type="checkbox"
              checked={confirmedAfterCompletion}
              required={Boolean(
                draft.electricity_kwh?.trim() && draft.gas_kwh?.trim(),
              )}
              disabled={
                saving ||
                preCompletionPeriod ||
                !draft.electricity_kwh?.trim() ||
                !draft.gas_kwh?.trim()
              }
              onChange={(e) => setConfirmedAfterCompletion(e.target.checked)}
            />
            <span>
              I confirm these annual electricity and gas readings describe the
              home after its completed work.
            </span>
          </label>
          <p>
            Enter both fuel readings to confirm a replacement baseline. Enter
            zero only if confirmed.
          </p>
        </Notice>
      ) : null}
      <div hidden={guided && step !== 3}>
        {workspaceBaseline ? (
          <Notice>
            This is a saved fictional household. Keep all edits fictional; real
            home details belong in temporary own-home screening.
          </Notice>
        ) : (
          <div className="fictional-choice">
            <label className="check-row">
              <input
                type="checkbox"
                name="fictional_scenario"
                checked={fictional}
                disabled={saving}
                onChange={(event) => setFictional(event.target.checked)}
              />
              <span>
                <strong>
                  These edits are a fictional scenario, not a real property
                </strong>
                <small>
                  Leave unchecked for actual home inputs. Only explicitly
                  fictional scenarios can receive a synthetic value
                  illustration.
                </small>
              </span>
            </label>
          </div>
        )}
      </div>
      <div className="form-actions">
        {guided && step > 0 ? (
          <Button disabled={saving} onClick={() => goStep(step - 1)}>
            Back
          </Button>
        ) : null}
        <Button
          type="submit"
          variant="primary"
          disabled={
            saving || (blockedAnnualBaseline && (!guided || step === 3))
          }
        >
          {saving ? (
            "Validating home…"
          ) : guided && step < 3 ? (
            `Continue to ${steps[step + 1].toLowerCase()}`
          ) : (
            <>
              <Check size={16} aria-hidden="true" />
              {workspaceBaseline
                ? "Apply home edits & reset plan"
                : "Save home & reset plan"}
            </>
          )}
        </Button>
        {onCancel ? (
          <Button
            onClick={() => {
              onCancel();
            }}
          >
            Cancel
          </Button>
        ) : null}
      </div>
      <p className="fine-print" hidden={guided && step !== 3}>
        Saving clears both packages and previous explanations so nothing is
        carried over from incompatible home details.
        {workspaceBaseline
          ? " Then choose Save property changes in Saved workspace to keep these edits after reload."
          : " In temporary mode, this applies only to the current page session."}
      </p>
    </form>
  );
}
