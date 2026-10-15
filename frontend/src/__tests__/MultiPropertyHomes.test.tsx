import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { Homes } from "../Homes";
import { api } from "../api";
import { multiWorkspace } from "./multiPropertyFixtures";
import { deferred } from "./fixtures";
import { ranking } from "./workspaceFixtures";
import type { HomeRanking } from "../types";

it("flattens 1/2/4 properties with unique home IDs, owner labels, individual budgets and inherited exclusions", async () => {
  const workspace = multiWorkspace([1, 2, 4]);
  workspace.customers[1].portfolio_budget_gbp = 100000;
  workspace.customers[1].customer_preferences.deferred_retrofits = [
    "heat_pump",
  ];
  const data: HomeRanking = {
    ...ranking,
    rows: workspace.customers.flatMap((c) =>
      c.properties.map((p) => ({
        ...ranking.rows[0],
        property_id: p.home.property_id!,
        budget_gbp: p.preferences.budget_gbp,
      })),
    ),
  };
  const rank = vi.spyOn(api, "rankHomes").mockResolvedValue(data),
    open = vi.fn();
  render(
    <Homes
      workspaceId={workspace.id}
      customers={workspace.customers}
      homes={[]}
      openHome={open}
    />,
  );
  await screen.findByText("Example customer 3 / Fictional home 4");
  const inputs = rank.mock.calls[0][0];
  expect(inputs).toHaveLength(7);
  expect(new Set(inputs.map((home) => home.property_id)).size).toBe(7);
  expect(inputs[2]).toMatchObject({
    budget_gbp: 10000,
    excluded_retrofits: ["heat_pump"],
  });
  expect(inputs.every((home) => home.budget_gbp !== 100000)).toBe(true);
  fireEvent.click(
    screen.getByRole("button", {
      name: "Open Example customer 2 / Fictional home 2",
    }),
  );
  expect(open).toHaveBeenCalledWith("HOME-customer-2-2");
});

it("invalidates stale ranking when versions or workspace identity change even with identical input facts", async () => {
  const workspace = multiWorkspace();
  const late = deferred<HomeRanking>();
  const result: HomeRanking = {
    ...ranking,
    rows: workspace.customers.map((c) => ({
      ...ranking.rows[0],
      property_id: c.properties[0].home.property_id!,
      reason: "CURRENT SCOPED RANKING",
    })),
  };
  const rank = vi
    .spyOn(api, "rankHomes")
    .mockReturnValueOnce(late.promise)
    .mockResolvedValue(result);
  const view = render(
    <Homes
      workspaceId={workspace.id}
      customers={workspace.customers}
      homes={[]}
      openHome={vi.fn()}
    />,
  );
  const changed = structuredClone(workspace.customers);
  changed[0].version += 1;
  changed[0].properties[0].version += 1;
  view.rerender(
    <Homes
      workspaceId={workspace.id}
      customers={changed}
      homes={[]}
      openHome={vi.fn()}
    />,
  );
  await screen.findAllByText("CURRENT SCOPED RANKING");
  expect(rank.mock.calls[0][1]?.aborted).toBe(true);
  await act(async () =>
    late.resolve({
      ...result,
      rows: result.rows.map((row) => ({ ...row, reason: "STALE RANKING" })),
    }),
  );
  expect(screen.queryByText("STALE RANKING")).toBeNull();
  view.rerender(
    <Homes
      workspaceId="different-workspace"
      customers={changed}
      homes={[]}
      openHome={vi.fn()}
    />,
  );
  await screen.findAllByText("CURRENT SCOPED RANKING");
  expect(rank).toHaveBeenCalledTimes(3);
});
