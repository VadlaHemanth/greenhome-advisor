import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useResource } from "../useResource";
import { deferred } from "./fixtures";

describe("resource request freshness", () => {
  it("does not request when the key is null", () => {
    const load = vi.fn(async () => "never");
    const { result } = renderHook(() => useResource(null, load));
    expect(load).not.toHaveBeenCalled();
    expect(result.current).toEqual({
      key: null,
      data: null,
      loading: false,
      error: null,
    });
  });

  it("clears old data immediately when its key changes and aborts its request", async () => {
    const requests = [deferred<string>(), deferred<string>()];
    const signals: AbortSignal[] = [];
    const load = vi.fn((signal: AbortSignal) => {
      signals.push(signal);
      return requests[signals.length - 1].promise;
    });
    const { result, rerender } = renderHook(({ id }) => useResource(id, load), {
      initialProps: { id: "A" },
    });
    await act(async () => {
      requests[0].resolve("home A");
    });
    expect(result.current.data).toBe("home A");
    rerender({ id: "B" });
    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(true);
    expect(signals[0].aborted).toBe(true);
    await act(async () => {
      requests[1].resolve("home B");
    });
    expect(result.current.data).toBe("home B");
  });

  it("ignores a stale out-of-order response from a non-cooperative loader", async () => {
    const a = deferred<string>(),
      b = deferred<string>();
    const load = vi
      .fn()
      .mockReturnValueOnce(a.promise)
      .mockReturnValueOnce(b.promise);
    const { result, rerender } = renderHook(({ id }) => useResource(id, load), {
      initialProps: { id: "A" },
    });
    rerender({ id: "B" });
    await act(async () => {
      b.resolve("new home");
    });
    await act(async () => {
      a.resolve("stale home");
    });
    expect(result.current.data).toBe("new home");
  });

  it("does not retain a prior result after the new request fails", async () => {
    const load = vi
      .fn()
      .mockResolvedValueOnce("old data")
      .mockRejectedValueOnce(new Error("validation rejected"));
    const { result, rerender } = renderHook(({ id }) => useResource(id, load), {
      initialProps: { id: "A" },
    });
    await waitFor(() => expect(result.current.data).toBe("old data"));
    rerender({ id: "B" });
    await waitFor(() =>
      expect(result.current.error).toBe("validation rejected"),
    );
    expect(result.current.data).toBeNull();
  });

  it("aborts on unmount", () => {
    let requested: AbortSignal | undefined;
    const load = (signal: AbortSignal) => {
      requested = signal;
      return new Promise<string>(() => {});
    };
    const { unmount } = renderHook(() => useResource("A", load));
    unmount();
    expect(requested?.aborted).toBe(true);
  });

  it("does not refetch merely because the callback identity changed", async () => {
    const first = vi.fn(async () => "value");
    const second = vi.fn(async () => "different");
    const { result, rerender } = renderHook(
      ({ load }) => useResource("stable", load),
      { initialProps: { load: first } },
    );
    await waitFor(() => expect(result.current.data).toBe("value"));
    rerender({ load: second });
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).not.toHaveBeenCalled();
  });

  it("reports synchronous loader errors instead of crashing the component", async () => {
    const { result } = renderHook(() =>
      useResource("A", () => {
        throw new Error("sync error");
      }),
    );
    await waitFor(() => expect(result.current.error).toBe("sync error"));
    expect(result.current.loading).toBe(false);
  });
});
