import { describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { validApiPayload } from "../apiValidation";
import {
  propertyContext,
  propertyHome,
  workspaceView,
} from "../workspaceModel";
import { multiWorkspace } from "./multiPropertyFixtures";
import { workspace as legacy } from "./workspaceFixtures";
import type { PropertyUpdate } from "../types";

describe("canonical customer → properties JSON", () => {
  it.each([1, 2, 4, 8])(
    "accepts %i properties without deprecated root fields",
    (count) => {
      const workspace = multiWorkspace([count, 1, 1, 1]);
      expect(validApiPayload("/workspace/session", workspace)).toBe(true);
      for (const suffix of [
        "properties",
        "settings",
        "properties/property-1",
        "properties/property-1/events",
      ])
        expect(
          validApiPayload(
            `/workspace/customers/customer-1/${suffix}`,
            workspace,
          ),
        ).toBe(true);
      expect(workspaceView(workspace).customers[0]).not.toHaveProperty("home");
    },
  );
  it("ignores contradictory deprecated projections in v2 rather than promoting them", () => {
    const workspace = multiWorkspace([2, 1, 1, 1]);
    Object.assign(workspace.customers[0], legacy.customers[0], {
      id: "customer-1",
    });
    expect(validApiPayload("/workspace/session", workspace)).toBe(true);
    expect(
      workspaceView(workspace).customers[0].properties[1].home.property_id,
    ).toBe("HOME-customer-1-2");
  });
  it("adapts a strict legacy fixture to exactly one property without promoting its budget/exclusions", () => {
    const input = structuredClone(legacy);
    input.customers[0].preferences.budget_gbp = 3210;
    input.customers[0].preferences.deferred_retrofits = ["heat_pump"];
    const customer = workspaceView(input).customers[0];
    expect(customer.properties).toHaveLength(1);
    expect(customer.properties[0].preferences.budget_gbp).toBe(3210);
    expect(customer.portfolio_budget_gbp).toBeNull();
    expect(customer.customer_preferences.deferred_retrofits).toEqual([]);
    expect(
      validApiPayload("/workspace/customers/customer-1/properties", input),
    ).toBe(false);
  });
  it.each([
    [
      "wrong owner",
      (w: ReturnType<typeof multiWorkspace>) => {
        w.customers[0].properties[0].customer_id = "customer-2";
      },
    ],
    [
      "duplicate resource",
      (w: ReturnType<typeof multiWorkspace>) => {
        w.customers[1].properties[0].id = w.customers[0].properties[0].id;
      },
    ],
    [
      "duplicate home",
      (w: ReturnType<typeof multiWorkspace>) => {
        w.customers[1].properties[0].home.property_id =
          w.customers[0].properties[0].home.property_id;
      },
    ],
    [
      "fractional version",
      (w: ReturnType<typeof multiWorkspace>) => {
        w.customers[0].properties[0].version = 1.2;
      },
    ],
    [
      "negative reservation",
      (w: ReturnType<typeof multiWorkspace>) => {
        w.customers[0].budget_summary.completed_reserved_gbp = -1;
      },
    ],
    [
      "unknown priority",
      (w: ReturnType<typeof multiWorkspace>) => {
        Object.assign(w.customers[0].customer_preferences, {
          priority: "profit",
        });
      },
    ],
    [
      "missing canonical properties",
      (w: ReturnType<typeof multiWorkspace>) => {
        Object.assign(w.customers[0], {
          properties: undefined,
          ...legacy.customers[0],
        });
      },
    ],
    [
      "empty properties",
      (w: ReturnType<typeof multiWorkspace>) => {
        w.customers[0].properties = [];
      },
    ],
    [
      "invalid event cost",
      (w: ReturnType<typeof multiWorkspace>) => {
        w.customers[0].properties[0].events = [
          {
            id: "event",
            kind: "completed",
            retrofit_id: "loft_insulation",
            completed_on: "2026-10-10",
            created_at: "2026-10-11T00:00:00Z",
            planning_cost_upper_gbp: Infinity,
          },
        ];
      },
    ],
  ])("rejects %s", (_, corrupt) => {
    const workspace = multiWorkspace();
    corrupt(workspace);
    expect(validApiPayload("/workspace", workspace)).toBe(false);
  });
  it("rejects more than eight properties and unsupported schema versions", () => {
    expect(validApiPayload("/workspace", multiWorkspace([9]))).toBe(false);
    expect(
      validApiPayload("/workspace", { ...legacy, schema_version: 3 }),
    ).toBe(false);
    expect(
      validApiPayload("/workspace", { ...legacy, schema_version: 2 }),
    ).toBe(false);
  });
  it("unions exclusions but never ranks against the shared cap", () => {
    const workspace = multiWorkspace([2]);
    const customer = workspace.customers[0];
    customer.customer_preferences.deferred_retrofits = [
      "solar_pv",
      "heat_pump",
    ];
    customer.portfolio_budget_gbp = 500000;
    const property = customer.properties[0];
    property.preferences.deferred_retrofits = ["solar_pv", "smart_controls"];
    expect(propertyHome(customer, property)).toMatchObject({
      budget_gbp: 5000,
      excluded_retrofits: ["solar_pv", "smart_controls", "heat_pump"],
    });
    expect(property.preferences.deferred_retrofits).toEqual([
      "solar_pv",
      "smart_controls",
    ]);
    const key = propertyContext(workspace, customer, property);
    for (const next of [
      propertyContext(
        { ...workspace, id: "new-workspace" },
        customer,
        property,
      ),
      propertyContext(workspace, { ...customer, version: 2 }, property),
      propertyContext(workspace, customer, { ...property, version: 2 }),
      propertyContext(workspace, customer, customer.properties[1]),
    ])
      expect(next).not.toBe(key);
  });
});

describe("new scoped HTTP client (mock transport, no provider)", () => {
  const workspace = multiWorkspace([2]);
  const customer = workspace.customers[0],
    property = customer.properties[1];
  const update: PropertyUpdate = {
    customer_version: customer.version,
    version: property.version,
    home: property.home,
    preferences: property.preferences,
    selected_retrofits: [],
    review_status: "reviewing",
    baseline_confirmed_after_completion: false,
  };
  it("uses the exact nested endpoint and both versions for saves, reads, completion and customer settings", async () => {
    const fetcher = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify(workspace)));
    const request = () =>
      fetcher.mockResolvedValueOnce(new Response(JSON.stringify(workspace)));
    await api.saveProperty(customer.id, property.id, update);
    expect(fetcher).toHaveBeenLastCalledWith(
      `/api/workspace/customers/${customer.id}/properties/${property.id}`,
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        body: JSON.stringify(update),
      }),
    );
    request();
    await api.property(customer.id, property.id);
    expect(fetcher).toHaveBeenLastCalledWith(
      `/api/workspace/customers/${customer.id}/properties/${property.id}`,
      expect.objectContaining({ method: "GET" }),
    );
    const event = {
      customer_version: 1,
      version: 1,
      kind: "completed" as const,
      retrofit_id: "loft_insulation" as const,
      completed_on: "2026-10-10",
      confirmed: true as const,
    };
    request();
    await api.completeProperty(customer.id, property.id, event);
    expect(fetcher).toHaveBeenLastCalledWith(
      `/api/workspace/customers/${customer.id}/properties/${property.id}/events`,
      expect.objectContaining({ body: JSON.stringify(event) }),
    );
    request();
    await api.addProperty(customer.id, {
      customer_version: 1,
      template_id: "DEMO-02",
    });
    expect(fetcher).toHaveBeenLastCalledWith(
      `/api/workspace/customers/${customer.id}/properties`,
      expect.objectContaining({
        body: '{"customer_version":1,"template_id":"DEMO-02"}',
      }),
    );
    request();
    await api.saveCustomerSettings(customer.id, {
      version: 1,
      customer_preferences: customer.customer_preferences,
      portfolio_budget_gbp: null,
      legacy_completed_reserve_gbp: 0,
      confirm_legacy_reserve: false,
    });
    expect(fetcher.mock.calls.at(-1)?.[0]).toBe(
      `/api/workspace/customers/${customer.id}/settings`,
    );
  });
  it("rejects a nominally successful response without the requested ownership", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(workspace)),
    );
    await expect(
      api.property("wrong-customer", property.id),
    ).rejects.toMatchObject({ code: "invalid_response" });
  });
  it("rejects legacy JSON at a v2 endpoint instead of silently falling back", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(legacy)),
    );
    await expect(
      api.saveProperty(customer.id, property.id, update),
    ).rejects.toMatchObject({ code: "invalid_response" });
  });
});
