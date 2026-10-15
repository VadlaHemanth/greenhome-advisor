import type {
  Assessment,
  CatalogueItem,
  Comparison,
  Decision,
  Health,
  Home,
  Metrics,
  Reply,
  RetrofitId,
  HomeRanking,
  Workspace,
  CustomerUpdate,
  CompletionInput,
  EnergyInputs,
  CanonicalWorkspace,
  PropertyUpdate,
  PropertyCompletionInput,
  CustomerSettingsUpdate,
  DemoTemplateId,
} from "./types";
import { validApiPayload } from "./apiValidation";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
    public fields: string[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function request<T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
  timeoutMs = 30_000,
): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener("abort", abort, { once: true });
  if (signal?.aborted) controller.abort();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  // ngrok's free browser interstitial otherwise replaces API JSON with a
  // warning page. This public flag is not an auth token or a credential.
  if (
    /\.(?:ngrok-free\.(?:app|dev)|ngrok\.(?:app|dev|io))$/i.test(
      globalThis.location?.hostname || "",
    )
  ) {
    headers["ngrok-skip-browser-warning"] = "1";
  }
  try {
    const response = await fetch(`/api${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
      // Send only this site's browser-managed gateway authentication. Provider
      // secrets are never present in the frontend or in request headers here.
      credentials: "same-origin",
      cache: "no-store",
    });
    if (controller.signal.aborted)
      throw new DOMException("Request cancelled", "AbortError");
    if (!response.ok) {
      let code = "";
      let fields: string[] = [];
      try {
        const detail = (await response.json())?.detail;
        const candidate = detail?.code;
        if (typeof candidate === "string" && /^[a-z_]{1,64}$/.test(candidate))
          code = candidate;
        const errors = Array.isArray(detail) ? detail : detail?.errors;
        const allowed = [
          "floor_area_m2",
          "electricity_kwh",
          "gas_kwh",
          "solar_kwp",
          "current_value_gbp",
          "budget_gbp",
          "age_band",
          "region",
          "epc_rating",
          "heating",
          "insulation",
          "glazing",
          "property_type",
        ];
        if (Array.isArray(errors))
          fields = [
            ...new Set(
              errors.flatMap((e: { loc?: unknown[] }) =>
                Array.isArray(e?.loc)
                  ? e.loc.filter(
                      (key): key is string =>
                        typeof key === "string" && allowed.includes(key),
                    )
                  : [],
              ),
            ),
          ];
      } catch {
        /* Do not expose proxy HTML or provider errors. */
      }
      const message =
        response.status === 401
          ? "This private workspace is missing or has expired. Your current changes have not been saved."
          : response.status === 409
            ? code.includes("budget")
              ? "The shared budget cannot cover this change and existing reservations. Your draft is unchanged. Review the saved customer allocation before retrying."
              : code.includes("exclu") || code.includes("defer")
                ? "These customer-wide exclusions conflict with a saved property plan. No plans were removed; your draft is unchanged. Review the affected property plans first."
                : code.includes("legacy") || code.includes("reserve")
                  ? "Historical planning costs need an explicitly confirmed aggregate reserve before a shared cap can be set. Your draft is unchanged."
                  : "This customer or property changed, or the saved plan conflicts with this request. Reload the saved workspace before trying again; your draft has not been overwritten."
            : response.status === 422
              ? "The engine could not accept this home or package. Check the home details, feasibility and combined budget; then try again."
              : response.status === 404
                ? "This service is not available on the running API yet. You can retry when it is ready."
                : response.status === 429
                  ? "Too many requests in a short time. Wait a minute, then retry. No previous result is being used."
                  : response.status === 503
                    ? "The service is busy. Try again shortly; no new result is available."
                    : response.status === 403
                      ? "This request is not permitted from the current page. Ask the operator to check access settings."
                      : "The calculation service is unavailable. Please retry; no previous result is being used.";
      throw new ApiError(message, response.status, code, fields);
    }
    let result: unknown;
    try {
      result = await response.json();
    } catch {
      throw new ApiError(
        "The service returned an unreadable response. Please retry.",
        502,
        "invalid_response",
      );
    }
    if (controller.signal.aborted)
      throw new DOMException("Request cancelled", "AbortError");
    if (!validApiPayload(path, result))
      throw new ApiError(
        "The service returned an incomplete response. Please retry.",
        502,
        "invalid_response",
      );
    return result as T;
  } catch (error) {
    if (timedOut)
      throw new ApiError(
        "The request timed out. Retry when the calculation service is ready.",
        408,
        "timeout",
      );
    if (signal?.aborted)
      throw new DOMException("Request cancelled", "AbortError");
    if (error instanceof ApiError) throw error;
    throw new ApiError(
      "Cannot connect to the calculation service. Check your connection and retry.",
      0,
      "connection",
    );
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}

export const api = {
  health: (signal?: AbortSignal) =>
    request<Health>("/health", undefined, signal),
  homes: (signal?: AbortSignal) =>
    request<Home[]>("/demo-homes", undefined, signal),
  catalogue: (signal?: AbortSignal) =>
    request<CatalogueItem[]>("/catalogue", undefined, signal),
  energyInputs: async (
    csv_text: string,
    end_month: string,
    signal?: AbortSignal,
  ) => {
    const result = await request<EnergyInputs>(
      "/energy-inputs",
      { csv_text, end_month },
      signal,
    );
    if (result.period.end_month !== end_month)
      throw new ApiError(
        "The service returned a different monthly period. Please preview again.",
        502,
        "invalid_response",
      );
    return result;
  },
  metrics: (signal?: AbortSignal) =>
    request<Metrics>("/metrics", undefined, signal),
  assess: (
    home: Home,
    selected_retrofits: RetrofitId[] | null,
    signal?: AbortSignal,
  ) => request<Assessment>("/assess", { home, selected_retrofits }, signal),
  compare: (
    home: Home,
    package_a: RetrofitId[],
    package_b: RetrofitId[],
    signal?: AbortSignal,
  ) => request<Comparison>("/compare", { home, package_a, package_b }, signal),
  whatIf: (
    home: Home,
    selected_retrofits: RetrofitId[],
    question: string,
    use_gemini: boolean,
    signal?: AbortSignal,
  ) =>
    request<Reply>(
      "/what-if",
      { home, selected_retrofits, question, use_gemini },
      signal,
    ),
  decision: (home: Home, signal?: AbortSignal) =>
    request<Decision>("/decision-check", { home }, signal),
  rankHomes: async (homes: Home[], signal?: AbortSignal) => {
    if (homes.length > 100)
      throw new ApiError(
        "Rank up to 100 homes at a time.",
        422,
        "too_many_homes",
      );
    const result = await request<HomeRanking>("/rank-homes", { homes }, signal);
    const expected = new Set(homes.map((h) => h.property_id));
    if (
      result.rows.length !== homes.length ||
      result.rows.some((r) => !expected.has(r.property_id))
    )
      throw new ApiError(
        "The service returned an incomplete home ranking. Please retry.",
        502,
        "invalid_response",
      );
    return result;
  },
  workspace: (signal?: AbortSignal) =>
    request<Workspace | null>("/workspace/session", undefined, signal),
  createWorkspace: (signal?: AbortSignal) =>
    request<Workspace>("/workspace", { consent: true }, signal),
  deleteWorkspace: (signal?: AbortSignal) =>
    request<{ deleted?: boolean; status?: string }>(
      "/workspace/delete",
      { confirm: true },
      signal,
    ),
  exportWorkspace: (signal?: AbortSignal) =>
    request<Workspace>("/workspace/export", undefined, signal),
  saveCustomer: (id: string, update: CustomerUpdate, signal?: AbortSignal) =>
    request<Workspace>(
      `/workspace/customers/${encodeURIComponent(id)}`,
      update,
      signal,
    ),
  completeRetrofit: (
    id: string,
    event: CompletionInput,
    signal?: AbortSignal,
  ) =>
    request<Workspace>(
      `/workspace/customers/${encodeURIComponent(id)}/events`,
      event,
      signal,
    ),
  property: (customerId: string, propertyId: string, signal?: AbortSignal) =>
    scopedWorkspace(
      propertyPath(customerId, propertyId),
      customerId,
      propertyId,
      undefined,
      signal,
    ),
  addProperty: (
    customerId: string,
    body: { customer_version: number; template_id: DemoTemplateId },
    signal?: AbortSignal,
  ) =>
    scopedWorkspace(
      `/workspace/customers/${encodeURIComponent(customerId)}/properties`,
      customerId,
      undefined,
      body,
      signal,
    ),
  saveProperty: (
    customerId: string,
    propertyId: string,
    update: PropertyUpdate,
    signal?: AbortSignal,
  ) =>
    scopedWorkspace(
      propertyPath(customerId, propertyId),
      customerId,
      propertyId,
      update,
      signal,
    ),
  completeProperty: (
    customerId: string,
    propertyId: string,
    event: PropertyCompletionInput,
    signal?: AbortSignal,
  ) =>
    scopedWorkspace(
      `${propertyPath(customerId, propertyId)}/events`,
      customerId,
      propertyId,
      event,
      signal,
    ),
  saveCustomerSettings: (
    customerId: string,
    update: CustomerSettingsUpdate,
    signal?: AbortSignal,
  ) =>
    scopedWorkspace(
      `/workspace/customers/${encodeURIComponent(customerId)}/settings`,
      customerId,
      undefined,
      update,
      signal,
    ),
};

function propertyPath(customerId: string, propertyId: string) {
  return `/workspace/customers/${encodeURIComponent(customerId)}/properties/${encodeURIComponent(propertyId)}`;
}
async function scopedWorkspace(
  path: string,
  customerId: string,
  propertyId?: string,
  body?: unknown,
  signal?: AbortSignal,
) {
  const result = await request<CanonicalWorkspace>(path, body, signal);
  const customer = result.customers.find((c) => c.id === customerId);
  if (
    !customer ||
    (propertyId && !customer.properties.some((p) => p.id === propertyId))
  )
    throw new ApiError(
      "The response did not match this customer and property. Your draft has not been replaced.",
      502,
      "invalid_response",
    );
  return result;
}
export function errorMessage(error: unknown) {
  return error instanceof Error
    ? error.message
    : "The request could not be completed. Please retry.";
}
export function downloadJson(filename: string, data: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
