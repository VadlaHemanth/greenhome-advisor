import { useRef, useState } from "react";
import { ApiError, request } from "./api";
import type {
  MoneyPlanResponse,
  MoneyTariffDraft,
  MoneyTariffErrors,
  MoneyTariffField,
  MoneyTariffs,
} from "./moneyTypes";
import { parseMoneyTariffs, validMoneyPlan } from "./moneyValidation";
import type { Home, RetrofitId } from "./types";
import { useResource } from "./useResource";
import type { Resource } from "./useResource";

/** One temporary controller, owned above Dashboard and Costs & packages. */
export type MoneyController = {
  home: Home | null;
  selected: RetrofitId[];
  draft: MoneyTariffDraft;
  errors: MoneyTariffErrors;
  confirmed: MoneyTariffs | null;
  result: Resource<MoneyPlanResponse>;
  edit: (field: MoneyTariffField, value: string) => void;
  /** Returns validation errors so the submitting form can focus its own input. */
  calculate: () => MoneyTariffErrors;
  useIllustration: () => void;
};

type TariffState = {
  identity: string;
  draft: MoneyTariffDraft;
  errors: MoneyTariffErrors;
  confirmed: { tariffs: MoneyTariffs; revision: number } | null;
};

function emptyState(identity: string): TariffState {
  return {
    identity,
    draft: {
      electricity_pence: "",
      gas_pence: "",
      as_of: "",
      source: "user_entered",
    },
    errors: {},
    confirmed: null,
  };
}

export function useMoneyPlan(
  home: Home | null,
  selected: RetrofitId[],
  scope: string,
): MoneyController {
  // An unidentified home is still distinct from having no active home.
  const identity = JSON.stringify([
    scope,
    home !== null,
    home?.property_id ?? null,
  ]);
  const [state, setState] = useState(() => emptyState(identity));
  const revision = useRef(0);
  // Reset in this render, not an effect: neither children nor the request
  // loader may observe a previous home's confirmed rates, even for one frame.
  const current = state.identity === identity ? state : emptyState(identity);
  if (state.identity !== identity) setState(current);

  const body =
    home && current.confirmed
      ? {
          home,
          selected_retrofits: selected,
          tariffs: current.confirmed.tariffs,
        }
      : null;
  // Include all home facts, selection, scope and confirmation revision.
  // A same-input retry is new work; home input edits reuse confirmed rates.
  const key = body
    ? JSON.stringify([identity, body, current.confirmed?.revision])
    : null;
  const result = useResource<MoneyPlanResponse>(key, async (signal) => {
    const data = await request<MoneyPlanResponse>("/money-plan", body, signal);
    if (!validMoneyPlan(data))
      throw new ApiError(
        "The service returned an incomplete money response. Please calculate again.",
        502,
        "invalid_response",
      );
    if (
      !body ||
      (Object.keys(body.tariffs) as (keyof MoneyTariffs)[]).some(
        (field) => data.tariffs[field] !== body.tariffs[field],
      )
    )
      throw new ApiError(
        "The service returned different rates or provenance. Please calculate again.",
        502,
        "invalid_response",
      );
    return data;
  });

  function edit(field: MoneyTariffField, value: string) {
    if (!home) return;
    setState((previous) => {
      // Ignore handlers retained by a page that belongs to an old scope.
      if (previous.identity !== identity) return previous;
      return {
        ...previous,
        draft: { ...previous.draft, [field]: value, source: "user_entered" },
        errors: {},
        confirmed: null,
      };
    });
  }

  function confirm(draft: MoneyTariffDraft): MoneyTariffErrors {
    if (!home) return {};
    const parsed = parseMoneyTariffs(draft);
    const confirmed = parsed.tariffs
      ? { tariffs: parsed.tariffs, revision: ++revision.current }
      : null;
    setState((previous) =>
      previous.identity === identity
        ? { ...previous, draft, errors: parsed.errors, confirmed }
        : previous,
    );
    return parsed.errors;
  }

  function useIllustration() {
    // An explicit illustration is not a dated quote or a current tariff.
    confirm({
      electricity_pence: "25",
      gas_pence: "7",
      as_of: "",
      source: "illustrative",
    });
  }

  return {
    home,
    selected,
    draft: current.draft,
    errors: current.errors,
    confirmed: current.confirmed?.tariffs ?? null,
    result,
    edit,
    calculate: () => confirm(current.draft),
    useIllustration,
  };
}
