import { describe, expect, it, vi } from "vitest";
import { api, request } from "../api";
import { validApiPayload } from "../apiValidation";
import { home } from "./fixtures";
import { ranking, workspace } from "./workspaceFixtures";

function respond(payload: unknown, status = 200) {
  vi.mocked(fetch).mockResolvedValue(
    new Response(JSON.stringify(payload), { status }),
  );
}
describe("workspace and ranking HTTP contract", () => {
  it("restores a nullable session without creating or requesting private data anonymously", async () => {
    respond(null);
    expect(await api.workspace()).toBeNull();
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/workspace/session");
    respond(workspace);
    expect(await api.workspace()).toEqual(workspace);
    expect(validApiPayload("/workspace/session", { unexpected: true })).toBe(
      false,
    );
  });
  it("sends versioned household data, exclusions and explicit completion-baseline confirmation", async () => {
    respond(workspace);
    const c = workspace.customers[0];
    const update = {
      version: 1,
      home: { ...c.home, excluded_retrofits: ["solar_pv"] as const },
      preferences: {
        ...c.preferences,
        deferred_retrofits: ["solar_pv"] as const,
      },
      selected_retrofits: [],
      review_status: "reviewing" as const,
      baseline_confirmed_after_completion: true,
    };
    await api.saveCustomer(c.id, {
      ...update,
      home: { ...update.home, excluded_retrofits: ["solar_pv"] },
      preferences: { ...update.preferences, deferred_retrofits: ["solar_pv"] },
    });
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe(
      "/api/workspace/customers/customer-1",
    );
    expect(
      JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string),
    ).toEqual(update);
  });
  it.each(["example.ngrok-free.app", "example.ngrok.io"])(
    "uses only same-origin cookies and ngrok guard for workspace %s",
    async (hostname) => {
      vi.stubGlobal("location", { hostname });
      respond(workspace);
      await api.createWorkspace();
      const options = vi.mocked(fetch).mock.calls[0][1]!;
      expect(options.credentials).toBe("same-origin");
      expect(options.cache).toBe("no-store");
      expect(options.headers).toMatchObject({
        "ngrok-skip-browser-warning": "1",
      });
      expect(JSON.parse(options.body as string)).toEqual({ consent: true });
      expect(options.headers).not.toHaveProperty("Authorization");
    },
  );
  it("requires the explicit completion event shape", async () => {
    respond(workspace);
    const event = {
      version: 1,
      kind: "completed" as const,
      retrofit_id: "loft_insulation" as const,
      completed_on: "2026-10-10",
      confirmed: true as const,
    };
    await api.completeRetrofit("customer-1", event);
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe(
      "/api/workspace/customers/customer-1/events",
    );
    expect(
      JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string),
    ).toEqual(event);
  });
  it("exports by authenticated GET and deletes by confirmed POST", async () => {
    respond(workspace);
    await api.exportWorkspace();
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/workspace/export");
    expect(vi.mocked(fetch).mock.calls[0][1]?.method).toBe("GET");
    respond({ deleted: true });
    await api.deleteWorkspace();
    expect(vi.mocked(fetch).mock.calls[1][0]).toBe("/api/workspace/delete");
    expect(
      JSON.parse(vi.mocked(fetch).mock.calls[1][1]!.body as string),
    ).toEqual({ confirm: true });
  });
  it.each([401, 409])(
    "returns safe recovery for HTTP %i without server prose",
    async (status) => {
      respond(
        {
          detail: {
            code: "workspace_required",
            message: "private SQL failure",
          },
        },
        status,
      );
      await expect(api.workspace()).rejects.toMatchObject({ status });
    },
  );
  it("preserves signed ranking results, missing cases and tied ranks", async () => {
    respond(ranking);
    expect(await api.rankHomes(workspace.customers.map((c) => c.home))).toEqual(
      ranking,
    );
    expect(
      JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string),
    ).toEqual({ homes: workspace.customers.map((c) => c.home) });
  });
  it("rejects more than 100 homes before any request", async () => {
    await expect(api.rankHomes(Array(101).fill(home))).rejects.toMatchObject({
      code: "too_many_homes",
    });
    expect(fetch).not.toHaveBeenCalled();
  });
  it("rejects a ranking that omits a requested home", async () => {
    respond({ ...ranking, rows: ranking.rows.slice(1) });
    await expect(
      api.rankHomes(workspace.customers.map((c) => c.home)),
    ).rejects.toMatchObject({ code: "invalid_response" });
  });
  it("allowlists field names without echoing validation messages", async () => {
    respond(
      {
        detail: {
          errors: [
            { loc: ["body", "home", "gas_kwh"], msg: "private value" },
            { loc: ["secret_debug"], msg: "secret" },
          ],
        },
      },
      422,
    );
    await expect(request("/assess")).rejects.toMatchObject({
      fields: ["gas_kwh"],
    });
  });
});

describe("new response schemas", () => {
  it("accepts workspace read/write/export and complete ranking fixtures", () => {
    for (const path of [
      "/workspace",
      "/workspace/export",
      "/workspace/customers/customer-1",
      "/workspace/customers/customer-1/events",
    ])
      expect(validApiPayload(path, workspace)).toBe(true);
    expect(validApiPayload("/rank-homes", ranking)).toBe(true);
    expect(validApiPayload("/workspace/delete", { deleted: true })).toBe(true);
  });
  it.each([
    ["mode", "real_bank"],
    ["expires_at", "not-a-date"],
    ["customers", {}],
    ["note", null],
  ])("rejects malformed workspace %s", (key, value) => {
    expect(validApiPayload("/workspace", { ...workspace, [key]: value })).toBe(
      false,
    );
  });
  it.each([
    { version: 0 },
    { version: 1.1 },
    { review_status: "approved_by_bank" },
    { baseline_status: "guessed" },
    { selected_retrofits: ["solar_pv", "solar_pv"] },
    { selected_retrofits: ["battery"] },
    {
      preferences: {
        budget_gbp: Infinity,
        deferred_retrofits: [],
        priority: "energy",
        disruption: "flexible",
      },
    },
    { home: { ...home, data_kind: "user_entered" } },
    { home: { ...home, electricity_kwh: "4800" } },
    { events: [{ kind: "free_text", text: "arbitrary note" }] },
  ])("rejects malformed customer %j", (patch) => {
    expect(
      validApiPayload("/workspace", {
        ...workspace,
        customers: [{ ...workspace.customers[0], ...patch }],
      }),
    ).toBe(false);
  });
  it("rejects duplicate household IDs and property references", () => {
    expect(
      validApiPayload("/workspace", {
        ...workspace,
        customers: [workspace.customers[0], workspace.customers[0]],
      }),
    ).toBe(false);
  });
  it.each([
    { improvement_percent: Infinity },
    { rank: -1 },
    { rank: null },
    { status: "guessed" },
    { status: "insufficient_evidence", improvement_percent: 0, rank: null },
    { electricity_saving_kwh: "negative" },
    { selected_retrofits: ["boiler"] },
    { baseline_kwh: 0 },
  ])("rejects malformed ranking row %j", (patch) => {
    expect(
      validApiPayload("/rank-homes", {
        ...ranking,
        rows: [{ ...ranking.rows[0], ...patch }],
      }),
    ).toBe(false);
  });
});
