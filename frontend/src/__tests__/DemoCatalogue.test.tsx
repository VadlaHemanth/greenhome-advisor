import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { expect, it, vi } from "vitest";
import * as catalogueApi from "../demoCatalogue";
import { DemoCatalogue } from "../DemoCatalogue";
import { catalogueFixture } from "./demoCatalogueFixtures";
import { deferred } from "./fixtures";

vi.mock("../HomeComparison", () => ({
  HomeThumbnail: () => <svg role="img" aria-label="Illustrative home" />,
}));

it("shows a bounded page and opens exactly the chosen fictional home", async () => {
  const data = catalogueFixture();
  const load = vi
    .spyOn(catalogueApi, "loadDemoCatalogue")
    .mockResolvedValue(data);
  const open = vi.fn();
  render(<DemoCatalogue onOpen={open} />);
  await screen.findByRole("heading", { name: "Fictional home 1" });
  expect(screen.getAllByRole("article")).toHaveLength(12);
  expect(screen.getByText("200 fictional homes")).toBeTruthy();
  fireEvent.click(
    screen.getByRole("button", { name: "Explore Fictional home 4" }),
  );
  expect(open).toHaveBeenCalledWith(data.entries[3].home);
  expect(load.mock.calls[0][0]).toMatchObject({
    page: 1,
    q: "",
    property_type: "",
  });
});

it("navigates to server pages without renumbering global ranks", async () => {
  const load = vi
    .spyOn(catalogueApi, "loadDemoCatalogue")
    .mockResolvedValueOnce(catalogueFixture())
    .mockResolvedValue(catalogueFixture(2));
  render(<DemoCatalogue onOpen={vi.fn()} />);
  await screen.findByRole("heading", { name: "Fictional home 1" });
  fireEvent.click(screen.getByRole("button", { name: "Next page" }));
  await screen.findByRole("heading", { name: "Fictional home 13" });
  expect(screen.getByText("Global rank 13")).toBeTruthy();
  expect(
    screen.queryByRole("heading", { name: "Fictional home 1" }),
  ).toBeNull();
  expect(load.mock.lastCall?.[0].page).toBe(2);
});

it("applies filters explicitly and returns to page one", async () => {
  const load = vi
    .spyOn(catalogueApi, "loadDemoCatalogue")
    .mockResolvedValue(catalogueFixture());
  render(<DemoCatalogue onOpen={vi.fn()} />);
  await screen.findByRole("heading", { name: "Fictional home 1" });
  fireEvent.change(screen.getByRole("searchbox"), {
    target: { value: "CAT-012" },
  });
  fireEvent.change(screen.getByLabelText("Building type"), {
    target: { value: "Flat" },
  });
  expect(load).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Find examples" }));
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
  expect(load.mock.lastCall?.[0]).toMatchObject({
    q: "CAT-012",
    property_type: "Flat",
    page: 1,
  });
});

it("clears stale cards and keeps errors distinct from an empty catalogue", async () => {
  const late = deferred<catalogueApi.DemoCataloguePage>();
  vi.spyOn(catalogueApi, "loadDemoCatalogue")
    .mockResolvedValueOnce(catalogueFixture())
    .mockReturnValueOnce(late.promise)
    .mockRejectedValueOnce(new Error("Unavailable right now"));
  render(<DemoCatalogue onOpen={vi.fn()} />);
  await screen.findByRole("heading", { name: "Fictional home 1" });
  fireEvent.click(screen.getByRole("button", { name: "Next page" }));
  expect(screen.queryByRole("article")).toBeNull();
  fireEvent.change(screen.getByRole("searchbox"), {
    target: { value: "new search" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Find examples" }));
  await screen.findByRole("alert");
  await act(async () => late.resolve(catalogueFixture(2)));
  expect(screen.queryByRole("article")).toBeNull();
  expect(screen.queryByText(/0 fictional homes/)).toBeNull();
  expect(screen.getByRole("button", { name: "Retry catalogue" })).toBeTruthy();
});

it("labels the public examples separately when a private workspace exists", async () => {
  vi.spyOn(catalogueApi, "loadDemoCatalogue").mockResolvedValue({
    ...catalogueFixture(),
    filtered_total: 0,
    entries: [],
    page_count: 0,
    summary: { assessed: 0, evidence_needed: 0, flagged: 0 },
  });
  render(<DemoCatalogue onOpen={vi.fn()} hasSavedWorkspace />);
  await screen.findByText("No examples match these filters.");
  expect(screen.getByText(/Your saved workspace stays separate/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Next page" })).toBeNull();
});
