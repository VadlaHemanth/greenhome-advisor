import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { Homes } from "../Homes";
import { api } from "../api";
import { ranking, workspace } from "./workspaceFixtures";
import { deferred } from "./fixtures";

it("keeps missing evidence separate, preserves zero opportunity and displays server ties", async () => {
  vi.spyOn(api, "rankHomes").mockResolvedValue(ranking);
  render(
    <Homes homes={[]} customers={workspace.customers} openHome={vi.fn()} />,
  );
  const assessed = await screen.findByRole("region", {
    name: /Assessed opportunity/,
  });
  expect(within(assessed).getAllByLabelText("Rank 1")).toHaveLength(2);
  expect(within(assessed).getByText("0.00%")).toBeTruthy();
  const evidence = screen.getByRole("region", {
    name: /Evidence needed or outside scope/,
  });
  expect(
    within(evidence).getByText("Example household 4 / DEMO-04"),
  ).toBeTruthy();
  expect(within(evidence).queryByText("0.00%")).toBeNull();
  expect(screen.getAllByText("-2,720 kWh/year")).toHaveLength(3);
});
it("passes saved budgets and exclusions for every home, not the active home's plan", async () => {
  const customers = structuredClone(workspace.customers);
  customers[0].preferences.budget_gbp = 5000;
  customers[0].preferences.deferred_retrofits = ["heat_pump"];
  const call = vi.spyOn(api, "rankHomes").mockResolvedValue(ranking);
  render(<Homes homes={[]} customers={customers} openHome={vi.fn()} />);
  await screen.findByText("Example household 1 / DEMO-01");
  expect(call.mock.calls[0][0]).toHaveLength(4);
  expect(call.mock.calls[0][0][0]).toMatchObject({
    budget_gbp: 5000,
    excluded_retrofits: ["heat_pump"],
  });
});
it("filters without recomputing or renumbering server ranks and opens the correct household", async () => {
  const call = vi.spyOn(api, "rankHomes").mockResolvedValue(ranking),
    open = vi.fn();
  render(<Homes homes={[]} customers={workspace.customers} openHome={open} />);
  await screen.findByText("Example household 1 / DEMO-01");
  fireEvent.change(screen.getByRole("searchbox"), {
    target: { value: "household 3" },
  });
  expect(screen.getByLabelText("Rank 3")).toBeTruthy();
  fireEvent.click(
    screen.getByRole("button", { name: "Open Example household 3 / DEMO-03" }),
  );
  expect(open).toHaveBeenCalledWith("DEMO-03");
  expect(call).toHaveBeenCalledTimes(1);
  const summary = screen.getByRole("region", {
    name: "Adviser assessment summary",
  });
  expect(
    within(summary).getByText("Homes in this view").nextElementSibling
      ?.textContent,
  ).toBe("1");
});
it("clears ranks during refresh and ignores late responses after changed inputs", async () => {
  const late = deferred<typeof ranking>();
  const call = vi
    .spyOn(api, "rankHomes")
    .mockResolvedValueOnce(ranking)
    .mockReturnValueOnce(late.promise)
    .mockRejectedValueOnce(new Error("Current ranking unavailable"));
  const { rerender } = render(
    <Homes homes={[]} customers={workspace.customers} openHome={vi.fn()} />,
  );
  await screen.findByText("Example household 1 / DEMO-01");
  fireEvent.click(screen.getByRole("button", { name: "Refresh ranking" }));
  expect(screen.queryByLabelText("Rank 1")).toBeNull();
  rerender(
    <Homes
      homes={[]}
      customers={workspace.customers.slice(1)}
      openHome={vi.fn()}
    />,
  );
  await screen.findByRole("alert");
  const summary = screen.getByRole("region", {
    name: "Adviser assessment summary",
  });
  expect(
    within(summary).getByText("Homes in this view").nextElementSibling
      ?.textContent,
  ).toBe("Unavailable");
  expect(summary.textContent).not.toContain("across 0 of 0");
  expect(call.mock.calls[1][1]?.aborted).toBe(true);
  await act(async () => late.resolve(ranking));
  expect(screen.queryByText("Example household 1 / DEMO-01")).toBeNull();
});
