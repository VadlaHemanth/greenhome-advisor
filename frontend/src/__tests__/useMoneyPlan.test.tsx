import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api";
import type { MoneyPlanResponse, MoneyTariffField } from "../moneyTypes";
import type { Home, RetrofitId } from "../types";
import { useMoneyPlan } from "../useMoneyPlan";
import { deferred } from "./fixtures";
import {
  illustrativeTariffs,
  moneyHome,
  moneyResponse,
  moneySelected,
  negativeMoney,
  partialMoney,
  unchangedMoney,
  zeroMoney,
} from "./moneyFixtures";

const initial: { home: Home | null; selected: RetrofitId[]; scope: string } = {
  home: moneyHome,
  selected: moneySelected,
  scope: "workspace-a:customer-a",
};
const mount = () =>
  renderHook(
    ({ home, selected, scope }) => useMoneyPlan(home, selected, scope),
    {
      initialProps: initial,
    },
  );

beforeEach(() => {
  vi.spyOn(api, "request").mockResolvedValue(moneyResponse());
});

describe("shared money controller", () => {
  it("starts unconfirmed without implicitly choosing tariffs or making a request", () => {
    const { result } = mount();
    expect(result.current.draft).toEqual({
      electricity_pence: "",
      gas_pence: "",
      as_of: "",
      source: "user_entered",
    });
    expect(result.current.confirmed).toBeNull();
    expect(result.current.result).toMatchObject({
      data: null,
      loading: false,
      error: null,
    });
    expect(api.request).not.toHaveBeenCalled();
  });

  it("uses the complete request and retains the server's signed values", async () => {
    const { result, rerender } = mount();
    act(() => result.current.useIllustration());
    await waitFor(() => expect(result.current.result.data).not.toBeNull());
    expect(result.current.confirmed).toEqual(illustrativeTariffs);
    expect(result.current.result.data?.money.total).toEqual({
      before_gbp: 2040,
      after_gbp: 1946,
      saving_gbp: 94,
    });
    expect(api.request).toHaveBeenCalledExactlyOnceWith(
      "/money-plan",
      {
        home: moneyHome,
        selected_retrofits: moneySelected,
        tariffs: illustrativeTariffs,
      },
      expect.any(AbortSignal),
    );
    rerender({
      ...initial,
      home: { ...moneyHome },
      selected: [...moneySelected],
    });
    expect(api.request).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["home ID", { home: { ...moneyHome, property_id: "DEMO02" } }],
    ["same home ID in another workspace", { scope: "workspace-b:customer-a" }],
    ["same home ID for another customer", { scope: "workspace-a:customer-b" }],
    ["null home", { home: null }],
  ] as [string, Partial<typeof initial>][])(
    "immediately resets rates/results on %s, including every render",
    async (_name, patch) => {
      const frames: {
        scope: string;
        id: Home["property_id"] | undefined;
        draft: string;
        data: MoneyPlanResponse | null;
      }[] = [];
      const { result, rerender } = renderHook(
        (props) => {
          const controller = useMoneyPlan(
            props.home,
            props.selected,
            props.scope,
          );
          frames.push({
            scope: props.scope,
            id: props.home?.property_id,
            draft: controller.draft.electricity_pence,
            data: controller.result.data,
          });
          return controller;
        },
        { initialProps: initial },
      );
      act(() => result.current.useIllustration());
      await waitFor(() => expect(result.current.result.data).not.toBeNull());
      frames.length = 0;
      rerender({ ...initial, ...patch });
      expect(
        frames.every((frame) => frame.data === null && frame.draft === ""),
      ).toBe(true);
      expect(result.current.confirmed).toBeNull();
      expect(result.current.errors).toEqual({});
      expect(result.current.result.loading).toBe(false);
      expect(result.current.result.error).toBeNull();
      expect(api.request).toHaveBeenCalledTimes(1);
      rerender(initial);
      expect(result.current.draft.electricity_pence).toBe("");
      expect(result.current.result.data).toBeNull();
      expect(api.request).toHaveBeenCalledTimes(1);
    },
  );

  it("clears old source, date and field errors in a new scope", () => {
    const { result, rerender } = mount();
    act(() => result.current.edit("as_of", "2026-10-16"));
    act(() => result.current.edit("gas_pence", "-1"));
    act(() => result.current.calculate());
    expect(result.current.errors.gas_pence).toBeTruthy();
    rerender({ ...initial, scope: "new-workspace" });
    expect(result.current.errors).toEqual({});
    expect(result.current.draft).toEqual({
      electricity_pence: "",
      gas_pence: "",
      as_of: "",
      source: "user_entered",
    });
  });

  it.each([
    ["annual input", { electricity_kwh: 6000 }],
    ["missing reading", { gas_kwh: null }],
    ["budget", { budget_gbp: 0 }],
    ["permission", { consent_confirmed: true }],
    ["exclusion", { excluded_retrofits: ["solar_pv"] }],
    ["physical facts", { floor_area_m2: 120 }],
    ["calculation assumption", { heat_pump_spf: 4 }],
  ] as [string, Partial<Home>][])(
    "recomputes %s changes on the same ID with confirmed rates",
    async (_name, patch) => {
      const next = deferred<MoneyPlanResponse>();
      vi.mocked(api.request)
        .mockResolvedValueOnce(moneyResponse())
        .mockReturnValueOnce(next.promise);
      const { result, rerender } = mount();
      act(() => result.current.useIllustration());
      await waitFor(() => expect(result.current.result.data).not.toBeNull());
      rerender({ ...initial, home: { ...moneyHome, ...patch } });
      expect(result.current.result.data).toBeNull();
      expect(result.current.result.loading).toBe(true);
      expect(result.current.confirmed).toEqual(illustrativeTariffs);
      expect(vi.mocked(api.request).mock.calls[1][1]).toEqual({
        home: { ...moneyHome, ...patch },
        selected_retrofits: moneySelected,
        tariffs: illustrativeTariffs,
      });
    },
  );

  it("recomputes an explicit empty selection rather than retaining the old plan", async () => {
    const next = deferred<MoneyPlanResponse>();
    vi.mocked(api.request)
      .mockResolvedValueOnce(moneyResponse())
      .mockReturnValueOnce(next.promise);
    const { result, rerender } = mount();
    act(() => result.current.useIllustration());
    await waitFor(() => expect(result.current.result.data).not.toBeNull());
    rerender({ ...initial, selected: [] });
    expect(result.current.result.data).toBeNull();
    expect(vi.mocked(api.request).mock.calls[1][1]).toMatchObject({
      selected_retrofits: [],
    });
    await act(async () => next.resolve(unchangedMoney()));
    expect(result.current.selected).toEqual([]);
    expect(result.current.result.data?.money.total.saving_gbp).toBe(0);
  });

  it.each(["electricity_pence", "gas_pence", "as_of"] as MoneyTariffField[])(
    "hides results and cancels confirmation immediately on a %s edit",
    async (field) => {
      const { result } = mount();
      act(() => result.current.useIllustration());
      await waitFor(() => expect(result.current.result.data).not.toBeNull());
      act(() =>
        result.current.edit(field, field === "as_of" ? "2026-10-16" : "0"),
      );
      expect(result.current.result.data).toBeNull();
      expect(result.current.confirmed).toBeNull();
      expect(result.current.draft.source).toBe("user_entered");
      expect(api.request).toHaveBeenCalledTimes(1);
    },
  );

  it("retains valid source/date until the explicit illustration clears the date", async () => {
    const dated = moneyResponse();
    dated.tariffs.source = "user_entered";
    dated.tariffs.as_of = "2026-10-16";
    vi.mocked(api.request)
      .mockResolvedValueOnce(dated)
      .mockResolvedValueOnce(moneyResponse());
    const { result } = mount();
    act(() => result.current.edit("electricity_pence", "25"));
    act(() => result.current.edit("gas_pence", "7"));
    act(() => result.current.edit("as_of", "2026-10-16"));
    act(() => result.current.calculate());
    await waitFor(() => expect(result.current.result.data).toEqual(dated));
    expect(result.current.confirmed?.as_of).toBe("2026-10-16");
    act(() => result.current.useIllustration());
    expect(result.current.result.data).toBeNull();
    expect(result.current.draft.as_of).toBe("");
    expect(result.current.confirmed?.source).toBe("illustrative");
    await waitFor(() =>
      expect(result.current.result.data?.tariffs.as_of).toBeNull(),
    );
  });

  it.each(["-1", "201", "Infinity", "NaN", "1e309", "bad"])(
    "rejects invalid rate %s locally",
    (value) => {
      const { result } = mount();
      act(() => result.current.edit("gas_pence", value));
      let errors;
      act(() => {
        errors = result.current.calculate();
      });
      expect(errors).toEqual({
        gas_pence: expect.stringMatching(/finite rate/),
      });
      expect(result.current.confirmed).toBeNull();
      expect(result.current.result.data).toBeNull();
      expect(api.request).not.toHaveBeenCalled();
    },
  );

  it("rejects impossible dates without requesting a calculation", () => {
    const { result } = mount();
    act(() => result.current.edit("as_of", "2026-02-30"));
    act(() => result.current.calculate());
    expect(result.current.errors.as_of).toMatch(/real calendar date/);
    expect(api.request).not.toHaveBeenCalled();
  });

  it("retains explicit zero rates and zero outputs", async () => {
    vi.mocked(api.request).mockResolvedValue(zeroMoney());
    const { result } = mount();
    act(() => result.current.edit("electricity_pence", "0"));
    act(() => result.current.edit("gas_pence", "0"));
    act(() => result.current.calculate());
    await waitFor(() =>
      expect(result.current.result.data).toEqual(zeroMoney()),
    );
    expect(result.current.confirmed?.electricity_pence).toBe(0);
    expect(result.current.result.data?.money.total.saving_gbp).toBe(0);
  });

  it("does not impute unknown rates or unknown totals", async () => {
    vi.mocked(api.request).mockResolvedValue(partialMoney());
    const { result } = mount();
    act(() => result.current.edit("electricity_pence", "25"));
    act(() => result.current.calculate());
    await waitFor(() =>
      expect(result.current.result.data).toEqual(partialMoney()),
    );
    expect(result.current.confirmed?.gas_pence).toBeNull();
    expect(result.current.result.data?.money.total.saving_gbp).toBeNull();
  });

  it("retains -£8 and no payback for the heat-pump-only response", async () => {
    vi.mocked(api.request).mockResolvedValue(negativeMoney());
    const { result, rerender } = mount();
    rerender({ ...initial, selected: ["heat_pump"] });
    act(() => result.current.useIllustration());
    await waitFor(() => expect(result.current.result.data).not.toBeNull());
    expect(result.current.result.data?.money.total.saving_gbp).toBe(-8);
    expect(result.current.result.data?.money.payback_years).toBeNull();
  });

  it.each([
    ["source", "user_entered"],
    ["as_of", "2026-10-16"],
    ["gas_pence", 8],
  ] as const)(
    "rejects changed response %s rather than accepting foreign provenance",
    async (field, value) => {
      const data = moneyResponse();
      Object.assign(data.tariffs, { [field]: value });
      vi.mocked(api.request).mockResolvedValue(data);
      const { result } = mount();
      act(() => result.current.useIllustration());
      await waitFor(() =>
        expect(result.current.result.error).toMatch(
          /different rates or provenance/,
        ),
      );
      expect(result.current.result.data).toBeNull();
    },
  );

  it("fails closed on malformed data then supports a fresh same-input retry", async () => {
    vi.mocked(api.request)
      .mockResolvedValueOnce({ money: null })
      .mockResolvedValueOnce(moneyResponse());
    const { result } = mount();
    act(() => result.current.useIllustration());
    await waitFor(() =>
      expect(result.current.result.error).toMatch(/incomplete money response/),
    );
    act(() => result.current.calculate());
    expect(result.current.result.error).toBeNull();
    await waitFor(() =>
      expect(result.current.result.data).toEqual(moneyResponse()),
    );
  });

  it("does not leak an old success or failure through rapid A→B→A selections", async () => {
    const old = deferred<MoneyPlanResponse>();
    const middle = deferred<MoneyPlanResponse>();
    const latest = deferred<MoneyPlanResponse>();
    vi.mocked(api.request)
      .mockReturnValueOnce(old.promise)
      .mockReturnValueOnce(middle.promise)
      .mockReturnValueOnce(latest.promise);
    const { result, rerender } = mount();
    act(() => result.current.useIllustration());
    rerender({ ...initial, selected: ["heat_pump"] });
    rerender(initial);
    expect(vi.mocked(api.request).mock.calls[0][2]?.aborted).toBe(true);
    expect(vi.mocked(api.request).mock.calls[1][2]?.aborted).toBe(true);
    await act(async () => {
      old.resolve(negativeMoney());
      middle.reject(new Error("Old failure"));
    });
    expect(result.current.result).toMatchObject({
      data: null,
      error: null,
      loading: true,
    });
    await act(async () => latest.resolve(moneyResponse()));
    expect(result.current.result.data?.money.total.saving_gbp).toBe(94);
  });

  it("ignores late responses across scopes with an identical home ID, even on return", async () => {
    const old = deferred<MoneyPlanResponse>();
    const latest = deferred<MoneyPlanResponse>();
    vi.mocked(api.request)
      .mockReturnValueOnce(old.promise)
      .mockReturnValueOnce(latest.promise);
    const { result, rerender } = mount();
    act(() => result.current.useIllustration());
    rerender({ ...initial, scope: "workspace-b" });
    rerender(initial);
    expect(result.current.confirmed).toBeNull();
    expect(result.current.draft.electricity_pence).toBe("");
    act(() => result.current.useIllustration());
    await act(async () => latest.resolve(moneyResponse()));
    await act(async () => old.resolve(negativeMoney()));
    expect(result.current.result.data?.money.total.saving_gbp).toBe(94);
  });

  it("aborts pending work on edits and unmount, without accepting late failures", async () => {
    const old = deferred<MoneyPlanResponse>();
    const next = deferred<MoneyPlanResponse>();
    vi.mocked(api.request)
      .mockReturnValueOnce(old.promise)
      .mockReturnValueOnce(next.promise);
    const { result, unmount } = mount();
    act(() => result.current.useIllustration());
    act(() => result.current.edit("gas_pence", ""));
    expect(vi.mocked(api.request).mock.calls[0][2]?.aborted).toBe(true);
    await act(async () => old.reject(new Error("Old error")));
    expect(result.current.result).toMatchObject({
      data: null,
      error: null,
      loading: false,
    });
    act(() => result.current.useIllustration());
    unmount();
    expect(vi.mocked(api.request).mock.calls[1][2]?.aborted).toBe(true);
    await act(async () => next.resolve(moneyResponse()));
  });

  it("leaves null home inert and does not transfer attempted tariffs into the next home", () => {
    const { result, rerender } = mount();
    rerender({ ...initial, home: null });
    act(() => result.current.useIllustration());
    act(() => result.current.calculate());
    expect(result.current.confirmed).toBeNull();
    expect(result.current.result.data).toBeNull();
    expect(api.request).not.toHaveBeenCalled();
    rerender(initial);
    expect(result.current.draft.electricity_pence).toBe("");
  });

  it("resets when a home with a null property ID is cleared", async () => {
    const { result, rerender } = mount();
    const unidentified = {
      ...initial,
      home: { ...moneyHome, property_id: null },
    };
    rerender(unidentified);
    act(() => result.current.useIllustration());
    await waitFor(() => expect(result.current.result.data).not.toBeNull());
    rerender({ ...initial, home: null });
    expect(result.current.confirmed).toBeNull();
    expect(result.current.draft.electricity_pence).toBe("");
    expect(result.current.result.data).toBeNull();
    rerender(unidentified);
    expect(result.current.confirmed).toBeNull();
    expect(result.current.draft.electricity_pence).toBe("");
    expect(api.request).toHaveBeenCalledTimes(1);
  });

  it("clears service errors on scope change without implicitly retrying", async () => {
    vi.mocked(api.request).mockRejectedValueOnce(
      new api.ApiError("Calculation unavailable.", 503, "unavailable"),
    );
    const { result, rerender } = mount();
    act(() => result.current.useIllustration());
    await waitFor(() =>
      expect(result.current.result.error).toMatch(/unavailable/),
    );
    rerender({ ...initial, scope: "new-workspace" });
    expect(result.current.result.error).toBeNull();
    expect(result.current.result.data).toBeNull();
    expect(result.current.confirmed).toBeNull();
    expect(api.request).toHaveBeenCalledTimes(1);
  });
});
