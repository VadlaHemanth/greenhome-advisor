import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, downloadJson, errorMessage } from "./api";
import type { Workspace } from "./types";

/** No browser storage or client-side identity: the HttpOnly cookie is managed by the API. */
export function useWorkspace() {
  const [data, setData] = useState<Workspace | null>(null);
  const [busy, setBusy] = useState<string | null>("Restoring saved workspace…");
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [message, setMessage] = useState("");
  const pending = useRef<AbortController | null>(null);
  const restore = useCallback(async () => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setBusy("Restoring saved workspace…");
    setError(null);
    setConflict(false);
    try {
      const next = await api.workspace(controller.signal);
      if (!controller.signal.aborted) {
        setData(next);
        setMessage(
          next
            ? "Saved fictional workspace restored."
            : "Temporary mode. Nothing is saved.",
        );
        return next;
      }
    } catch (cause) {
      if (!controller.signal.aborted) {
        if (cause instanceof ApiError && cause.status === 401) {
          setData(null);
          setMessage("Temporary mode. Nothing is saved.");
          return null;
        } else setError(errorMessage(cause));
      }
    } finally {
      if (pending.current === controller) {
        pending.current = null;
        if (!controller.signal.aborted) setBusy(null);
      }
    }
  }, []);
  useEffect(() => {
    void restore();
    return () => {
      pending.current?.abort();
    };
  }, [restore]);
  async function mutate(
    label: string,
    operation: (signal: AbortSignal) => Promise<Workspace | null>,
    success: string,
  ) {
    // Synchronous guard prevents double writes before React commits the disabled state.
    if (pending.current) return undefined;
    const controller = new AbortController();
    pending.current = controller;
    setBusy(label);
    setError(null);
    setConflict(false);
    try {
      const next = await operation(controller.signal);
      if (controller.signal.aborted) return undefined;
      setData(next);
      setMessage(success);
      return next;
    } catch (cause) {
      if (!controller.signal.aborted) {
        setError(errorMessage(cause));
        setConflict(
          cause instanceof ApiError &&
            (cause.status === 409 || cause.status === 401),
        );
      }
      return undefined;
    } finally {
      if (pending.current === controller) {
        pending.current = null;
        if (!controller.signal.aborted) setBusy(null);
      }
    }
  }
  async function exportData() {
    if (pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    setBusy("Preparing saved workspace export…");
    setError(null);
    try {
      const result = await api.exportWorkspace(controller.signal);
      if (!controller.signal.aborted) {
        downloadJson("greenhome-fictional-workspace.json", result);
        setMessage("Saved workspace exported. Unsaved edits are not included.");
      }
    } catch (cause) {
      if (!controller.signal.aborted) setError(errorMessage(cause));
    } finally {
      if (pending.current === controller) {
        pending.current = null;
        if (!controller.signal.aborted) setBusy(null);
      }
    }
  }
  const clearIssue = () => {
    setError(null);
    setConflict(false);
  };
  return {
    data,
    busy,
    error,
    conflict,
    message,
    restore,
    mutate,
    exportData,
    clearIssue,
  };
}
