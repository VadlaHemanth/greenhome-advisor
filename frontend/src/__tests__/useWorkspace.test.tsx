import { act, renderHook, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { api, ApiError } from "../api";
import { useWorkspace } from "../useWorkspace";
import { deferred } from "./fixtures";
import { workspace } from "./workspaceFixtures";

it("treats no workspace as temporary, with no implicit creation", async () => {
  const create = vi.spyOn(api, "createWorkspace");
  vi.spyOn(api, "workspace").mockRejectedValue(
    new ApiError("Missing", 401, "workspace_required"),
  );
  const { result } = renderHook(useWorkspace);
  await waitFor(() => expect(result.current.busy).toBeNull());
  expect(result.current.data).toBeNull();
  expect(result.current.error).toBeNull();
  expect(create).not.toHaveBeenCalled();
});
it("aborts an older restore and ignores a response that arrives after a newer restore", async () => {
  const late = deferred<typeof workspace>();
  const get = vi
    .spyOn(api, "workspace")
    .mockReturnValueOnce(late.promise)
    .mockResolvedValueOnce(workspace);
  const { result } = renderHook(useWorkspace);
  await act(async () => result.current.restore());
  expect(get.mock.calls[0][0]?.aborted).toBe(true);
  await act(async () => late.resolve({ ...workspace, id: "stale" }));
  expect(result.current.data?.id).toBe(workspace.id);
});
it("keeps failed save recovery explicit without replacing the last saved version", async () => {
  vi.spyOn(api, "workspace").mockResolvedValue(workspace);
  const { result } = renderHook(useWorkspace);
  await waitFor(() => expect(result.current.data).toEqual(workspace));
  await act(async () => {
    await result.current.mutate(
      "Saving",
      async () => {
        throw new ApiError("Conflict", 409, "stale_version");
      },
      "Saved",
    );
  });
  expect(result.current.conflict).toBe(true);
  expect(result.current.error).toBe("Conflict");
  expect(result.current.data).toEqual(workspace);
});
it("exports the saved authenticated response rather than draft or browser storage", async () => {
  vi.spyOn(api, "workspace").mockResolvedValue(workspace);
  const exportCall = vi
    .spyOn(api, "exportWorkspace")
    .mockResolvedValue(workspace);
  const create = vi.fn(() => "blob:workspace-test");
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: create,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: vi.fn(),
  });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const { result } = renderHook(useWorkspace);
  await waitFor(() => expect(result.current.busy).toBeNull());
  await act(async () => result.current.exportData());
  expect(exportCall).toHaveBeenCalledWith(expect.any(AbortSignal));
  expect(create).toHaveBeenCalledWith(expect.any(Blob));
  expect(result.current.message).toContain("Unsaved edits are not included");
});
