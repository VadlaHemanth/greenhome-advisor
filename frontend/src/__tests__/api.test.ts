import { describe, expect, it, vi } from "vitest";
import { api, ApiError, downloadJson, request } from "../api";
import { assessment, catalogue, health, home, reply } from "./fixtures";

function respond(payload: unknown, status = 200) {
  vi.mocked(fetch).mockImplementation(
    async () =>
      new Response(JSON.stringify(payload), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
  );
}

describe("same-origin API client", () => {
  it.each([
    "example.ngrok-free.dev",
    "example.ngrok-free.app",
    "example.ngrok.app",
    "example.ngrok.dev",
    "example.ngrok.io",
  ])("gets JSON through ngrok browser interstitial on %s", async (hostname) => {
    vi.stubGlobal("location", { hostname });
    vi.mocked(fetch).mockImplementation(async (_url, options) =>
      new Headers(options?.headers).get("ngrok-skip-browser-warning") === "1"
        ? new Response(JSON.stringify(health), {
            headers: { "Content-Type": "application/json" },
          })
        : new Response("You are about to visit this ngrok endpoint.", {
            headers: { "Content-Type": "text/plain" },
          }),
    );
    await expect(api.health()).resolves.toEqual(health);
    expect(vi.mocked(fetch).mock.calls[0][1]?.credentials).toBe("same-origin");
  });

  it("adds the ngrok flag to POSTs without changing the JSON or auth policy", async () => {
    vi.stubGlobal("location", { hostname: "example.ngrok-free.dev" });
    respond(assessment);
    await api.assess(home, ["heat_pump"]);
    const options = vi.mocked(fetch).mock.calls[0][1]!;
    expect(options.headers).toEqual({
      Accept: "application/json",
      "Content-Type": "application/json",
      "ngrok-skip-browser-warning": "1",
    });
    expect(JSON.parse(options.body as string).selected_retrofits).toEqual([
      "heat_pump",
    ]);
    expect(options.credentials).toBe("same-origin");
  });

  it.each([
    "localhost",
    "127.0.0.1",
    "greenhome.example",
    "example.ngrok-free.dev.attacker.example",
    "notngrok-free.dev",
  ])("leaves ordinary hosts unchanged on %s", async (hostname) => {
    vi.stubGlobal("location", { hostname });
    respond(health);
    await api.health();
    expect(vi.mocked(fetch).mock.calls[0][1]?.headers).not.toHaveProperty(
      "ngrok-skip-browser-warning",
    );
  });

  it("uses same-origin gateway credentials without embedding provider configuration", async () => {
    respond(assessment);
    const result = await api.assess(home, ["heat_pump"]);
    expect(result.scenario.electricity_saving_kwh).toBe(-2720);
    const [url, options] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/assess");
    expect(options).toMatchObject({
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
    });
    expect(JSON.parse(options!.body as string)).toEqual({
      home,
      selected_retrofits: ["heat_pump"],
    });
    expect(options!.headers).not.toHaveProperty("Authorization");
  });

  it.each([
    ["/health", health],
    ["/demo-homes", [home]],
    ["/catalogue", catalogue],
    ["/metrics", { status: "unavailable", metrics: null }],
  ])("loads %s without creating a POST body", async (path, payload) => {
    respond(payload);
    expect(await request(path)).toEqual(payload);
    expect(vi.mocked(fetch).mock.calls[0][1]).toMatchObject({
      method: "GET",
      body: undefined,
    });
  });

  it("preserves null as automatic selection and [] as no changes", async () => {
    respond(assessment);
    await api.assess(home, null);
    expect(
      JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string)
        .selected_retrofits,
    ).toBeNull();
    await api.assess(home, []);
    expect(
      JSON.parse(vi.mocked(fetch).mock.calls[1][1]!.body as string)
        .selected_retrofits,
    ).toEqual([]);
  });

  it("sends local what-if mode explicitly", async () => {
    respond(reply);
    await api.whatIf(home, ["heat_pump"], "Explain my score", false);
    expect(
      JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string).use_gemini,
    ).toBe(false);
  });

  it("keeps comparison packages independent", async () => {
    respond({ package_a: assessment, package_b: assessment });
    await api.compare(home, ["heat_pump"], ["loft_insulation"]);
    expect(
      JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string),
    ).toEqual({
      home,
      package_a: ["heat_pump"],
      package_b: ["loft_insulation"],
    });
  });

  it.each([400, 413, 422, 429, 500])(
    "sanitises error details for HTTP %i",
    async (status) => {
      respond(
        {
          detail: {
            code: "invalid_scenario",
            message: "secret-provider-debug-key",
          },
        },
        status,
      );
      const result = await request("/assess").catch((error) => error);
      expect(result).toBeInstanceOf(ApiError);
      if (!(result instanceof ApiError))
        throw new Error("Expected safe API error");
      expect(result.status).toBe(status);
      expect(result.message).not.toContain("secret-provider-debug-key");
    },
  );

  it("returns a useful unavailable-service message for planned endpoints", async () => {
    respond({ detail: "Not Found" }, 404);
    await expect(api.decision(home)).rejects.toThrow(
      "not available on the running API",
    );
  });

  it("does not echo connection exception details", async () => {
    vi.mocked(fetch).mockRejectedValue(
      new Error("sensitive URL or debug data"),
    );
    await expect(request("/health")).rejects.toThrow("Cannot connect");
  });

  it.each([null, false, "not an object", 123])(
    "rejects an invalid JSON root %s",
    async (payload) => {
      respond(payload);
      await expect(request("/health")).rejects.toMatchObject({
        code: "invalid_response",
      });
    },
  );

  it("rejects a malformed assessment instead of allowing component crashes", async () => {
    respond({ score: 99 });
    await expect(api.assess(home, [])).rejects.toMatchObject({
      code: "invalid_response",
    });
  });

  it("rejects HTML with status 200 as an invalid response, not fabricated data", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response("<html>proxy fallback</html>", { status: 200 }),
    );
    await expect(request("/health")).rejects.toMatchObject({
      code: "invalid_response",
    });
  });

  it("cancels on caller abort without retrying", async () => {
    const parent = new AbortController();
    vi.mocked(fetch).mockImplementation(
      (_url, options) =>
        new Promise((_resolve, reject) => {
          options?.signal?.addEventListener("abort", () =>
            reject(new DOMException("cancelled", "AbortError")),
          );
        }),
    );
    const pending = request("/health", undefined, parent.signal);
    parent.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("rejects responses that arrive after cancellation even when fetch ignores abort", async () => {
    const parent = new AbortController();
    respond(health);
    const pending = request("/health", undefined, parent.signal);
    parent.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });

  it("aborts after the request deadline", async () => {
    vi.useFakeTimers();
    vi.mocked(fetch).mockImplementation(
      (_url, options) =>
        new Promise((_resolve, reject) => {
          options?.signal?.addEventListener("abort", () =>
            reject(new DOMException("timeout", "AbortError")),
          );
        }),
    );
    const pending = request("/health", undefined, undefined, 20);
    const assertion = expect(pending).rejects.toMatchObject({
      status: 408,
      code: "timeout",
    });
    await vi.advanceTimersByTimeAsync(20);
    await assertion;
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("downloads the supplied object without making a network request", () => {
    vi.useFakeTimers();
    const create = vi.fn(() => "blob:test-json");
    const revoke = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: create,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: revoke,
    });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    downloadJson("assessment.json", assessment);
    expect(create).toHaveBeenCalledWith(expect.any(Blob));
    expect(click).toHaveBeenCalledTimes(1);
    expect(document.querySelector("a[download]")).toBeNull();
    vi.advanceTimersByTime(1000);
    expect(revoke).toHaveBeenCalledWith("blob:test-json");
    expect(fetch).not.toHaveBeenCalled();
  });
});
